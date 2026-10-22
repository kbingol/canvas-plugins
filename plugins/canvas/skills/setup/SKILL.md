---
name: setup
description: Check or diagnose this plugin's connection to the local Canvas desktop app using its fixed HTTP MCP endpoint.
---

# Connect Canvas

Use the user's language. Canvas must run on the same Windows computer with MCP enabled. This plugin reads open projects and agent definitions, edits flows in the active project, and creates, exports or deletes personal assistant packages with the updated Canvas app. It cannot run assistants or generate media. No account sign-in, API key, tunnel, additional local server, or manual client configuration is needed.

Canvas and the bundled server both use `http://127.0.0.1:47321/mcp`. The user does not need to choose or enter an address.

1. Call the installed plugin's `canvas_get_status` tool.
2. If unavailable, guide the user to open the updated Canvas app, enable MCP in Settings, and keep it running. If Canvas was updated, restart it so the updated binary serves the fixed endpoint.
3. Once Canvas is ready, restart the client's MCP connection or begin a new local conversation, then retry once. If Canvas reports a port conflict, report that concrete error; do not select another port or connect to an unrelated listener.
4. After status succeeds, call `canvas_list_projects`. An empty list is a working connection with no open projects. Do not read project contents merely to check installation.

Flow editing needs `canvas_edit_project`; assistant authoring additionally needs `canvas_get_assistant`, `canvas_create_assistant`, and `canvas_export_assistant`; personal-package deletion additionally needs `canvas_delete_assistant`. If they are missing, explain that the Canvas app must be updated and its MCP connection refreshed. Do not test setup by editing a project or creating, exporting or deleting a package. Updating this plugin alone cannot change the running application's capabilities.

Report success only after a tool returns from the real Canvas instance. If execution is remote, use a local desktop conversation; a cloud runtime's `127.0.0.1` cannot reach the user's computer.

Keep the plugin-owned server enabled. Do not add a separate direct MCP registration, rewrite client configuration, select another port, or edit the installed plugin cache as a connection workaround.

If connection still fails, return the observed status and next concrete action. Do not expose Canvas to the network, install a tunnel, weaken permissions, or invent credentials to make this local connection succeed.
