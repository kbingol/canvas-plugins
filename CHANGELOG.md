# Changelog

## 1.5.0

- Add requested assistant execution with `canvas_run_node`, `canvas_get_run` and `canvas_cancel_run` through Canvas's existing project-owned Harness.
- Sequence a flow by observing upstream success and fresh project revisions before starting downstream nodes.
- Preserve request replay, durable recovery, headless missing-input handling and explicit confirmation for uncertain prior execution.
- Cancel only the operation owned by a request; completed receipts cannot stop later work on the same node.
- Extend isolated HTTP diagnostics to twelve tools with provider-aware execution annotations and synthetic jobs; no paid model runs are used for validation.

## 1.4.0

- Add flow authoring and editing through `canvas_edit_project` in the active open Canvas project.
- Create text/assistant/empty-media nodes, connect typed ports, update editable text inputs and move nodes in one validated transaction.
- Use expected revisions and request receipts to reject stale edits and replay exact retries without duplicates.
- Extend isolated HTTP diagnostics to nine tools with destructive and idempotent graph-edit annotations; live diagnostics remain read-only.
- Keep assistant execution, media generation, asset imports and node/wire removal outside this tool.

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
