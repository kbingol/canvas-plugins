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
import copy
from collections import deque
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import re
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
READ_TOOLS = frozenset(("canvas_get_status", "canvas_list_projects", "canvas_get_project", "canvas_list_agents", "canvas_get_assistant", "canvas_get_run"))
WRITE_TOOLS = frozenset(("canvas_create_assistant", "canvas_export_assistant", "canvas_delete_assistant", "canvas_edit_project", "canvas_run_node", "canvas_cancel_run"))
DESTRUCTIVE_TOOLS = frozenset(("canvas_delete_assistant", "canvas_edit_project", "canvas_run_node", "canvas_cancel_run"))
OPEN_WORLD_TOOLS = frozenset(("canvas_run_node",))
IDEMPOTENT_TOOLS = READ_TOOLS | {"canvas_edit_project", "canvas_run_node", "canvas_cancel_run"}
TOOLS = READ_TOOLS | WRITE_TOOLS
PRE_DELETE_TOOLS = TOOLS - {"canvas_delete_assistant", "canvas_edit_project", "canvas_run_node", "canvas_get_run", "canvas_cancel_run"}
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
                "clientInfo": {"name": "canvas_plugin_install_test", "title": "Canvas installation diagnostic", "version": "1.5.0"},
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
    elif name == "canvas_run_node":
        schema["properties"] = {
            "sessionId": {"type": "string", "format": "uuid"}, "nodeId": {"type": "string", "format": "uuid"},
            "request": {"type": "object", "properties": {
                "requestId": {"type": "string", "format": "uuid"},
                "expectedRevision": {"type": "integer", "minimum": 0},
                "confirmNewRun": {"type": "boolean", "default": False}},
                "required": ["requestId", "expectedRevision"], "additionalProperties": False}}
        schema["required"] = ["sessionId", "nodeId", "request"]
    elif name in {"canvas_get_run", "canvas_cancel_run"}:
        schema["properties"] = {key: {"type": "string", "format": "uuid"} for key in ("sessionId", "requestId")}
        schema["required"] = ["sessionId", "requestId"]
    elif name in {"canvas_get_assistant", "canvas_export_assistant", "canvas_delete_assistant"}:
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
    elif name == "canvas_edit_project":
        text = {"type": "string", "maxLength": 65536}
        position = {"x": {"type": "number", "minimum": -10000000, "maximum": 10000000}, "y": {"type": "number", "minimum": -10000000, "maximum": 10000000}}
        node = {"type": "object", "properties": {
            "key": {"type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9_-]{0,63}$"},
            "kind": {"type": "string", "enum": ["text", "assistant", "image", "video"]},
            **position, "text": text, "assistantId": {"type": "string"}},
            "required": ["key", "kind", "x", "y"], "additionalProperties": False}
        connection = {"type": "object", "properties": {
            key: {"type": "string"} for key in ("source", "target", "sourcePortId", "targetPortId")},
            "required": ["source", "target"], "additionalProperties": False}
        update = {"type": "object", "properties": {"nodeId": {"type": "string", "format": "uuid"}, "text": text},
                  "required": ["nodeId", "text"], "additionalProperties": False}
        move = {"type": "object", "properties": {"nodeId": {"type": "string", "format": "uuid"}, **position},
                "required": ["nodeId", "x", "y"], "additionalProperties": False}
        schema["properties"] = {"sessionId": {"type": "string", "format": "uuid"}, "edit": {
            "type": "object", "properties": {
                "requestId": {"type": "string", "format": "uuid"}, "expectedRevision": {"type": "integer", "minimum": 0},
                **{key: {"type": "array", "maxItems": maximum, "items": item}
                   for key, maximum, item in (("nodes", 100, node), ("connections", 200, connection),
                                               ("textUpdates", 100, update), ("moves", 100, move))}},
            "required": ["requestId", "expectedRevision"], "additionalProperties": False}}
        schema["required"] = ["sessionId", "edit"]
    read_only = name in READ_TOOLS
    return {
        "name": name, "description": "In-memory Canvas installation-test fixture: " + name,
        "inputSchema": schema,
        "annotations": {"readOnlyHint": read_only, "destructiveHint": name in DESTRUCTIVE_TOOLS, "idempotentHint": name in IDEMPOTENT_TOOLS, "openWorldHint": name in OPEN_WORLD_TOOLS},
    }


