# Release validation

## Validation scope

Version 1.1.0 uses one fixed endpoint shared with Canvas. The actual installed plugin must own the connection to `http://127.0.0.1:47321/mcp`; a separate direct MCP registration is never accepted as proof that the package works.

The package uses portable root manifests and the vendored Agent Plugins 1.0.0 JSON schemas. Validation covers schema and skill frontmatter, package boundaries, reproducible archives, and a real Codex CLI installation in disposable homes. The client test discovers both packaged skills and all four tools, calls the read-only tools, checks session routing, pagination and errors, and verifies offline/reconnect behavior without a model turn.

The fixture uses the exact packaged URL. No global MCP registration, disabled bundled server, or URL override is introduced. A regression test rejects a different endpoint before installation or any CLI/configuration operation.

The fixture proves client installation and connection ownership. Canvas's own production-host tests and a separate live run must verify the real application's fixed endpoint. A running Canvas binary is not updated by installing this plugin.

The graphical menu clicks are not automated by these tests. The actual installed loader and MCP engine are exercised through the CLI and app-server diagnostic interface. No inference-based behavioral evaluation of the natural-language skills is claimed. Local reports record the tested Codex version; CI pins Codex 0.163.0. Published Git installation and CI status must be checked for the specific released commit rather than inferred from a local run.

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

Live mode accepts only the packaged endpoint. Supplying another URL fails before installation rather than creating a workaround registration. Calls are read-only, and reports contain installation evidence and counts rather than project contents. All lifecycle writes are confined to disposable test homes. User configuration is hashed before and after the run; account credentials are neither copied nor requested. No model listing, inference, or paid generation is started. `app-server` is only a diagnostic client; experimental plugin mutation APIs are not shipped as an installer.
