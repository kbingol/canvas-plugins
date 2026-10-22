#!/usr/bin/env python3
"""Exercise the real Codex plugin loader without a model turn or user changes.

Only Python's standard library and an installed Codex CLI are required. All
configuration, caches, and logs belong to a disposable CODEX_HOME. By default a
deterministic read-only MCP fixture owns the package's canonical loopback port;
an occupied port is an error, never a reason to stop another application.

App-server is used as a diagnostic client only. No app-server plugin mutation
methods, account methods, model listing, or turn/start requests are sent.
"""

from __future__ import annotations

import argparse
import contextlib
from collections import deque
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlsplit
import uuid


CANONICAL_ENDPOINT = "http://127.0.0.1:47321/mcp"
TOOLS = frozenset(("canvas_get_status", "canvas_list_projects", "canvas_get_project", "canvas_list_agents"))
PROJECT_A = "11111111-1111-4111-8111-111111111111"
PROJECT_B = "22222222-2222-4222-8222-222222222222"
COMMON_FLAGS = ("--disable", "remote_plugin", "--disable", "apps")


class CheckFailure(RuntimeError):
    """A test failed without requiring a traceback containing environment data."""


def check(condition: Any, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def package_location(repository: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    catalog = read_json(repository / ".agents" / "plugins" / "marketplace.json")
    entry = next((item for item in catalog["plugins"] if item["name"] == "canvas"), None)
    check(entry is not None, "Marketplace must contain the Canvas plugin")
    source = entry["source"]
    relative = source if isinstance(source, str) else source.get("path", source.get("source"))
    check(isinstance(relative, str), "Canvas marketplace source must identify a local package")
    root = (repository / relative).resolve()
    check(root.is_relative_to(repository.resolve()), "Plugin source escapes repository")
    return catalog, entry, root


def user_config_snapshot() -> dict[str, str | None]:
    """Hash only relevant user configuration, never read or copy credentials."""
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    result = {}
    for relative in ("config.toml", "plugins/installed_plugins.json", "plugins/known_marketplaces.json"):
        path = root / relative
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


def isolated_environment(home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        upper = name.upper()
        if upper.endswith("API_KEY") or upper in {
            "OPENAI_ACCESS_TOKEN", "OPENAI_AUTH_TOKEN", "CODEX_API_KEY",
            "CODEX_MANAGED_MODE", "CODEX_CONFIG", "CODEX_CONFIG_FILE",
            "CODEX_CLI_PATH", "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
        }:
            environment.pop(name, None)
    environment.update({
        "CODEX_HOME": str(home), "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never", "NO_COLOR": "1",
    })
    return environment


def run_cli(codex: str, args: list[str], environment: dict[str, str], cwd: Path) -> Any:
    result = run_cli_process(codex, args, environment, cwd)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CheckFailure(f"Codex did not return JSON for {' '.join(args[:3])}: {result.stdout[-3000:]}") from error


def run_cli_process(codex: str, args: list[str], environment: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [codex, *COMMON_FLAGS, *args], cwd=cwd, env=environment,
        text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=120,
    )
    if result.returncode:
        # Output is from an unauthenticated, isolated process, not the user's CLI.
        raise CheckFailure(f"Codex {' '.join(args[:3])} failed ({result.returncode}):\n{result.stderr[-6000:]}")
    return result


def matching_plugins(value: Any, name: str = "canvas") -> list[dict[str, Any]]:
    found = []
    if isinstance(value, dict):
        if value.get("name") == name or value.get("pluginName") == name:
            found.append(value)
        for child in value.values():
            found.extend(matching_plugins(child, name))
    elif isinstance(value, list):
        for child in value:
            found.extend(matching_plugins(child, name))
    return found


class AppServer:
    """Bounded newline JSON-RPC client for the installed app-server executable."""

    def __init__(self, codex: str, environment: dict[str, str], cwd: Path, overrides: list[str] | None = None):
        self.messages: queue.Queue[Any] = queue.Queue()
        self.errors: deque[str] = deque(maxlen=80)
        self.notifications: list[dict[str, Any]] = []
        self.next_id = 1
        command = [codex, *COMMON_FLAGS]
        for override in overrides or []:
            command.extend(("-c", override))
        command.extend(("app-server", "--stdio"))
        self.process = subprocess.Popen(
            command, cwd=cwd, env=environment, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
        )
        self.readers = (
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        )
        for reader in self.readers:
            reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                self.errors.append("Non-JSON app-server stdout: " + line[:500])
        self.messages.put(None)

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.errors.append(line.rstrip()[:1000])

    def send(self, message: dict[str, Any]) -> None:
        method = message.get("method", "")
        check(method not in {"turn/start", "model/list"} and not method.startswith("account/"),
              "Installation diagnostics must not request inference or account access")
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def call(self, method: str, params: dict[str, Any], timeout: float = 45) -> Any:
        identifier = self.next_id
        self.next_id += 1
        self.send({"id": identifier, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            check(message is not None, f"app-server exited during {method}: {'; '.join(self.errors)[-3000:]}")
            if message.get("id") == identifier and "method" not in message:
                check("error" not in message, f"{method} failed: {message.get('error')}")
                return message.get("result")
            check("id" not in message or "method" not in message,
                  f"Unexpected server request in a no-inference diagnostic: {message.get('method')}")
            self.notifications.append(message)
        raise CheckFailure(f"app-server timed out during {method}: {'; '.join(self.errors)[-3000:]}")

    def __enter__(self) -> "AppServer":
        try:
            self.call("initialize", {
                "clientInfo": {"name": "canvas_plugin_install_test", "title": "Canvas installation diagnostic", "version": "1.0.0"},
                # Diagnostics only: mcpServer/tool/call is experimental in some CLI versions.
                "capabilities": {"experimentalApi": True},
            })
            self.send({"method": "initialized"})
        except BaseException:
            self.close()
            raise
        return self

    def close(self) -> None:
        if self.process.stdin:
            with contextlib.suppress(OSError):
                self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for reader in self.readers:
            reader.join(timeout=2)
        for stream in (self.process.stdout, self.process.stderr):
            if stream:
                stream.close()

    def __exit__(self, *_: Any) -> None:
        self.close()


def tool_definition(name: str) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
    if name == "canvas_get_project":
        schema["properties"] = {
            "sessionId": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100},
        }
        schema["required"] = ["sessionId"]
    return {
        "name": name, "description": "Read-only Canvas installation-test fixture: " + name,
        "inputSchema": schema,
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    }


def fixture_project(session: str) -> dict[str, Any]:
    return {"sessionId": session, "title": "Same project title", "projectPath": "fixture.flow",
            "isActive": session == PROJECT_A, "isLoaded": True, "isClosing": False,
            "revision": 7, "nodeCount": 2, "edgeCount": 2}


class McpFixture:
    """Deterministic Streamable HTTP MCP fixture; never touches Canvas files."""

    def __init__(self, port: int = 47321):
        self.calls: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_: Any) -> None:
                pass

            def reply(self, status: int, body: Any = None) -> None:
                data = json.dumps(body).encode("utf-8") if body is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def do_GET(self) -> None:
                self.reply(405)

            def do_DELETE(self) -> None:
                self.reply(200)

            def do_POST(self) -> None:
                if self.path != "/mcp" or "Origin" in self.headers:
                    self.reply(403)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    self.reply(413)
                    return
                try:
                    request = json.loads(self.rfile.read(length))
                    result = owner.dispatch(request)
                except (ValueError, KeyError, TypeError):
                    self.reply(400)
                    return
                if "id" not in request:
                    self.reply(202)
                else:
                    self.reply(200, {"jsonrpc": "2.0", "id": request["id"], "result": result})

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/mcp"

    def __enter__(self) -> "McpFixture":
        self.thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def dispatch(self, request: dict[str, Any]) -> Any:
        method = request["method"]
        with self.lock:
            self.calls.append(request)
        if method == "initialize":
            return {"protocolVersion": request["params"]["protocolVersion"], "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "canvas-install-fixture", "version": "1.0.0"}}
        if method in {"notifications/initialized", "notifications/cancelled", "ping"}:
            return {}
        if method == "tools/list":
            return {"tools": [tool_definition(name) for name in sorted(TOOLS)]}
        if method == "resources/list":
            return {"resources": []}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        check(method == "tools/call", f"Unsupported fixture MCP method {method}")
        name = request["params"]["name"]
        arguments = request["params"].get("arguments", {})
        error = None
        if name == "canvas_get_status":
            value = {"instanceId": PROJECT_A, "apiVersion": 1, "application": "Canvas", "isClosing": False, "capabilities": sorted(TOOLS)}
        elif name == "canvas_list_projects":
            value = {"projects": [fixture_project(PROJECT_A), fixture_project(PROJECT_B)]}
        elif name == "canvas_list_agents":
            value = {"agents": [{"id": "fixture-agent", "pluginId": "fixture", "version": "1.0.0", "name": "Fixture agent", "inputs": [], "outputs": []}]}
        elif name == "canvas_get_project":
            session = arguments.get("sessionId")
            offset, limit = arguments.get("offset", 0), arguments.get("limit", 100)
            try:
                valid_id = uuid.UUID(str(session)).int != 0
            except ValueError:
                valid_id = False
            if not valid_id or not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 100:
                error = "invalid_argument"
            elif session not in {PROJECT_A, PROJECT_B}:
                error = "project_not_found"
            if error:
                value = {"error": {"code": error, "message": "Use a live sessionId from canvas_list_projects."}}
            else:
                values = [{"id": f"{session}:{i}", "kind": "Note", "x": i, "y": 0, "text": f"{session} node {i}", "textTruncated": False,
                           "agentId": None, "agentName": None, "state": "Idle", "assetId": None} for i in range(2)]
                edges = [{"id": f"edge:{i}", "sourceId": values[0]["id"], "targetId": values[1]["id"], "sourcePortId": None, "targetPortId": None} for i in range(2)]
                value = {"project": fixture_project(session), "offset": offset, "limit": limit, "nodes": values[offset:offset + limit],
                         "edges": edges[offset:offset + limit], "hasMoreNodes": offset + limit < len(values), "hasMoreEdges": offset + limit < len(edges)}
        else:
            value, error = {"error": {"code": "unknown_method"}}, "unknown_method"
        return {"content": [{"type": "text", "text": json.dumps(value)}], "structuredContent": value, "isError": bool(error)}


def structured(result: dict[str, Any]) -> Any:
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = next((item["text"] for item in result.get("content", []) if item.get("type") == "text"), "")
    return json.loads(text)


def validate_endpoint(endpoint: str) -> None:
    parsed = urlsplit(endpoint)
    check(parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port is not None
          and parsed.path == "/mcp" and not parsed.query and not parsed.fragment
          and parsed.username is None and parsed.password is None,
          "Endpoint must be an exact local http://127.0.0.1:PORT/mcp URL without credentials or query")


def configure_fallback(codex: str, environment: dict[str, str], cwd: Path, endpoint: str) -> None:
    validate_endpoint(endpoint)
    # Exercise the same supported CLI command documented for custom profiles.
    run_cli_process(codex, ["mcp", "add", "canvas-local", "--url", endpoint], environment, cwd)
    config = Path(environment["CODEX_HOME"]) / "config.toml"
    with config.open("a", encoding="utf-8") as stream:
        stream.write('\n[plugins."canvas@canvas-plugins".mcp_servers.canvas]\nenabled = false\n')


def offline_check(codex: str, environment: dict[str, str], cwd: Path, fallback: bool) -> dict[str, Any]:
    with AppServer(codex, environment, cwd) as server:
        inventory = server.call("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"})
        candidates = [item for item in inventory["data"] if item["name"] == ("canvas-local" if fallback else "canvas")]
        check(len(candidates) == 1, "Offline Canvas server disappeared from configuration")
        item = candidates[0]
        check(not item["tools"] and (item.get("toolsError") or item.get("runtimeStatus") in {"failed", "notStarted"}),
              f"A fresh Codex connection must report the unavailable Canvas endpoint: {item}")
        return {"unavailableReported": True, "toolsReturned": len(item["tools"])}


def discover_canvas(server: AppServer, thread_id: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"detail": "full"}
    if thread_id:
        params["threadId"] = thread_id
    inventory = server.call("mcpServerStatus/list", params)
    matches = [item for item in inventory["data"] if TOOLS.issubset(set(item.get("tools", {})))]
    check(len(matches) == 1, f"Expected one connected Canvas server with all four tools; inventory: {inventory}")
    result = matches[0]
    check(result.get("toolsError") is None, "Canvas MCP tool discovery reported an error")
    for tool in result["tools"].values():
        check(tool.get("annotations", {}).get("readOnlyHint") is True, f"Tool must advertise read-only behavior: {tool.get('name')}")
    return result


def engine_checks(codex: str, environment: dict[str, str], cwd: Path, selector: str,
                  endpoint: str, fixture: McpFixture | None) -> dict[str, Any]:
    with AppServer(codex, environment, cwd) as server:
        skills = server.call("skills/list", {"cwds": [str(cwd)], "forceReload": True})
        bundled = [skill for entry in skills["data"] for skill in entry["skills"]
                   if skill.get("pluginId") == selector and skill.get("enabled")]
        check({"canvas:canvas", "canvas:setup"}.issubset({skill["name"] for skill in bundled}),
              "Installed Canvas workflow and onboarding skills are not discoverable by the real Codex loader")
        check(all(not entry["errors"] for entry in skills["data"]), "Installed skill discovery returned errors")
        # thread/start creates only an empty, ephemeral context. No turn is run.
        thread = server.call("thread/start", {"cwd": str(cwd), "ephemeral": True, "sandbox": "read-only", "approvalPolicy": "never"})
        thread_id = thread["thread"]["id"]
        inventory = discover_canvas(server, thread_id)
        origin = urlsplit(endpoint)
        check(inventory.get("httpOrigin") == f"{origin.scheme}://{origin.netloc}", "MCP loaded a different HTTP origin")
        if endpoint == CANONICAL_ENDPOINT:
            check(inventory.get("pluginId") in {selector, "canvas"} or "canvas" in str(inventory.get("pluginId", "")),
                  "Connected MCP must originate in the installed Canvas plugin")
        else:
            check(inventory["name"] == "canvas-local" and inventory.get("pluginId") is None,
                  "Custom endpoint must use the documented direct MCP registration")
            all_servers = server.call("mcpServerStatus/list", {"detail": "toolsAndAuthOnly", "threadId": thread_id})
            bundled_servers = [item for item in all_servers["data"] if item.get("pluginId") == selector]
            check(all(not item.get("tools") and item.get("runtimeStatus") in {"disabled", None} for item in bundled_servers),
                  "The bundled default connection must be disabled while preserving plugin skills")

        def call(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return server.call("mcpServer/tool/call", {"threadId": thread_id, "server": inventory["name"],
                               "tool": name, "arguments": arguments or {}})

        status = call("canvas_get_status")
        check(not status.get("isError") and structured(status)["application"] == "Canvas", "Canvas status tool failed")
        projects_result = call("canvas_list_projects")
        check(not projects_result.get("isError"), "Canvas project listing failed")
        projects = structured(projects_result)["projects"]
        agents = call("canvas_list_agents")
        check(not agents.get("isError") and isinstance(structured(agents)["agents"], list), "Canvas agent listing failed")
        project_checks = 0
        if fixture:
            check(len(projects) == 2 and projects[0]["title"] == projects[1]["title"], "Fixture must exercise duplicate project titles")
            selected = next(project for project in projects if not project["isActive"])
            first = structured(call("canvas_get_project", {"sessionId": selected["sessionId"], "offset": 0, "limit": 1}))
            second = structured(call("canvas_get_project", {"sessionId": selected["sessionId"], "offset": 1, "limit": 1}))
            check(first["project"]["sessionId"] == PROJECT_B == second["project"]["sessionId"], "Selected sessionId was not routed correctly")
            check(len(first["nodes"]) == len(first["edges"]) == 1 and first["hasMoreNodes"] and first["hasMoreEdges"], "First independently paged snapshot is incorrect")
            check(not second["hasMoreNodes"] and not second["hasMoreEdges"] and first["nodes"] != second["nodes"], "Second project page is incorrect")
            invalid = call("canvas_get_project", {"sessionId": "not-a-guid"})
            check(invalid.get("isError") is True and structured(invalid)["error"]["code"] == "invalid_argument", "Invalid session error was lost by the client")
            stale = call("canvas_get_project", {"sessionId": "33333333-3333-4333-8333-333333333333"})
            check(stale.get("isError") is True and structured(stale)["error"]["code"] == "project_not_found", "Stale session error was lost by the client")
            project_checks = 4
        else:
            loaded = [project for project in projects if project.get("isLoaded") and not project.get("isClosing")]
            if loaded:
                snapshot = call("canvas_get_project", {"sessionId": loaded[0]["sessionId"], "offset": 0, "limit": 1})
                check(not snapshot.get("isError"), "Live project snapshot failed")
                check(structured(snapshot)["project"]["sessionId"] == loaded[0]["sessionId"], "Live project session routing failed")
                project_checks = 1
            invalid = call("canvas_get_project", {"sessionId": "not-a-guid"})
            check(invalid.get("isError") is True and structured(invalid)["error"]["code"] == "invalid_argument",
                  "Live invalid-session error was lost by the client")
            project_checks += 1
        return {"serverName": inventory["name"], "pluginId": inventory.get("pluginId"),
                "toolCount": len(inventory["tools"]), "bundledSkillNames": [skill["name"] for skill in bundled],
                "projectChecks": project_checks, "modelTurns": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=str(Path(__file__).resolve().parents[1]), help="Local marketplace root or public Git repository URL")
    parser.add_argument("--codex", default=shutil.which("codex"), help="Installed Codex executable")
    parser.add_argument("--endpoint", help="Use an already-running Canvas endpoint instead of the deterministic fixture")
    parser.add_argument("--fixture-port", type=int, default=47321, help="Fixture port; default is the exact packaged URL. A different port requires an isolated fallback configuration")
    parser.add_argument("--artifacts", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts", help="Disposable test homes and final report directory")
    args = parser.parse_args(argv)
    check(args.codex, "Install Codex CLI before running installation diagnostics")
    check(0 <= args.fixture_port <= 65535, "Fixture port must be between 0 and 65535")
    args.artifacts.mkdir(parents=True, exist_ok=True)
    artifact_root = args.artifacts.resolve()
    before = user_config_snapshot()
    report: dict[str, Any] = {"repository": args.repository, "canonicalEndpoint": CANONICAL_ENDPOINT, "modelTurns": 0}
    version = subprocess.run([args.codex, "--version"], capture_output=True, text=True, timeout=15, check=True)
    report["codexVersion"] = version.stdout.strip()
    with tempfile.TemporaryDirectory(prefix="install-", dir=artifact_root) as temporary:
        run_root = Path(temporary).resolve()
        check(run_root.is_relative_to(artifact_root), "Test directory must stay inside artifacts")
        home, cwd = run_root / "home", run_root / "workspace"
        home.mkdir()
        cwd.mkdir()
        (cwd / ".canvas-plugin-test-root").touch()
        (home / "config.toml").write_text(
            'cli_auth_credentials_store = "file"\nproject_root_markers = [".canvas-plugin-test-root"]\n'
            '[analytics]\nenabled = false\n', encoding="utf-8")
        environment = isolated_environment(home)
        marketplace = run_cli(args.codex, ["plugin", "marketplace", "add", args.repository, "--json"], environment, cwd)
        report["marketplaceAdd"] = marketplace
        sources = run_cli(args.codex, ["plugin", "marketplace", "list", "--json"], environment, cwd)
        available = run_cli(args.codex, ["plugin", "list", "--available", "--json"], environment, cwd)
        entries = matching_plugins(available)
        check(entries, "Canvas plugin is absent from the real Codex marketplace listing")
        # This project's marketplace has a deliberately stable name.
        selector = "canvas@canvas-plugins"
        installed = run_cli(args.codex, ["plugin", "add", selector, "--json"], environment, cwd)
        report["install"] = installed
        listing = run_cli(args.codex, ["plugin", "list", "--json"], environment, cwd)
        check(matching_plugins(listing), "Canvas was not present after installation")
        endpoint = args.endpoint or f"http://127.0.0.1:{args.fixture_port}/mcp"
        if args.endpoint:
            validate_endpoint(endpoint)
        if endpoint != CANONICAL_ENDPOINT and args.endpoint:
            configure_fallback(args.codex, environment, cwd, endpoint)
        if args.endpoint:
            report["engine"] = engine_checks(args.codex, environment, cwd, selector, endpoint, None)
        else:
            with McpFixture(args.fixture_port) as fixture:
                endpoint = fixture.endpoint
                if endpoint != CANONICAL_ENDPOINT:
                    configure_fallback(args.codex, environment, cwd, endpoint)
                report["engine"] = engine_checks(args.codex, environment, cwd, selector, endpoint, fixture)
                methods = {request["method"] for request in fixture.calls}
                tools_called = {request["params"]["name"] for request in fixture.calls if request["method"] == "tools/call"}
                check({"initialize", "tools/list", "tools/call"}.issubset(methods), "Fixture did not observe a real MCP handshake and tool call")
                check(tools_called == TOOLS, "Client did not call all four Canvas tools")
                report["fixture"] = {"endpoint": endpoint, "toolsCalled": sorted(tools_called), "requestCount": len(fixture.calls)}
            report["offline"] = offline_check(args.codex, environment, cwd, endpoint != CANONICAL_ENDPOINT)
            with McpFixture(int(urlsplit(endpoint).port)) as recovered:
                report["reconnectedEngine"] = engine_checks(args.codex, environment, cwd, selector, endpoint, recovered)
        # Skill discovery must still work in endpoint-override diagnostics; the
        # fallback is disclosed in the report rather than claimed as package MCP.
        report["endpointOverride"] = endpoint != CANONICAL_ENDPOINT
        run_cli(args.codex, ["plugin", "remove", selector, "--json"], environment, cwd)
        removed = run_cli(args.codex, ["plugin", "list", "--json"], environment, cwd)
        installed_rows = removed.get("installed", []) if isinstance(removed, dict) else removed
        check(not matching_plugins(installed_rows), "Uninstall left Canvas installed")
        run_cli(args.codex, ["plugin", "marketplace", "remove", "canvas-plugins", "--json"], environment, cwd)
        report["uninstalled"] = True
        report["marketplaceSourcesVerified"] = bool(sources)
    check(user_config_snapshot() == before, "Real user Codex configuration changed during isolated diagnostics")
    report["userConfigurationUnchanged"] = True
    report["passed"] = True
    report_path = artifact_root / "install-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckFailure, OSError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
