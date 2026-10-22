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

Canvas currently exposes four read-only tools: `canvas_get_status`, `canvas_list_projects`, `canvas_get_project`, and `canvas_list_agents`. The plugin skill must respect project session IDs, paging and truncation. It must not promise editing, execution or model generation. The [Canvas MCP contract and access boundary](https://github.com/kbingol/canvas/blob/main/docs/mcp.md) define those capabilities.

The HTTP listener is local and unauthenticated. Canvas applies loopback, Host and Origin checks, which do not authenticate other local processes. The package adds no new credential scheme. Reading local project content through MCP still sends tool results to the configured AI client; the plugin does not promise that model processing stays on the device.

## Verification expectations

Package checks validate JSON schemas, catalog paths, stable names and versions, local-execution metadata, and the exact loopback endpoint. Installation checks use an isolated Codex home so existing configuration and installed caches are untouched. A meaningful runtime check must initialize the installed plugin's HTTP connection and call its advertised tools against an actual Canvas-compatible server; parsing the manifest alone is insufficient.

For a release, also verify a fresh install from the published Git source, a new session, useful empty-workspace results, live project reads, and graceful failure while Canvas is closed or MCP is off. The installation fixture uses the exact packaged address; Canvas's own production-host tests verify that the real application serves it. See [release validation](validation.md) for checks and reproduction commands.
