# Release validation

## Validation scope

Version 1.4.0 uses one fixed endpoint shared with Canvas. The actual installed plugin must own the connection to `http://127.0.0.1:47321/mcp`; a separate direct MCP registration is never accepted as proof that the package works.

The package uses portable root manifests and the vendored Agent Plugins 1.0.0 JSON schemas. The validation scripts cover schema and skill frontmatter, package boundaries, reproducible archives, and Codex CLI installation in disposable homes. The installation diagnostic is designed to discover three packaged skills and all nine tools, check read/write/destructive annotations, session routing, pagination and errors, and verify offline/reconnect behavior without a model turn. Its assistant creation, inspection, duplicate rejection, provenance, export, personal deletion and bundled protection calls affect only in-memory fixture state. Flow diagnostics additionally exercise atomic node/wire creation, exact request replay, payload and revision conflicts, rollback on invalid links, and existing text/position updates. These fixture checks exercise the installed connection, not the real Canvas package or graph implementation.

The fixture uses the exact packaged URL. No global MCP registration, disabled bundled server, or URL override is introduced. A regression test rejects a different endpoint before installation or any CLI/configuration operation.

A successful complete installation diagnostic provides evidence of client installation and connection ownership. Canvas's own production-host tests and a separate live run must verify the real application's fixed endpoint. A running Canvas binary is not updated by installing this plugin.

The graphical menu clicks are not automated by these tests. The installation diagnostic uses the actual installed loader and MCP engine through the CLI and app-server diagnostic interface. No inference-based behavioral evaluation of the natural-language skills is claimed. Completed local reports record the tested Codex version; CI pins Codex 0.163.0. Published Git installation and CI status must be checked for the specific released commit rather than inferred from a local run.

## Version 1.4.0 validation result

Package schema validation, all 18 Python unit/reproducibility checks, archive creation, and validation of all three skills passed. The Python checks include a real HTTP handshake with the nine-tool in-memory fixture on ephemeral ports, the graph edit schema and annotations, atomic flow creation, new-node alias resolution, text/position round trips, exact retry replay, stale-revision rejection, changed-payload conflicts, and failed-edit isolation. They also retain assistant package management and compatibility with older apps.

The separate Canvas implementation passed its full portable suite, including 33 graph-edit and 86 live-workspace edit assertions; 190 HTTP MCP assertions on ephemeral ports; a native build with no warnings or errors; and 24 assertions in hidden WinUI windows. Native checks rendered the real flow, exercised revision/retry/cancellation and editor/modal/tab admission, observed natural autosave, and reopened the saved portable project. These application checks do not establish an installed Codex plugin connection to the fixed endpoint.

No live project was edited and no assistant or model was executed during these package checks. The full installed-Codex nine-tool fixture handshake, offline/reconnect sequence, successful live fixed-endpoint run and published Git/CI installation are **not verified for 1.4.0** by this local package validation. The application implementation requires its separate production-host and native tests; Python fixture success does not substitute for those checks.

## Version 1.3.0 validation result

Package schema validation, all 15 Python unit/reproducibility checks, and validation of all three skills passed. The Python checks include a real HTTP handshake with the eight-tool in-memory fixture on an ephemeral port, provenance, destructive annotations, personal deletion, bundled protection and compatibility with an older seven-tool app.

The separate updated Canvas implementation passed 158 real HTTP MCP assertions on ephemeral ports (`--ephemeral-only`), the portable test suite, a native build with no warnings or errors, and 85 assertions in hidden native windows. These results validate the application implementation; they do not establish that a published plugin was successfully exercised against the user's fixed endpoint.

The isolated Codex CLI installation reached plugin loading, but the MCP handshake against `127.0.0.1:47321` could not complete; the fixture also could not bind that fixed port (`WinError 10013`). Therefore the full installed-plugin eight-tool handshake, its offline/reconnect sequence, and a successful live fixed-endpoint run are **not verified for 1.3.0**. No existing Canvas process was stopped or replaced to claim the port. Run the installation diagnostic below in an environment where that port is available, then check the published Git commit and its CI separately.

## Reproduce

These are maintainer commands, not requirements for users installing the plugin:

```sh
python -m pip install -r requirements-dev.txt
python scripts/validate.py
python -m unittest discover -s tests -v
python scripts/package.py
python scripts/test_install.py
python scripts/test_install.py --repository https://github.com/kbingol/canvas-plugins --artifacts artifacts/git-install
```

The fixture refuses to replace an occupied listener. Run the fixture checks in an environment where its selected ports are free. To verify the updated running Canvas app instead, use live mode:

```sh
python scripts/test_install.py --endpoint http://127.0.0.1:47321/mcp --artifacts artifacts/live
```

Live mode accepts only the packaged endpoint. Supplying another URL fails before installation rather than creating a workaround registration. Calls against the real Canvas app are read-only, and reports contain installation evidence and counts rather than project contents. Live discovery verifies the existing authoring tools and reports whether deletion and flow editing are advertised; an older seven-tool app remains a valid connection while awaiting restart/update. It never edits a project or creates, exports or deletes an assistant. All diagnostic lifecycle writes are confined to disposable test homes. User configuration is hashed before and after the run; account credentials are neither copied nor requested. No model listing, inference, or paid generation is started. `app-server` is only a diagnostic client; experimental plugin mutation APIs are not shipped as an installer.
