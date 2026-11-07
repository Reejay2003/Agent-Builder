"""The built-in tool library for the personal-automation template: Gmail, Calendar, Sheets and web search.

Standard library only. Each namespace is served by its own MCP server (`python -m agentbuilder.library.server <ns>`), so
a spec that uses only `calendar.*` never starts, or gets network access for, Gmail. Every tool has a mock response: in
mock mode nothing leaves the machine."""

from agentbuilder.library.catalog import personal_catalog

__all__ = ["personal_catalog"]
