"""Package and transport contract checks; no third-party test dependency."""

from __future__ import annotations

import importlib.util
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("canvas_install_checks", ROOT / "scripts" / "test_install.py")
assert SPEC is not None and SPEC.loader is not None
install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install)


class PackageChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.entry, cls.plugin_root = install.package_location(ROOT)

    def test_marketplace_has_stable_identity_and_one_canvas_package(self):
        self.assertEqual(self.catalog["name"], "canvas-plugins")
        self.assertEqual(len([item for item in self.catalog["plugins"] if item["name"] == "canvas"]), 1)
        self.assertTrue(self.plugin_root.is_dir())

    def test_portable_manifest_identity_version_and_safe_paths(self):
        manifest_path = self.plugin_root / "plugin.json"
        self.assertTrue(manifest_path.is_file(), "Use the current portable root manifest format")
        manifest = install.read_json(manifest_path)
        self.assertEqual(manifest["name"], "canvas")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
        self.assertTrue(manifest.get("description"))
        for key in ("skills", "mcpServers"):
            value = manifest.get(key)
            paths = value if isinstance(value, list) else [value] if isinstance(value, str) else []
            for relative in paths:
                resolved = (self.plugin_root / relative).resolve()
                self.assertTrue(resolved.is_relative_to(self.plugin_root.resolve()), f"{key} escapes plugin")
                self.assertTrue(resolved.exists(), f"Missing packaged {key}: {relative}")

    def test_http_endpoint_is_exact_local_default_without_runtime_dependencies(self):
        configuration = install.read_json(self.plugin_root / "mcp.json")
        servers = configuration.get("mcpServers", configuration)
        self.assertEqual(set(servers), {"canvas"})
        server = servers["canvas"]
        self.assertEqual(server["url"], install.CANONICAL_ENDPOINT)
        self.assertIn(server.get("type", "http"), {"http", "streamable-http"})
        self.assertNotIn("command", server)
        self.assertNotIn("args", server)
        self.assertNotIn("headers", server)
        self.assertNotIn("env", server)
        self.assertNotIn("oauth", server)

    def test_skills_cover_workspace_reads_flow_edits_and_assistant_authoring(self):
        files = list((self.plugin_root / "skills").glob("*/SKILL.md"))
        self.assertTrue(files, "Canvas skill must be included")
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), f"Skill frontmatter missing: {path.name}")
            self.assertRegex(text, r"(?m)^name:\s*\S+")
            self.assertRegex(text, r"(?m)^description:\s*\S+")
        for name in install.TOOLS:
            self.assertIn(name, combined)
        self.assertIn("sessionId", combined)
        self.assertTrue((self.plugin_root / "skills/canvas/references/flow-editing.md").is_file())
        self.assertRegex(combined.lower(), r"(pagination|offset|page)")

    def test_release_contains_no_credentials_user_paths_or_generated_state(self):
        forbidden_names = {"auth.json", "config.toml", "installed_plugins.json", "known_marketplaces.json", ".env"}
        for path in self.plugin_root.rglob("*"):
            self.assertNotIn(path.name, forbidden_names)
            self.assertNotEqual(path.name, "node_modules")
            if path.is_file() and path.suffix in {".json", ".md", ".yaml", ".yml", ".toml"}:
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(?i)C:[\\/]+Users[\\/]+Kaan")
                self.assertNotRegex(text, r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")
                self.assertNotIn("51098", text, "A developer's old custom port must not ship as the default")


class FixtureContractChecks(unittest.TestCase):
    def rpc(self, endpoint, method, params=None, identifier=1):
        request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if identifier is not None:
            request["id"] = identifier
        body = json.dumps(request).encode("utf-8")
        with urlopen(Request(endpoint, body, {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}), timeout=3) as response:
            data = response.read()
            return response.status, json.loads(data) if data else None

    def test_real_http_handshake_discovery_and_notification(self):
        with install.McpFixture(0) as fixture:
            status, result = self.rpc(fixture.endpoint, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "unit", "version": "1"}})
            self.assertEqual(status, 200)
            self.assertEqual(result["result"]["protocolVersion"], "2025-11-25")
            self.assertEqual(self.rpc(fixture.endpoint, "notifications/initialized", identifier=None), (202, None))
            tools = self.rpc(fixture.endpoint, "tools/list")[1]["result"]["tools"]
            self.assertEqual({tool["name"] for tool in tools}, install.TOOLS)
            for tool in tools:
                self.assertEqual(tool["annotations"]["readOnlyHint"], tool["name"] in install.READ_TOOLS)
                self.assertEqual(tool["annotations"]["destructiveHint"], tool["name"] in install.DESTRUCTIVE_TOOLS)
                self.assertEqual(tool["annotations"]["idempotentHint"], tool["name"] in install.IDEMPOTENT_TOOLS)

    def test_assistant_create_inspect_and_export_cross_the_http_connection(self):
        with install.McpFixture(0) as fixture:
            def call(name, arguments):
                return self.rpc(fixture.endpoint, "tools/call", {"name": name, "arguments": arguments})[1]["result"]

            definition = {"id": "user.contract", "pluginId": "user.assistant.contract", "name": "Contract",
                          "description": "Test assistant", "instructions": "Translate supplied text.",
                          "contextPreamble": "Translate the ordered context."}
            created = call("canvas_create_assistant", {"definition": definition})
            self.assertFalse(created["isError"])
            self.assertEqual(install.structured(created)["id"], definition["id"])
            listed = install.structured(call("canvas_list_agents", {}))["agents"]
            self.assertIn(definition["id"], {item["id"] for item in listed})
            personal = next(item for item in listed if item["id"] == definition["id"])
            bundled = next(item for item in listed if item["id"] == "fixture-agent")
            self.assertEqual(personal["origin"], "personal")
            self.assertTrue(personal["canDelete"])
            self.assertEqual(bundled["origin"], "bundled")
            self.assertFalse(bundled["canDelete"])
            inspected = install.structured(call("canvas_get_assistant", {"assistantId": definition["id"]}))
            self.assertEqual(inspected["instructions"], definition["instructions"])
            self.assertEqual(inspected["version"], "1.0.0")
            duplicate = call("canvas_create_assistant", {"definition": definition})
            self.assertTrue(duplicate["isError"])
            first = install.structured(call("canvas_export_assistant", {"assistantId": definition["id"]}))
            second = install.structured(call("canvas_export_assistant", {"assistantId": definition["id"]}))
            self.assertTrue(first["filePath"].endswith(".flowast"))
            self.assertNotEqual(first["filePath"], second["filePath"])
            collision = call("canvas_export_assistant", {"assistantId": definition["id"], "destinationPath": first["filePath"]})
            self.assertTrue(collision["isError"])
            for tool in ("canvas_get_assistant", "canvas_export_assistant", "canvas_delete_assistant"):
                self.assertTrue(call(tool, {"assistantId": "missing"})["isError"])
            protected = call("canvas_delete_assistant", {"assistantId": "fixture-agent"})
            self.assertEqual(install.structured(protected)["error"]["code"], "assistant_protected")
            deleted = call("canvas_delete_assistant", {"assistantId": definition["id"]})
            self.assertFalse(deleted["isError"])
            self.assertEqual(install.structured(deleted), {"id": definition["id"], "name": definition["name"]})
            self.assertEqual(fixture.exports, {first["filePath"], second["filePath"]})
            listed = install.structured(call("canvas_list_agents", {}))["agents"]
            self.assertNotIn(definition["id"], {item["id"] for item in listed})
            repeated = call("canvas_delete_assistant", {"assistantId": definition["id"]})
            self.assertEqual(install.structured(repeated)["error"]["code"], "assistant_not_found")
            self.assertFalse(call("canvas_create_assistant", {"definition": definition})["isError"])

    def test_live_discovery_accepts_older_app_and_reports_only_advertised_annotations(self):
        class SevenToolServer:
            def call(self, method, params):
                return {"data": [{"name": "canvas", "tools": {
                    name: install.tool_definition(name) for name in install.PRE_DELETE_TOOLS
                }}]}

        result = install.discover_canvas(SevenToolServer(), require_current=False)
        self.assertNotIn("canvas_delete_assistant", result["tools"])
        with self.assertRaises(install.CheckFailure):
            install.discover_canvas(SevenToolServer())

    def test_projects_route_by_session_and_page_nodes_and_edges_independently(self):
        with install.McpFixture(0) as fixture:
            args = {"name": "canvas_get_project", "arguments": {"sessionId": install.PROJECT_B, "offset": 0, "limit": 1}}
            result = self.rpc(fixture.endpoint, "tools/call", args)[1]["result"]
            self.assertFalse(result["isError"])
            value = install.structured(result)
            self.assertEqual(value["project"]["sessionId"], install.PROJECT_B)
            self.assertEqual((len(value["nodes"]), len(value["edges"])), (1, 1))
            self.assertTrue(value["hasMoreNodes"] and value["hasMoreEdges"])
            args["arguments"]["offset"] = 1
            second = install.structured(self.rpc(fixture.endpoint, "tools/call", args)[1]["result"])
            self.assertNotEqual(value["nodes"], second["nodes"])
            self.assertFalse(second["hasMoreNodes"] or second["hasMoreEdges"])

    def test_invalid_and_stale_sessions_are_tool_errors(self):
        with install.McpFixture(0) as fixture:
            for session, expected in (("invalid", "invalid_argument"), ("33333333-3333-4333-8333-333333333333", "project_not_found")):
                result = self.rpc(fixture.endpoint, "tools/call", {"name": "canvas_get_project", "arguments": {"sessionId": session}})[1]["result"]
                self.assertTrue(result["isError"])
                self.assertEqual(install.structured(result)["error"]["code"], expected)

    def test_flow_transaction_round_trips_ids_text_positions_and_exact_retry(self):
        with install.McpFixture(0) as fixture:
            def call(name, arguments):
                return self.rpc(fixture.endpoint, "tools/call", {"name": name, "arguments": arguments})[1]["result"]

            before = install.structured(call("canvas_get_project", {"sessionId": install.PROJECT_A}))
            flow = {"requestId": str(uuid.uuid4()), "expectedRevision": before["project"]["revision"],
                    "nodes": [{"key": "input", "kind": "text", "x": 300, "y": 200, "text": "Test source"},
                              {"key": "assistant", "kind": "assistant", "x": 650, "y": 200, "assistantId": "fixture-agent"},
                              {"key": "empty", "kind": "image", "x": 1000, "y": 200}],
                    "connections": [{"source": "input", "target": "assistant", "targetPortId": "context"}]}
            arguments = {"sessionId": install.PROJECT_A, "edit": flow}
            created = call("canvas_edit_project", arguments)
            self.assertFalse(created["isError"])
            receipt = install.structured(created)
            self.assertEqual(receipt["requestId"], flow["requestId"])
            self.assertEqual(receipt["revision"], 8)
            self.assertTrue(receipt["changed"])
            self.assertFalse(receipt["replayed"])
            ids = {item["key"]: item["node"]["id"] for item in receipt["nodes"]}
            self.assertEqual(set(ids), {"input", "assistant", "empty"})
            self.assertEqual(receipt["edges"][0]["sourceId"], ids["input"])
            self.assertEqual(receipt["edges"][0]["targetId"], ids["assistant"])
            self.assertEqual(next(item["node"] for item in receipt["nodes"] if item["key"] == "assistant")["outputPorts"][0]["id"], "context")
            self.assertEqual(next(item["node"] for item in receipt["nodes"] if item["key"] == "input")["outputPorts"][0]["id"], "value")
            replayed = install.structured(call("canvas_edit_project", arguments))
            self.assertTrue(replayed["replayed"])
            self.assertEqual(replayed["nodes"], receipt["nodes"])
            after = install.structured(call("canvas_get_project", {"sessionId": install.PROJECT_A}))
            self.assertEqual(len(after["nodes"]), len(before["nodes"]) + 3)
            update = {"requestId": str(uuid.uuid4()), "expectedRevision": 8,
                      "textUpdates": [{"nodeId": ids["input"], "text": "New text"}],
                      "moves": [{"nodeId": ids["assistant"], "x": 700, "y": 220}]}
            result = call("canvas_edit_project", {"sessionId": install.PROJECT_A, "edit": update})
            self.assertFalse(result["isError"])
            self.assertEqual(install.structured(result)["revision"], 9)
            after = install.structured(call("canvas_get_project", {"sessionId": install.PROJECT_A}))
            self.assertEqual(next(item for item in after["nodes"] if item["id"] == ids["input"])["text"], "New text")
            self.assertEqual(next(item for item in after["nodes"] if item["id"] == ids["assistant"])["x"], 700)

    def test_flow_conflicts_bad_connections_and_inactive_sessions_leave_graph_intact(self):
        with install.McpFixture(0) as fixture:
            def call(edit, session=install.PROJECT_A):
                return self.rpc(fixture.endpoint, "tools/call", {"name": "canvas_edit_project", "arguments": {"sessionId": session, "edit": edit}})[1]["result"]

            original = copy.deepcopy(fixture.projects)
            def edit(**changes):
                return {"requestId": str(uuid.uuid4()), "expectedRevision": 7, "nodes": [{"key": "default", "kind": "text", "x": 0, "y": 0}], **changes}

            invalid = edit(nodes=[{"key": "input", "kind": "text", "x": 0, "y": 0}],
                           connections=[{"source": "input", "target": str(uuid.uuid4())}])
            cases = [(invalid, "node_not_found", install.PROJECT_A),
                     (edit(expectedRevision=6), "revision_conflict", install.PROJECT_A),
                     (edit(), "project_not_active", install.PROJECT_B),
                     (edit(nodes=[{"key": "missing", "kind": "assistant", "assistantId": "missing", "x": 0, "y": 0}]), "agent_unavailable", install.PROJECT_A),
                     (edit(nodes=[{"key": "input", "kind": "text", "x": 0, "y": 0}],
                           connections=[{"source": "input", "target": "input"}]), "invalid_connection", install.PROJECT_A)]
            for payload, code, session in cases:
                with self.subTest(code=code):
                    result = call(payload, session)
                    self.assertTrue(result["isError"])
                    self.assertEqual(install.structured(result)["error"]["code"], code)
                    self.assertEqual(fixture.projects, original)
            success = edit(nodes=[{"key": "first", "kind": "text", "x": 0, "y": 0}])
            self.assertFalse(call(success)["isError"])
            committed = copy.deepcopy(fixture.projects)
            conflict = {**success, "moves": [{"nodeId": str(uuid.uuid4()), "x": 10, "y": 20}]}
            result = call(conflict)
            self.assertEqual(install.structured(result)["error"]["code"], "request_conflict")
            self.assertEqual(fixture.projects, committed)

    def test_flow_tool_schema_advertises_typed_batch_and_retry_annotations(self):
        definition = install.tool_definition("canvas_edit_project")
        self.assertEqual(definition["annotations"], {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
        schema = definition["inputSchema"]
        self.assertEqual(schema["required"], ["sessionId", "edit"])
        edit = schema["properties"]["edit"]
        self.assertEqual(edit["required"], ["requestId", "expectedRevision"])
        self.assertEqual(set(edit["properties"]), {"requestId", "expectedRevision", "nodes", "connections", "textUpdates", "moves"})
        self.assertEqual(edit["properties"]["nodes"]["items"]["properties"]["kind"]["enum"], ["text", "assistant", "image", "video"])
        for field, maximum in (("nodes", 100), ("connections", 200), ("textUpdates", 100), ("moves", 100)):
            self.assertEqual(edit["properties"][field]["maxItems"], maximum)

    def test_browser_origin_is_rejected(self):
        with install.McpFixture(0) as fixture:
            request = Request(fixture.endpoint, b"{}", {"Content-Type": "application/json", "Origin": "https://untrusted.example"})
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 403)

    def test_diagnostics_reject_every_endpoint_except_the_installed_bundle(self):
        install.validate_endpoint("http://127.0.0.1:47321/mcp")
        for endpoint in ("http://127.0.0.1:51098/mcp", "https://example.com/mcp", "http://0.0.0.0:47321/mcp",
                         "http://localhost:47321/mcp", "http://127.0.0.1:47321/mcp/",
                         "http://127.0.0.1:47321/mcp?token=secret",
                         "http://user:secret@127.0.0.1:47321/mcp"):
            with self.subTest(endpoint=endpoint), self.assertRaises(install.CheckFailure):
                install.validate_endpoint(endpoint)

    def test_wrong_port_fails_before_install_or_configuration_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "artifacts"
            with patch.object(install, "run_cli") as cli, patch.object(install.subprocess, "run") as process:
                with self.assertRaises(install.CheckFailure):
                    install.main(["--endpoint", "http://127.0.0.1:51098/mcp", "--artifacts", str(artifacts)])
                cli.assert_not_called()
                process.assert_not_called()
                self.assertFalse(artifacts.exists(), "Invalid endpoint must not create installation state")


if __name__ == "__main__":
    unittest.main()