def fixture_project(session: str, revision: int = 7, nodes: int = 2, edges: int = 2) -> dict[str, Any]:
    return {"sessionId": session, "title": "Same project title", "projectPath": "fixture.flow",
            "isActive": session == PROJECT_A, "isLoaded": True, "isClosing": False,
            "revision": revision, "nodeCount": nodes, "edgeCount": edges}


def fixture_node_ports(kind: str) -> dict[str, Any]:
    if kind == "ImageGenerator":
        port = {"id": "context", "name": "Context", "kind": "Context", "required": False, "multiple": True, "maxItems": None}
        return {"inputPorts": [port], "outputPorts": [{**port, "required": True}]}
    port = {"id": "value", "name": kind, "kind": kind, "required": False, "multiple": False, "maxItems": None}
    return {"inputPorts": [port], "outputPorts": [port.copy()]}


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
        self.personal_assistants: set[str] = set()
        self.projects = {}
        self.edit_receipts: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self.runs: dict[tuple[str, str], dict[str, Any]] = {}
        self.confirmation_required: set[str] = set()
        for session in (PROJECT_A, PROJECT_B):
            values = [{"id": str(uuid.uuid5(uuid.UUID(session), f"node:{i}")), "kind": "Text", "x": i, "y": 0,
                       "text": f"{session} node {i}", "textTruncated": False, "agentId": None, "agentName": None,
                       "state": "Idle", "assetId": None, **fixture_node_ports("Text")} for i in range(2)]
            edges = [{"id": str(uuid.uuid5(uuid.UUID(session), f"edge:{i}")), "sourceId": values[0]["id"],
                      "targetId": values[1]["id"], "sourcePortId": None, "targetPortId": None} for i in range(2)]
            self.projects[session] = {"revision": 7, "nodes": values, "edges": edges}
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
            value = {"projects": [self.project_summary(session) for session in (PROJECT_A, PROJECT_B)]}
        elif name == "canvas_list_agents":
            with self.lock:
                value = {"agents": [{**{key: item[key] for key in ("id", "pluginId", "version", "name")},
                                     "inputs": [{"id": "context", "name": "Context", "kind": "Context", "required": False, "multiple": True, "maxItems": None}],
                                     "outputs": [{"id": "context", "name": "Context", "kind": "Context", "required": True, "multiple": True, "maxItems": None}],
                                     "origin": "personal" if item["id"] in self.personal_assistants else "bundled",
                                     "canDelete": item["id"] in self.personal_assistants} for item in self.assistants.values()]}
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
                        self.personal_assistants.add(stored["id"])
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
        elif name == "canvas_delete_assistant":
            with self.lock:
                assistant_id = arguments.get("assistantId")
                assistant = self.assistants.get(assistant_id)
                if assistant is None:
                    value, error = {"error": {"code": "assistant_not_found"}}, "assistant_not_found"
                elif assistant_id not in self.personal_assistants:
                    value, error = {"error": {"code": "assistant_protected"}}, "assistant_protected"
                else:
                    del self.assistants[assistant_id]
                    self.personal_assistants.remove(assistant_id)
                    value = {"id": assistant_id, "name": assistant["name"]}
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
                with self.lock:
                    state = self.projects[session]
                    values, edges = state["nodes"], state["edges"]
                    value = {"project": self.project_summary(session), "offset": offset, "limit": limit,
                             "nodes": copy.deepcopy(values[offset:offset + limit]), "edges": copy.deepcopy(edges[offset:offset + limit]),
                             "hasMoreNodes": offset + limit < len(values), "hasMoreEdges": offset + limit < len(edges)}
        elif name == "canvas_edit_project":
            value, error = self.edit_project(arguments)
        elif name == "canvas_run_node":
            value, error = self.run_node(arguments)
        elif name in {"canvas_get_run", "canvas_cancel_run"}:
            value, error = self.observe_run(arguments, cancel=name == "canvas_cancel_run")
        else:
            value, error = {"error": {"code": "unknown_method"}}, "unknown_method"
        return {"content": [{"type": "text", "text": json.dumps(value)}], "structuredContent": value, "isError": bool(error)}


    def project_summary(self, session: str) -> dict[str, Any]:
        state = self.projects[session]
        return fixture_project(session, state["revision"], len(state["nodes"]), len(state["edges"]))

    def edit_project(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """In-memory transaction fixture; production validation belongs to Canvas."""
        def fail(code: str) -> tuple[dict[str, Any], str]:
            return {"error": {"code": code}}, code

        def valid_guid(value: Any) -> bool:
            try:
                return isinstance(value, str) and uuid.UUID(value).int != 0
            except ValueError:
                return False

        def valid_position(item: Any) -> bool:
            return all(isinstance(item.get(key), (int, float)) and not isinstance(item[key], bool)
                       and math.isfinite(item[key]) and abs(item[key]) <= 10000000 for key in ("x", "y"))

        def valid_text(value: Any) -> bool:
            return isinstance(value, str) and len(value.encode("utf-16-le", errors="surrogatepass")) <= 131072

        session, edit = arguments.get("sessionId"), arguments.get("edit")
        if not valid_guid(session) or not isinstance(edit, dict) or not valid_guid(edit.get("requestId")):
            return fail("invalid_argument")
        revision = edit.get("expectedRevision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            return fail("invalid_argument")
        arrays = {key: edit.get(key, []) for key in ("nodes", "connections", "textUpdates", "moves")}
        if any(not isinstance(value, list) for value in arrays.values()):
            return fail("invalid_argument")
        if any(len(arrays[key]) > maximum for key, maximum in (("nodes", 100), ("connections", 200), ("textUpdates", 100), ("moves", 100))):
            return fail("invalid_argument")
        if not 1 <= sum(map(len, arrays.values())) <= 500:
            return fail("invalid_argument")
        if any(not isinstance(item, dict) for values in arrays.values() for item in values):
            return fail("invalid_argument")
        fingerprint = json.dumps(edit, sort_keys=True, separators=(",", ":"))
        receipt_key = (session, edit["requestId"])
        with self.lock:
            if session not in self.projects:
                return fail("project_not_found")
            if receipt_key in self.edit_receipts:
                previous, receipt = self.edit_receipts[receipt_key]
                if previous != fingerprint:
                    return fail("request_conflict")
                return {**copy.deepcopy(receipt), "replayed": True}, None
            if session != PROJECT_A:
                return fail("project_not_active")
            state = self.projects[session]
            if state["revision"] != revision:
                return fail("revision_conflict")
            staged = copy.deepcopy(state)
            node_by_id = {item["id"]: item for item in staged["nodes"]}
            new_nodes, new_edges, aliases = [], [], {}
            total_text_units = 0
            for item in arrays["nodes"]:
                key, kind = item.get("key"), item.get("kind")
                text = item.get("text", "")
                if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", key) or key in aliases:
                    return fail("invalid_argument")
                if kind not in {"text", "assistant", "image", "video"} or not valid_position(item) or not valid_text(text):
                    return fail("invalid_argument")
                assistant_id = item.get("assistantId")
                if (kind != "text" and item.get("text") is not None) or (kind != "assistant" and assistant_id is not None):
                    return fail("invalid_argument")
                if kind == "assistant" and assistant_id not in self.assistants:
                    return fail("agent_unavailable")
                total_text_units += len(text.encode("utf-16-le", errors="surrogatepass")) // 2
                node = {"id": str(uuid.uuid4()), "kind": {"text": "Text", "assistant": "ImageGenerator", "image": "Image", "video": "Video"}[kind],
                        "x": item["x"], "y": item["y"], "text": text, "textTruncated": False,
                        "agentId": assistant_id if kind == "assistant" else None,
                        "agentName": self.assistants[assistant_id]["name"] if kind == "assistant" else None,
                        "state": "Idle", "assetId": None, **fixture_node_ports("ImageGenerator" if kind == "assistant" else kind.title())}
                aliases[key] = node["id"]
                node_by_id[node["id"]] = node
                staged["nodes"].append(node)
                new_nodes.append({"key": key, "node": node})
            changed = bool(new_nodes)
            existing_ids = {item["id"] for item in state["nodes"]}
            for item in arrays["textUpdates"]:
                node = node_by_id.get(item.get("nodeId")) if item.get("nodeId") in existing_ids else None
                if node is None:
                    return fail("node_not_found")
                if node["kind"] != "Text" or any(edge["targetId"] == node["id"] for edge in staged["edges"]) or any(aliases.get(wire.get("target"), wire.get("target")) == node["id"] for wire in arrays["connections"]):
                    return fail("node_not_editable")
                if not valid_text(item.get("text")):
                    return fail("invalid_argument")
                total_text_units += len(item["text"].encode("utf-16-le", errors="surrogatepass")) // 2
                changed = changed or node["text"] != item["text"]
                node["text"] = item["text"]
            if total_text_units > 262144:
                return fail("invalid_argument")
            for item in arrays["moves"]:
                node = node_by_id.get(item.get("nodeId")) if item.get("nodeId") in existing_ids else None
                if node is None:
                    return fail("node_not_found")
                if not valid_position(item):
                    return fail("invalid_argument")
                changed = changed or (node["x"], node["y"]) != (item["x"], item["y"])
                node.update(x=item["x"], y=item["y"])
            for item in arrays["connections"]:
                source = node_by_id.get(aliases.get(item.get("source"), item.get("source")))
                target = node_by_id.get(aliases.get(item.get("target"), item.get("target")))
                if source is None or target is None:
                    return fail("node_not_found")
                if source is target:
                    return fail("invalid_connection")
                for port, node in (("sourcePortId", source), ("targetPortId", target)):
                    if node["kind"] == "ImageGenerator" and item.get(port) not in {None, "context"}:
                        return fail("invalid_connection")
                    if node["kind"] != "ImageGenerator" and item.get(port) not in {None, "value"}:
                        return fail("invalid_connection")
                if target["kind"] != "ImageGenerator":
                    if source["kind"] != target["kind"] or any(edge["targetId"] == target["id"] for edge in staged["edges"]):
                        return fail("invalid_connection")
                source_port = "context" if source["kind"] == "ImageGenerator" else "value"
                target_port = "context" if target["kind"] == "ImageGenerator" else "value"
                if any((edge["sourceId"], edge["targetId"], edge["sourcePortId"], edge["targetPortId"])
                       == (source["id"], target["id"], source_port, target_port) for edge in staged["edges"]):
                    return fail("invalid_connection")
                edge = {"id": str(uuid.uuid4()), "sourceId": source["id"], "targetId": target["id"],
                        "sourcePortId": source_port, "targetPortId": target_port}
                staged["edges"].append(edge)
                new_edges.append(edge)
                changed = True
            staged["revision"] += int(changed)
            receipt = {"sessionId": session, "requestId": edit["requestId"], "revision": staged["revision"],
                       "nodes": new_nodes, "edges": new_edges, "changed": changed, "replayed": False}
            self.projects[session] = staged
            self.edit_receipts[receipt_key] = (fingerprint, copy.deepcopy(receipt))
            session_receipts = [key for key in self.edit_receipts if key[0] == session]
            for key in session_receipts[:-128]:
                del self.edit_receipts[key]
            return receipt, None


    @staticmethod
    def valid_run_guid(value: Any) -> bool:
        try:
            return isinstance(value, str) and uuid.UUID(value).int != 0
        except ValueError:
            return False

    @staticmethod
    def run_error(code: str) -> tuple[dict[str, Any], str]:
        return {"error": {"code": code}}, code

    def run_snapshot(self, record: dict[str, Any], replayed: bool = False) -> dict[str, Any]:
        if record["completed"]:
            return {**copy.deepcopy(record["snapshot"]), "replayed": replayed}
        state = self.projects[record["sessionId"]]
        node = next(item for item in state["nodes"] if item["id"] == record["nodeId"])
        return {"sessionId": record["sessionId"], "requestId": record["request"]["requestId"], "nodeId": node["id"],
                "status": record["status"], "phase": record["phase"], "errorCode": None, "revision": state["revision"],
                "node": copy.deepcopy(node), "outputs": [], "replayed": replayed, "hasMoreOutputs": False}

    def run_node(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """Admit only synthetic in-memory work; no Canvas engine or provider is called."""
        session, node_id, request = arguments.get("sessionId"), arguments.get("nodeId"), arguments.get("request")
        if not self.valid_run_guid(session) or not self.valid_run_guid(node_id) or not isinstance(request, dict):
            return self.run_error("invalid_argument")
        if not self.valid_run_guid(request.get("requestId")) or not isinstance(request.get("expectedRevision"), int) or isinstance(request.get("expectedRevision"), bool) or request["expectedRevision"] < 0 or not isinstance(request.get("confirmNewRun", False), bool):
            return self.run_error("invalid_argument")
        normalized = {"requestId": request["requestId"], "expectedRevision": request["expectedRevision"], "confirmNewRun": request.get("confirmNewRun", False)}
        key = (session, request["requestId"])
        with self.lock:
            if session not in self.projects:
                return self.run_error("project_not_found")
            if key in self.runs:
                record = self.runs[key]
                if record["nodeId"] != node_id or record["request"] != normalized:
                    return self.run_error("request_conflict")
                return self.run_snapshot(record, replayed=True), None
            if session != PROJECT_A:
                return self.run_error("project_not_active")
            state = self.projects[session]
            if state["revision"] != request["expectedRevision"]:
                return self.run_error("revision_conflict")
            node = next((item for item in state["nodes"] if item["id"] == node_id), None)
            if node is None:
                return self.run_error("node_not_found")
            active = [item for item in self.runs.values() if item["sessionId"] == session and not item["completed"]]
            if node["state"] == "Running" or any(item["nodeId"] == node_id for item in active):
                return self.run_error("node_running")
            if node["kind"] != "ImageGenerator" or node["agentId"] not in self.assistants:
                return self.run_error("agent_unavailable")
            visited, pending = set(), [edge["sourceId"] for edge in state["edges"] if edge["targetId"] == node_id]
            while pending:
                upstream = pending.pop()
                if upstream in visited:
                    continue
                visited.add(upstream)
                if any(item["nodeId"] == upstream for item in active):
                    return self.run_error("upstream_running")
                pending.extend(edge["sourceId"] for edge in state["edges"] if edge["targetId"] == upstream)
            if node_id in self.confirmation_required and not normalized["confirmNewRun"]:
                return self.run_error("run_confirmation_required")
            if len(active) >= 8:
                return self.run_error("run_limit")
            node["state"] = "Running"
            state["revision"] += 1
            record = {"sessionId": session, "nodeId": node_id, "request": normalized, "status": "running", "phase": "preparing",
                      "polls": 0, "completed": False}
            self.runs[key] = record
            return self.run_snapshot(record), None

    def finish_fixture_run(self, record: dict[str, Any], status: str) -> None:
        state = self.projects[record["sessionId"]]
        node = next(item for item in state["nodes"] if item["id"] == record["nodeId"])
        outputs = []
        if status == "succeeded":
            output_id = str(uuid.uuid4())
            item_port = "context::fixture-" + record["request"]["requestId"]
            output = {"id": output_id, "kind": "Text", "x": node["x"] + 360, "y": node["y"],
                      "text": "Synthetic fixture result; no model was called.", "textTruncated": False,
                      "agentId": None, "agentName": None, "state": "Idle", "assetId": None, **fixture_node_ports("Text")}
            state["nodes"].append(output)
            state["edges"].append({"id": str(uuid.uuid4()), "sourceId": node["id"], "targetId": output_id,
                                   "sourcePortId": item_port, "targetPortId": "value"})
            node["outputPorts"].append({"id": item_port, "name": "Context 1", "kind": "Text", "required": True, "multiple": False, "maxItems": None})
            node["state"] = "Ready"
            outputs = [copy.deepcopy(output)]
        else:
            node["state"] = "Idle"
        state["revision"] += 1
        record["status"], record["phase"] = status, None
        snapshot = self.run_snapshot(record)
        snapshot["outputs"] = outputs
        record["snapshot"], record["completed"] = snapshot, True
        finished = [key for key, item in self.runs.items() if key[0] == record["sessionId"] and item["completed"]]
        for key in finished[:-128]:
            del self.runs[key]

    def observe_run(self, arguments: dict[str, Any], cancel: bool = False) -> tuple[dict[str, Any], str | None]:
        session, request_id = arguments.get("sessionId"), arguments.get("requestId")
        if not self.valid_run_guid(session) or not self.valid_run_guid(request_id):
            return self.run_error("invalid_argument")
        with self.lock:
            if session not in self.projects:
                return self.run_error("project_not_found")
            record = self.runs.get((session, request_id))
            if record is None:
                return self.run_error("run_not_found")
            if not record["completed"]:
                if cancel:
                    record["status"] = "canceling"
                elif record["status"] == "canceling":
                    self.finish_fixture_run(record, "canceled")
                else:
                    record["polls"] += 1
                    record["phase"] = "working"
                    if record["polls"] >= 2:
                        self.finish_fixture_run(record, "succeeded")
            return self.run_snapshot(record), None


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


def discover_canvas(server: AppServer, thread_id: str | None = None, require_current: bool = True) -> dict[str, Any]:
    params: dict[str, Any] = {"detail": "full"}
    if thread_id:
        params["threadId"] = thread_id
    inventory = server.call("mcpServerStatus/list", params)
    required = TOOLS if require_current else PRE_DELETE_TOOLS
    matches = [item for item in inventory["data"] if required.issubset(set(item.get("tools", {})))]
    check(len(matches) == 1, f"Expected one connected Canvas server with {len(required)} required tools; inventory: {inventory}")
    result = matches[0]
    check(result.get("toolsError") is None, "Canvas MCP tool discovery reported an error")
    for name in TOOLS & set(result["tools"]):
        tool = result["tools"][name]
        check(tool.get("annotations", {}).get("readOnlyHint") is (name in READ_TOOLS),
              f"Tool must advertise its actual read/write behavior: {name}")
        check(tool.get("annotations", {}).get("destructiveHint") is (name in DESTRUCTIVE_TOOLS),
              f"Tool must advertise its actual destructive behavior: {name}")
        check(tool.get("annotations", {}).get("idempotentHint") is (name in IDEMPOTENT_TOOLS),
              f"Tool must advertise its actual retry behavior: {name}")
        check(tool.get("annotations", {}).get("openWorldHint") is (name in OPEN_WORLD_TOOLS),
              f"Tool must advertise whether external providers can be called: {name}")
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
        inventory = discover_canvas(server, thread_id, require_current=fixture is not None)
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
        flow_checks = 0
        execution_checks = 0
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
            flow = {"requestId": str(uuid.uuid4()), "expectedRevision": 7,
                    "nodes": [{"key": "source", "kind": "text", "x": 300, "y": 200, "text": "Translate this text."},
                              {"key": "agent", "kind": "assistant", "x": 650, "y": 200, "assistantId": "fixture-agent"}],
                    "connections": [{"source": "source", "target": "agent", "targetPortId": "context"}]}
            edit_args = {"sessionId": PROJECT_A, "edit": flow}
            edited = call("canvas_edit_project", edit_args)
            receipt = structured(edited)
            check(not edited.get("isError") and receipt["changed"] and receipt["revision"] == 8,
                  "Flow transaction did not cross the installed MCP connection")
            check(len(receipt["nodes"]) == 2 and len(receipt["edges"]) == 1, "Flow edit receipt lost new node aliases or wires")
            replayed = call("canvas_edit_project", edit_args)
            check(not replayed.get("isError") and structured(replayed)["replayed"] and structured(replayed)["revision"] == 8,
                  "Exact transaction retry must replay its receipt without duplicates")
            conflicting = call("canvas_edit_project", {"sessionId": PROJECT_A, "edit": {**flow, "expectedRevision": 8}})
            check(conflicting.get("isError") and structured(conflicting)["error"]["code"] == "request_conflict",
                  "Changing a used request payload must remain a conflict")
            stale_edit = call("canvas_edit_project", {"sessionId": PROJECT_A, "edit": {**flow, "requestId": str(uuid.uuid4())}})
            check(stale_edit.get("isError") and structured(stale_edit)["error"]["code"] == "revision_conflict",
                  "Stale project revisions must be rejected")
            failed_edit = call("canvas_edit_project", {"sessionId": PROJECT_A, "edit": {
                "requestId": str(uuid.uuid4()), "expectedRevision": 8,
                "nodes": [{"key": "temporary", "kind": "text", "x": 0, "y": 0, "text": "Must not appear"}],
                "connections": [{"source": "temporary", "target": str(uuid.uuid4())}]}})
            snapshot = structured(call("canvas_get_project", {"sessionId": PROJECT_A}))
            check(failed_edit.get("isError") and snapshot["project"]["revision"] == 8 and len(snapshot["nodes"]) == 4,
                  "Failed flow transactions must leave the graph unchanged")
            ids = {item["key"]: item["node"]["id"] for item in receipt["nodes"]}
            updated = call("canvas_edit_project", {"sessionId": PROJECT_A, "edit": {
                "requestId": str(uuid.uuid4()), "expectedRevision": 8,
                "textUpdates": [{"nodeId": ids["source"], "text": "Updated translation input."}],
                "moves": [{"nodeId": ids["agent"], "x": 800, "y": 220}]}})
            final = structured(call("canvas_get_project", {"sessionId": PROJECT_A}))
            check(not updated.get("isError") and final["project"]["revision"] == 9
                  and next(item for item in final["nodes"] if item["id"] == ids["source"])["text"] == "Updated translation input."
                  and next(item for item in final["nodes"] if item["id"] == ids["agent"])["x"] == 800,
                  "Existing node text and positions must round-trip through the connection")
            flow_checks = 6
            # Synthetic job lifecycle only: this fixture has no provider/client implementation.
            current = structured(call("canvas_get_project", {"sessionId": PROJECT_A}))
            run_request = {"requestId": str(uuid.uuid4()), "expectedRevision": current["project"]["revision"]}
            run_args = {"sessionId": PROJECT_A, "nodeId": ids["agent"], "request": run_request}
            admitted = call("canvas_run_node", run_args)
            check(not admitted.get("isError") and structured(admitted)["status"] == "running", "Execution must return an immediate receipt")
            repeated = call("canvas_run_node", run_args)
            check(not repeated.get("isError") and structured(repeated)["replayed"], "An exact start retry must not create a second job")
            changed_run = call("canvas_run_node", {**run_args, "request": {**run_request, "confirmNewRun": True}})
            check(changed_run.get("isError") and structured(changed_run)["error"]["code"] == "request_conflict",
                  "Changing a run confirmation flag under the same request must conflict")
            query = {"sessionId": PROJECT_A, "requestId": run_request["requestId"]}
            progressing = call("canvas_get_run", query)
            check(not progressing.get("isError") and structured(progressing)["status"] == "running", "Status read must expose running work")
            completed = call("canvas_get_run", query)
            check(not completed.get("isError") and structured(completed)["status"] == "succeeded" and len(structured(completed)["outputs"]) == 1,
                  "Successful execution must return actual synthetic result snapshots")
            after_run = structured(call("canvas_get_project", {"sessionId": PROJECT_A}))
            cancel_request = {"requestId": str(uuid.uuid4()), "expectedRevision": after_run["project"]["revision"]}
            cancel_start = call("canvas_run_node", {**run_args, "request": cancel_request})
            check(not cancel_start.get("isError"), "A separate requested run must receive a separate receipt")
            cancel_query = {"sessionId": PROJECT_A, "requestId": cancel_request["requestId"]}
            old_cancel = call("canvas_cancel_run", query)
            check(not old_cancel.get("isError") and structured(old_cancel)["status"] == "succeeded",
                  "Canceling a completed receipt must not cancel a later run of the same node")
            canceling = call("canvas_cancel_run", cancel_query)
            repeated_cancel = call("canvas_cancel_run", cancel_query)
            check(not canceling.get("isError") and structured(canceling)["status"] == "canceling"
                  and structured(repeated_cancel)["status"] == "canceling", "Cancellation requests must be owned and idempotent")
            canceled = call("canvas_get_run", cancel_query)
            check(not canceled.get("isError") and structured(canceled)["status"] == "canceled", "Observe cancellation until terminal")
            missing_run = call("canvas_get_run", {"sessionId": PROJECT_A, "requestId": str(uuid.uuid4())})
            check(missing_run.get("isError") and structured(missing_run)["error"]["code"] == "run_not_found", "Missing run receipt error was lost")
            execution_checks = 10
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
            personal = next(item for item in structured(call("canvas_list_agents"))["agents"] if item["id"] == definition["id"])
            check(personal["origin"] == "personal" and personal["canDelete"], "Created assistant must report its personal installation origin")
            protected = call("canvas_delete_assistant", {"assistantId": "fixture-agent"})
            check(protected.get("isError") is True and structured(protected)["error"]["code"] == "assistant_protected",
                  "Bundled package deletion must remain protected")
            deleted = call("canvas_delete_assistant", {"assistantId": definition["id"]})
            check(not deleted.get("isError") and structured(deleted)["id"] == definition["id"], "Personal deletion result was lost")
            missing = call("canvas_get_assistant", {"assistantId": definition["id"]})
            check(missing.get("isError") is True and structured(missing)["error"]["code"] == "assistant_not_found",
                  "Deleted assistant must become unavailable immediately")
            authoring_checks = 9
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
                "personalDeletionAvailable": "canvas_delete_assistant" in inventory["tools"],
                "flowEditingAvailable": "canvas_edit_project" in inventory["tools"],
                "executionAvailable": {"canvas_run_node", "canvas_get_run", "canvas_cancel_run"}.issubset(inventory["tools"]),
                "projectChecks": project_checks, "fixtureAuthoringChecks": authoring_checks, "fixtureFlowChecks": flow_checks, "fixtureExecutionChecks": execution_checks, "modelTurns": 0}


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
                check(tools_called == TOOLS, "Client did not call all twelve Canvas tools")
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
