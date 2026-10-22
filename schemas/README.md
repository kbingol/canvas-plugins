# Upstream schemas

These unmodified Agent Plugins 1.0.0 schemas come from the schema URLs referenced by the official OpenAI package guide:

- https://agent-plugins.org/schemas/1.0.0/plugin.schema.json
- https://agent-plugins.org/schemas/1.0.0/mcp.schema.json

Vendoring keeps package validation reproducible and independent of network availability. The schemas are validation inputs, not runtime dependencies of the plugin. Their license and specification are maintained by the Agent Plugins project.

The published MCP schema rejects per-server `extensions` although OpenAI's authentication examples include them. This anonymous local connection omits that optional declaration and validates against the unmodified upstream schema.
