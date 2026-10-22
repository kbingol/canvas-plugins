# Architecture

This repository distributes a Git-backed marketplace and a Canvas plugin. It does not contain another Canvas server or project store. The installed plugin connects directly to the HTTP MCP server inside the running Canvas desktop application.

```text
Codex on the user's computer
    → http://127.0.0.1:47321/mcp
    → running Canvas workspace
```

## Package and distribution

The package uses portable root `plugin.json` and `mcp.json` files, with the published Agent Plugins 1.0.0 schema identifiers. Skills live under the plugin's `skills/` directory. OpenAI-specific interface metadata belongs in `extensions.com.openai`. This follows [OpenAI's manual package pattern](https://developers.openai.com/plugins/build/plugins#create-a-plugin-manually) and [bundled MCP configuration](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks).

The catalog lives at `.agents/plugins/marketplace.json`. Its stable marketplace name is `canvas-plugins`, and its plugin name is `canvas`. The local source path is relative to the marketplace repository root. Git-backed marketplace registration and explicit refresh use the documented [marketplace lifecycle commands](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli). This Git catalog is independent of OpenAI's public directory; inclusion in that directory is a separate submission process.

The package contains no launch hook or transport bridge. Installing it does not launch Canvas, enable its MCP preference, or rewrite existing application or client settings. Canvas must already be running with MCP enabled. Installation changes apply to a new local session, as described in [OpenAI's plugin usage documentation](https://learn.chatgpt.com/docs/plugins).

## Endpoint and compatibility

The manifest uses `type: "streamable-http"` and the literal URL `http://127.0.0.1:47321/mcp`. Canvas uses that same fixed address, defined in the [Canvas application contract](https://github.com/kbingol/canvas/blob/main/src/Canvas.Application/Automation/McpConnectionContracts.cs).

Canvas exposes one fixed loopback MCP endpoint. Installation needs no direct MCP registration, configuration edits, URL interpolation, discovery command, lifecycle hook, or transport bridge. The application must be updated and running with MCP enabled; installing the plugin cannot update a running application binary.

OpenAI's [bundled MCP configuration](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks) supports the literal HTTP URL used here. Its [plugin server policy](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) controls enablement and tool policy, not a per-user replacement URL. Keeping the stable endpoint in the application avoids relying on an undocumented plugin override.

Canvas exposes six read-only tools: `canvas_get_status`, `canvas_list_projects`, `canvas_get_project`, `canvas_list_agents`, `canvas_get_assistant` and `canvas_get_run`. The first four retain their workspace contract. Assistant inspection returns a package's complete reusable authoring definition; native functions need not have one. Run inspection observes an existing owned execution receipt without starting a model.

Three write tools manage assistant packages: `canvas_create_assistant` validates a typed definition and atomically installs it in the local user assistant folder, and `canvas_export_assistant` writes an installed package as a `.flowast` file. Neither overwrites an existing destination. `canvas_delete_assistant` removes only personal packages on user request and is annotated destructive; bundled packages are protected. `canvas_list_agents` reports installation-root provenance as `origin` and `canDelete`, including personal packages created over MCP. Deletion preserves project nodes, saved outputs, started jobs and exported archives. Canvas owns validation, assigned package paths, live catalog publication, and archive creation; the plugin carries skills and connects to these tools dynamically, without a second package store or local executable bridge. Creating a package does not execute the assistant, edit a project, or invoke a model. The focused `assistant-authoring` skill documents this boundary and routes detailed fields to its definition reference.

A fourth write tool, `canvas_edit_project`, applies one validated transaction to the active open project. A batch can add text/assistant/empty-media nodes, connect nodes through declared typed ports, update editable text inputs, and move existing nodes. The app resolves the live session on its UI thread and uses its normal project editing and autosave path; the plugin does not write `.flow` files or own a second graph model. It does not remove nodes or wires, replace occupied inputs, import media, run assistants, or generate outputs.

Every edit carries a non-empty GUID `requestId` and the observed `expectedRevision`. Canvas validates the entire batch before applying it, increments revision once when changed, and rejects stale revisions. The open session retains its last 128 successful request receipts. Repeating a retained request and payload returns its receipt without adding duplicates; changing the payload of an existing request ID is a conflict. This tool is annotated destructive because it can alter existing content and idempotent because exact retries are receipt-backed. The workspace skill routes request fields, limits and error handling to its flow-editing reference.

Execution adds `canvas_run_node` and `canvas_cancel_run`. Starting one existing assistant delegates to Canvas's normal project-owned Harness lifecycle, configured provider/tools, durable recovery and cancellation paths. The plugin does not call AI providers or implement a second execution engine. The start returns an immediate receipt; `canvas_get_run` reports progress and a terminal outcome. To run a chain, the client model observes upstream `succeeded`, rereads current graph results/revision, and chooses the next dependent node. Other terminal outcomes stop that sequence. Editing a graph or installing a package alone never starts execution.

Each start includes `requestId` and `expectedRevision`; exact node/request retries reuse the same owned operation. Completed receipts are detached historical snapshots, with 128 completed records retained per open session and up to eight active records that are never evicted. Admitted work survives HTTP disconnects; entered execution survives tab switches, while pending preparation still obeys native admission guards. Explicit cancellation targets only its owned receipt and cannot recall an already submitted external provider request. A previous request with uncertain execution requires separate explicit user authorization before `confirmNewRun: true`; a usable saved checkpoint takes its existing recovery path instead. Missing model/account input is reported without opening configuration or automating authentication.

Run start is destructive, idempotent and open-world because the configured engine can call external providers and consume quota. Run status is read-only and closed-world; cancellation is a destructive idempotent closed-world operation. Known generated output cards can predate the current run, so their presence is not a substitute for its `succeeded` receipt.

Project session IDs, paging and truncation still apply to workspace reads. The [Canvas MCP contract and access boundary](https://github.com/kbingol/canvas/blob/main/docs/mcp.md) define the server capabilities. Version 1.5.0 requires the updated application for node execution; flow editing was introduced in 1.4.0 and personal-package deletion in 1.3.0. Supported reads remain available when an older running app lacks newer tools. Updating the plugin cannot update the running app.

The listing's `Read` and `Write` capability labels describe the integration, following the [official inline manifest example](https://developers.openai.com/plugins/build/plugins#create-a-plugin-manually); they are not an additional permission mechanism. Tool annotations distinguish read operations, package writes, destructive deletion and receipt-backed project edits.

The HTTP listener is local and unauthenticated. Canvas applies loopback, Host and Origin checks, which do not authenticate other local processes. The package adds no new credential scheme. Reading local project content through MCP still sends tool results to the configured AI client; the plugin does not promise that model processing stays on the device.

## Verification expectations

Package checks validate JSON schemas, catalog paths, stable names and versions, local-execution metadata, and the exact loopback endpoint. Installation checks use an isolated Codex home so existing configuration and installed caches are untouched. A meaningful runtime check must initialize the installed plugin's HTTP connection and call its advertised tools against an actual Canvas-compatible server; parsing the manifest alone is insufficient.

For a release, also verify a fresh install from the published Git source, a new session, useful empty-workspace results, live project reads, and graceful failure while Canvas is closed or MCP is off. The installation fixture uses the exact packaged address; separate production-host and live checks must verify the real application at that address. See [release validation](validation.md) for the 1.5.0 results, unverified fixed-endpoint checks, and reproduction commands.
