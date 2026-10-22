# Release validation

## Environment and results

Release 1.0.0 was validated on Windows with the installed **Codex CLI 0.163.0**. The package uses the documented portable layout, not an untested rename of a legacy manifest.

- Upstream Agent Plugins 1.0.0 JSON schemas: passed for both manifests.
- Packaged skill frontmatter: passed the Codex skill-creator validator.
- Package/HTTP contract and release archive tests: 12 passed.
- Real Codex marketplace registration, installation, skill discovery, MCP discovery, tool calls and removal: passed in isolated homes.
- All four read-only tools called through the real client against an explicit deterministic HTTP fixture at the package's exact default endpoint.
- Duplicate project titles, session routing, independent node/edge paging and invalid/stale sessions: passed.
- Endpoint unavailable followed by a fresh successful connection: passed.
- Nondefault-port compatibility: passed with a real direct MCP registration and only the bundled server disabled.
- A separate run against a running Canvas desktop instance on its existing nondefault port verified status, project listing, agent listing and project snapshot calls. That run used the documented direct-registration fallback; it is not evidence that the unmodified bundled URL points at a nondefault port.
- User configuration hashes were unchanged. Test homes contained no copied account credentials. No model turn or paid generation was started.
- Two independent archive builds produced identical bytes and SHA256 hashes.

The graphical menu flow is documented from the supported UI; clicks in the ChatGPT desktop app were not automated. The actual installed client loader and MCP engine were tested through its CLI and app-server diagnostic interface. No inference-based behavioral evaluation of the natural-language skills is claimed.

CI repeats the package checks and the actual Codex installation tests with pinned Codex 0.163.0. Release validation also uses a fresh home fetching this public Git repository; inspect the corresponding CI run for the current commit rather than treating this document as future CI status.

## Reproduce

These are maintainer commands, not requirements for people installing the plugin:

```sh
python -m pip install -r requirements-dev.txt
python scripts/validate.py
python -m unittest discover -s tests -v
python scripts/package.py
python scripts/test_install.py
python scripts/test_install.py --fixture-port 51098 --artifacts artifacts/custom-port
python scripts/test_install.py --repository https://github.com/kbingol/canvas-plugins --artifacts artifacts/git-install
```

The fixture test refuses to replace an occupied listener. If Canvas is running on a selected port, either choose a free fixture port or use the explicit live mode:

```sh
python scripts/test_install.py --endpoint http://127.0.0.1:51098/mcp --artifacts artifacts/live
```

Live mode performs read-only calls and records counts and installation evidence, not project contents. All lifecycle writes are confined to disposable test homes. `app-server` is a diagnostic client in the tests; experimental plugin mutation APIs are not shipped as an installer.
