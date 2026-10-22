#!/usr/bin/env python3
"""Exercise the real Codex plugin loader without a model turn or user changes.

Only Python's standard library and an installed Codex CLI are required. All
configuration, caches, and logs belong to a disposable CODEX_HOME. By default a
deterministic in-memory MCP fixture owns the package's canonical loopback port;
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
import tomllib
from typing import Any
from urllib.parse import urlsplit
import uuid


CANONICAL_ENDPOINT = "http://127.0.0.1:47321/mcp"
READ_TOOLS = frozenset(("canvas_get_status", "canvas_list_projects", "canvas_get_project", "canvas_list_agents", "canvas_get_assistant"))
WRITE_TOOLS = frozenset(("canvas_create_assistant", "canvas_export_assistant"))
TOOLS = READ_TOOLS | WRITE_TOOLS
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
                "clientInfo": {"name": "canvas_plugin_install_test", "title": "Canvas installation diagnostic", "version": "1.2.0"},
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
    elif name in {"canvas_get_assistant", "canvas_export_assistant"}:
        schema["properties"] = {"assistantId": {"type": "string"}}
        schema["required"] = ["assistantId"]
        if name == "canvas_export_assistant":
            schema["properties"]["destinationPath"] = {"type": "string"}
    elif name == "canvas_create_assistant":
        fields = ("id", "pluginId", "name", "description", "instructions", "contextPreamble")
        schema["properties"] = {"definition": {
            "type": "object", "properties": {field: {"type": "string"} for field in fields},
            "required": list(fields), "additionalProperties": True,
        }}
        schema["required"] = ["definition"]
    read_only = name in READ_TOOLS
    return {
        "name": name, "description": "In-memory Canvas installation-test fixture: " + name,
        "inputSchema": schema,
        "annotations": {"readOnlyHint": read_only, "destructiveHint": False, "idempotentHint": read_only, "openWorldHint": False},
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
        self.assistants = {"fixture-agent": {
            "id": "fixture-agent", "pluginId": "fixture", "version": "1.0.0", "name": "Fixture agent",
            "description": "In-memory diagnostic assistant", "instructions": "Translate the supplied text.",
            "contextPreamble": "Translate the ordered context.", "icon": "text", "tools": [], "skills": [],
        }}
        self.exports: set[str] = set()
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
            with self.lock:
                value = {"agents": [{**{key: item[key] for key in ("id", "pluginId", "version", "name")},
                                     "inputs": [], "outputs": []} for item in self.assistants.values()]}
        elif name == "canvas_get_assistant":
            with self.lock:
                value = self.assistants.get(arguments.get("assistantId"))
            if value is None:
                value, error = {"error": {"code": "assistant_not_found"}}, "assistant_not_found"
        elif name == "canvas_create_assistant":
            definition = arguments.get("definition")
            fields = ("id", "pluginId", "name", "description", "instructions", "contextPreamble")
            if not isinstance(definition, dict) or any(not isinstance(definition.get(key), str) or not definition[key].strip() for key in fields):
                value, error = {"error": {"code": "invalid_argument"}}, "invalid_argument"
            else:
                with self.lock:
                    if any(item["id"] == definition["id"] or item["pluginId"] == definition["pluginId"] for item in self.assistants.values()):
                        value, error = {"error": {"code": "assistant_conflict"}}, "assistant_conflict"
                    else:
                        stored = {"version": "1.0.0", "icon": "text", "tools": [], "skills": [], **definition}
                        self.assistants[stored["id"]] = stored
                        value = {key: stored[key] for key in ("id", "pluginId", "name", "version")}
                        value["directoryPath"] = "fixture/assistants/" + stored["id"]
        elif name == "canvas_export_assistant":
            with self.lock:
                assistant = self.assistants.get(arguments.get("assistantId"))
                if assistant is None:
                    value, error = {"error": {"code": "assistant_not_found"}}, "assistant_not_found"
                else:
                    target = arguments.get("destinationPath") or f"fixture/Exports/{assistant['id']}-{len(self.exports) + 1}.flowast"
                    if target in self.exports:
                        value, error = {"error": {"code": "destination_exists"}}, "destination_exists"
                    else:
                        self.exports.add(target)
                        value = {"id": assistant["id"], "version": assistant["version"], "filePath": target, "byteLength": 512}
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
    check(endpoint == CANONICAL_ENDPOINT,
          f"Installation diagnostics require the bundled endpoint {CANONICAL_ENDPOINT}; endpoint overrides are not supported")


def offline_check(codex: str, environment: dict[str, str], cwd: Path) -> dict[str, Any]:
    with AppServer(codex, environment, cwd) as server:
        inventory = server.call("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"})
        candidates = [item for item in inventory["data"] if item["name"] == "canvas"]
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
    check(len(matches) == 1, f"Expected one connected Canvas server with all seven tools; inventory: {inventory}")
    result = matches[0]
    check(result.get("toolsError") is None, "Canvas MCP tool discovery reported an error")
    for name in TOOLS:
        tool = result["tools"][name]
        check(tool.get("annotations", {}).get("readOnlyHint") is (name in READ_TOOLS),
              f"Tool must advertise its actual read/write behavior: {name}")
    return result


def engine_checks(codex: str, environment: dict[str, str], cwd: Path, selector: str,
                  endpoint: str, fixture: McpFixture | None) -> dict[str, Any]:
    with AppServer(codex, environment, cwd) as server:
        skills = server.call("skills/list", {"cwds": [str(cwd)], "forceReload": True})
        bundled = [skill for entry in skills["data"] for skill in entry["skills"]
                   if skill.get("pluginId") == selector and skill.get("enabled")]
        check({"canvas:canvas", "canvas:setup", "canvas:assistant-authoring"}.issubset({skill["name"] for skill in bundled}),
              "Installed Canvas workflow and onboarding skills are not discoverable by the real Codex loader")
        check(all(not entry["errors"] for entry in skills["data"]), "Installed skill discovery returned errors")
        # thread/start creates only an empty, ephemeral context. No turn is run.
        thread = server.call("thread/start", {"cwd": str(cwd), "ephemeral": True, "sandbox": "read-only", "approvalPolicy": "never"})
        thread_id = thread["thread"]["id"]
        inventory = discover_canvas(server, thread_id)
        origin = urlsplit(endpoint)
        check(inventory.get("httpOrigin") == f"{origin.scheme}://{origin.netloc}", "MCP loaded a different HTTP origin")
        check(endpoint == CANONICAL_ENDPOINT and inventory["name"] == "canvas",
              "Connected MCP must use the packaged fixed endpoint and server name")
        check(inventory.get("pluginId") == selector,
              "Connected MCP must originate in the installed Canvas plugin")

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
        authoring_checks = 0
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
            # Writes below affect only this fixture's in-memory dictionaries.
            original = call("canvas_get_assistant", {"assistantId": "fixture-agent"})
            check(not original.get("isError") and structured(original)["instructions"], "Assistant definition inspection failed")
            definition = {"id": "user.install-check", "pluginId": "user.assistant.install-check", "name": "Install check",
                          "description": "In-memory connection check", "instructions": "Translate the supplied text.",
                          "contextPreamble": "Translate ordered context."}
            created = call("canvas_create_assistant", {"definition": definition})
            check(not created.get("isError") and structured(created)["id"] == definition["id"], "Assistant creation result was lost")
            duplicate = call("canvas_create_assistant", {"definition": definition})
            check(duplicate.get("isError") is True, "Duplicate assistant creation must remain an error")
            inspected = call("canvas_get_assistant", {"assistantId": definition["id"]})
            check(not inspected.get("isError") and structured(inspected)["instructions"] == definition["instructions"],
                  "Created definition must round-trip through the installed connection")
            exported = call("canvas_export_assistant", {"assistantId": definition["id"]})
            check(not exported.get("isError") and structured(exported)["filePath"].endswith(".flowast"), "Assistant export result was lost")
            authoring_checks = 5
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
                "projectChecks": project_checks, "fixtureAuthoringChecks": authoring_checks, "modelTurns": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=str(Path(__file__).resolve().parents[1]), help="Local marketplace root or public Git repository URL")
    parser.add_argument("--codex", default=shutil.which("codex"), help="Installed Codex executable")
    parser.add_argument("--endpoint", help=f"Use an already-running Canvas app at exactly {CANONICAL_ENDPOINT} instead of the fixture")
    parser.add_argument("--artifacts", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts", help="Disposable test homes and final report directory")
    args = parser.parse_args(argv)
    # Reject unsupported URLs before creating test state or running any client
    # command. A direct server registration would hide a broken plugin install.
    if args.endpoint is not None:
        validate_endpoint(args.endpoint)
    check(args.codex, "Install Codex CLI before running installation diagnostics")
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
        installed_root = Path(installed["installedPath"]).resolve()
        check(installed_root.is_relative_to(home), "Plugin installation must stay inside the disposable home")
        installed_manifest = read_json(installed_root / "plugin.json")
        installed_mcp = read_json(installed_root / "mcp.json")
        check(installed_manifest["name"] == "canvas" and installed_manifest["version"] == installed["version"],
              "Installed plugin identity or version does not match the marketplace result")
        check(installed_mcp["mcpServers"] == {"canvas": {"type": "streamable-http", "url": CANONICAL_ENDPOINT}},
              "The installed bundle must retain the exact fixed HTTP server declaration")
        installed_files = {str(path.relative_to(installed_root)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in installed_root.rglob("*") if path.is_file()}
        listing = run_cli(args.codex, ["plugin", "list", "--json"], environment, cwd)
        check(matching_plugins(listing), "Canvas was not present after installation")
        installed_config = (home / "config.toml").read_bytes()
        check(not tomllib.loads(installed_config.decode("utf-8")).get("mcp_servers"),
              "Installation must not add a separate global MCP server")
        endpoint = CANONICAL_ENDPOINT
        if args.endpoint:
            report["engine"] = engine_checks(args.codex, environment, cwd, selector, endpoint, None)
        else:
            with McpFixture() as fixture:
                check(fixture.endpoint == endpoint, "Fixture must use the installed plugin's fixed endpoint")
                report["engine"] = engine_checks(args.codex, environment, cwd, selector, endpoint, fixture)
                methods = {request["method"] for request in fixture.calls}
                tools_called = {request["params"]["name"] for request in fixture.calls if request["method"] == "tools/call"}
                check({"initialize", "tools/list", "tools/call"}.issubset(methods), "Fixture did not observe a real MCP handshake and tool call")
                check(tools_called == TOOLS, "Client did not call all seven Canvas tools")
                report["fixture"] = {"endpoint": endpoint, "toolsCalled": sorted(tools_called), "requestCount": len(fixture.calls)}
            report["offline"] = offline_check(args.codex, environment, cwd)
            with McpFixture() as recovered:
                report["reconnectedEngine"] = engine_checks(args.codex, environment, cwd, selector, endpoint, recovered)
        check((home / "config.toml").read_bytes() == installed_config,
              "Connection checks must not rewrite the installed client's configuration")
        check({str(path.relative_to(installed_root)): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in installed_root.rglob("*") if path.is_file()} == installed_files,
              "Connection checks must not modify the installed plugin bundle")
        report["bundledConnectionOnly"] = True
        report["installationConfigurationUnchanged"] = True
        report["installedBundleUnchanged"] = True
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
