---
name: setup
description: Set up or diagnose this plugin's connection to the local Canvas desktop app, including an existing profile that uses a custom HTTP MCP address.
---

# Set up Canvas

Connect to the Canvas app running on the same Windows computer. Use the user's language. This package only reads open projects and agent definitions; it cannot edit projects or run agents. No account sign-in, API key, tunnel, or additional local server is needed for the default connection.

## Default connection

The packaged endpoint is `http://127.0.0.1:47321/mcp`.

1. Try the configured Canvas server's `canvas_get_status` tool.
2. If unavailable, guide the user to open Canvas, enable MCP in Settings, and keep Canvas running. Do not start an application or change its profile automatically.
3. Compare the address shown in Canvas with the packaged endpoint. If it matches, restart the MCP connection or start a new local conversation after Canvas is ready, then retry once.
4. Call `canvas_list_projects` after status succeeds. An empty list is a working connection with no open projects. Do not read project contents merely to check installation.

Report success only after a tool returns from the real Canvas instance. If the host is executing remotely, switch to a local desktop conversation; its `127.0.0.1` cannot reach the user's computer from a cloud runtime.

## Existing custom-port profile

Preserve the user's existing Canvas profile and the address it displays. The package's endpoint is fixed; do not silently change Canvas, rewrite installed cache files, or add a second failing connection alongside the first.

Use the client's supported direct MCP registration for that address:

- In the desktop client's MCP settings, add a Streamable HTTP server named `canvas-local` with the exact URL displayed in Canvas. If available, the equivalent Codex CLI command is `codex mcp add canvas-local --url "URL_SHOWN_IN_CANVAS"`, replacing the quoted example with the real URL.
- Disable only this package's bundled server through the supported user configuration, preserving the plugin and its skills:

```toml
[plugins."canvas@canvas-plugins".mcp_servers.canvas]
enabled = false
```

- Keep other MCP servers and settings unchanged. Use an existing suitable `canvas-local` registration if present instead of duplicating it. Explain any necessary user configuration change before applying it under the user's setup request.
- Restart the connection or begin a new local conversation. Verify `canvas_get_status` and `canvas_list_projects` on the directly registered server, not the disabled bundled server.

This fallback uses the same local HTTP protocol and the same read-only tools. When returning to the default endpoint later, remove the redundant direct registration and re-enable the bundled server through supported client settings.

## Connection limits

If the address is not a loopback address, stop and explain that this package is intended for a local Canvas instance. Do not expose the server to the network, install a tunnel, weaken client permissions, or introduce credentials to make a local connection succeed.

Return the observed connection status and the next concrete action when a check fails. Do not describe an unavailable server as installed and working.
