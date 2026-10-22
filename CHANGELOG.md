# Changelog

## 1.1.0

- Canvas and its plugin share one fixed local HTTP endpoint with no manual port selection or client configuration.
- Keep a single plugin-owned HTTP MCP connection; remove the direct-registration workaround from setup.
- Installation diagnostics reject endpoint overrides and verify the actual bundled server, plus unavailable/reconnect behavior.
- Requires the updated Canvas version using the fixed plugin endpoint.

## 1.0.0

- Initial Canvas plugin and Git marketplace catalog.
- Direct connection to Canvas's local Streamable HTTP MCP endpoint.
- Read-only workspace guidance.
