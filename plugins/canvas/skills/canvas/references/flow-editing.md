# Edit an open Canvas flow

`canvas_edit_project(sessionId, edit)` applies one validated transaction to the active open project. It does not run agents or import media. Inspect the project and `canvas_list_agents` first so positions, IDs, connections and assistant ports come from the real workspace. Use the returned project revision, not a guessed revision or a counter from another session.

## Request

`edit` contains:

| Field | Meaning |
| --- | --- |
| `requestId` | New non-empty GUID for this transaction. Keep it with the exact payload until the result is known. |
| `expectedRevision` | Required integer revision returned by `canvas_get_project`. |
| `nodes` | Optional new nodes: `{key, kind, x, y, text?, assistantId?}`. |
| `connections` | Optional wires: `{source, target, sourcePortId?, targetPortId?}`. |
| `textUpdates` | Optional changes to existing unconnected text input nodes: `{nodeId, text}`. |
| `moves` | Optional existing-node positions: `{nodeId, x, y}`. |

New `key` values match `[a-zA-Z][a-zA-Z0-9_-]{0,63}` and must be unique within the request. They are local aliases, not persisted node IDs. `kind` is `text`, `assistant`, `image` or `video`. Use `assistantId` from `canvas_list_agents` for an assistant; image/video nodes start empty. Coordinates are finite canvas coordinates with absolute values at most 10,000,000. Only text nodes accept `text`; only assistant nodes accept `assistantId`. Include at least one operation.

Connection endpoints are new-node keys or existing node GUID strings. New assistant ports come from `canvas_list_agents`; existing node snapshots expose actual `inputPorts` and `outputPorts` as `{id, name, kind, required, multiple, maxItems}` arrays. Read those arrays for currently published item output IDs when connecting an existing assistant to text/image/video result cards. Do not construct item IDs yourself. Text/media value ports can be omitted when the compatible connection is unambiguous. Use the actual declared Context output and Context input for assistant chains. Item outputs exist only when the assistant has published those items; do not invent numbered output ports or generated output nodes before execution. Existing output nodes can be connected using their returned IDs and actual ports.

The server validates the complete edit before applying it. It will not silently replace an occupied input, accept incompatible typed ports, edit generated/connected text, or modify a project blocked by a current native interaction. Existing nodes and connections remain unless changed by the supported operations.

Limits per transaction: 100 new nodes, 200 connections, 100 text updates and 100 moves, with at most 500 operations total. Individual text is at most 65,536 UTF-16 code units and total request text is at most 262,144 UTF-16 code units. Split larger work into deliberate transactions and use each returned revision for the next.

## Example: idea → prompt assistant → image assistant

1. Select the active project from `canvas_list_projects`, then read its graph and revision with `canvas_get_project`.
2. Inspect `canvas_list_agents`. Identify the installed Prompt Assistant and Image Assistant IDs and their declared Context ports. The list includes disabled definitions and has no enabled flag. A missing definition can be detected here; `agent_unavailable` during editing can also mean the user disabled it. Explain the cause and let the user enable it in Canvas Settings, or use another installed assistant when that fits their request.
3. Choose a clear position beside existing nodes. Submit one edit such as the template below, replacing placeholders with the observed IDs, revision, ports and a fresh GUID:

```json
{
  "sessionId": "<active session GUID>",
  "edit": {
    "requestId": "<new request GUID>",
    "expectedRevision": 12,
    "nodes": [
      {"key": "idea", "kind": "text", "x": 0, "y": 0, "text": "A quiet library lit by the morning sun."},
      {"key": "prompt", "kind": "assistant", "x": 360, "y": 0, "assistantId": "<observed prompt assistant ID>"},
      {"key": "image", "kind": "assistant", "x": 720, "y": 0, "assistantId": "<observed image assistant ID>"}
    ],
    "connections": [
      {"source": "idea", "target": "prompt", "targetPortId": "<prompt Context input port>"},
      {"source": "prompt", "sourcePortId": "<prompt Context output port>", "target": "image", "targetPortId": "<image Context input port>"}
    ]
  }
}
```

The result returns `sessionId`, `requestId`, `revision`, new `nodes` as `{key, node}` entries, `edges`, `changed` and `replayed`. Use returned real IDs for later changes. Verify the resulting graph with `canvas_get_project`; tell the user that the flow is connected and ready to run in Canvas. Drawing it has not produced an image.

## Revisions, retries and errors

The transaction either applies fully or leaves the graph unchanged. It increments revision once when changed and uses normal project autosave. A failed edit does not partially add nodes or wires.

- `revision_conflict`: reread the project, reassess positions/connections against user changes, and submit a new transaction with a new `requestId` and current revision. Do not reuse the old ID with an altered payload.
- If a response is lost, retry the **same `requestId` and exact payload**. The server returns the stored receipt with `replayed: true` without adding duplicates. Receipts cover the last 128 successful requests in that open project session; they are not a durable cross-restart log. If a receipt is unavailable and its old revision is stale, inspect the graph before deciding what work remains. `request_conflict` means that ID was already used with different content; inspect the project before proceeding. Do not blindly repeat a write with a fresh ID after a transport failure.
- `project_not_active`: ask the user to select the intended Canvas tab. `project_busy`: wait for the existing interaction to finish, reread, and retry only while the request remains relevant.
- `node_not_found`, `node_not_editable`, `invalid_connection` or `agent_unavailable`: reread affected nodes and current installed agent definitions, fix the concrete cause, and submit a new transaction. Agent lists do not expose enablement; an installed assistant rejected as unavailable may need enabling in Canvas Settings. Do not bypass validation with filesystem edits or a second server.

The edit tool is advertised as a destructive write because it can change existing text and positions; its request receipt makes exact retries idempotent. User instructions to build or edit the flow authorize those graph changes. Assistant execution and media generation use the separate run tools only when requested; see [flow-execution.md](flow-execution.md).
