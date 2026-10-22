# Changelog

## 1.3.0

- Add user-requested personal assistant deletion through `canvas_delete_assistant`; app-provided bundled assistants are protected.
- Describe installation provenance (`origin`) and deletion permission (`canDelete`), including MCP-created personal packages.
- Preserve project nodes, saved outputs, started jobs and exported archives when removing an installed personal package.
- Extend isolated diagnostics to eight tools with the destructive deletion annotation; live diagnostics remain read-only and report support without requiring a newer app to have already restarted.

## 1.2.0

- Add assistant authoring guidance for `canvas_get_assistant`, `canvas_create_assistant`, and `canvas_export_assistant` from the updated Canvas MCP server.
- Create validated packages in Canvas's local user assistant folder with immediate discovery; export installed packages as `.flowast` files without overwriting existing files.
- Add a focused authoring skill with typed-definition examples, optional budgets, acceptance rules, and host-tool constraints.
- Advertise assistant-package writes while preserving read-only project access and the existing fixed local connection.
- Extend isolated connection diagnostics to discover seven tools and distinguish read and write annotations. Only the in-memory fixture exercises writes; live diagnostics remain read-only.

## 1.1.0

- Canvas and its plugin share one fixed local HTTP endpoint with no manual port selection or client configuration.
- Keep a single plugin-owned HTTP MCP connection; remove the direct-registration workaround from setup.
- Installation diagnostics reject endpoint overrides and verify the actual bundled server, plus unavailable/reconnect behavior.
- Requires the updated Canvas version using the fixed plugin endpoint.

## 1.0.0

- Initial Canvas plugin and Git marketplace catalog.
- Direct connection to Canvas's local Streamable HTTP MCP endpoint.
- Read-only workspace guidance.
