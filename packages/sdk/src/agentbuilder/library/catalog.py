"""The personal-automation tools as a ToolCatalog: one MCP server per namespace (gmail, calendar, sheets, web)."""

from __future__ import annotations

import sys

from agentbuilder.library import calendar_tools, gmail_tools, sheets_tools, web_tools
from agentbuilder.tools import Tool, ToolCatalog

TOOLS_BY_NAMESPACE: dict[str, list[Tool]] = {
    "gmail": [gmail_tools.read, gmail_tools.send_draft],
    "calendar": [calendar_tools.list_events, calendar_tools.create_event],
    "sheets": [sheets_tools.read],
    "web": [web_tools.search],
}


def personal_catalog(catalog: ToolCatalog | None = None, *, python: str | None = None) -> ToolCatalog:
    """Add the library to `catalog` (or a new one). Each namespace runs as
    `python -m agentbuilder.library.server <namespace>`."""
    catalog = ToolCatalog() if catalog is None else catalog
    for namespace, tools in TOOLS_BY_NAMESPACE.items():
        catalog.add_tools(
            namespace, tools, command=python or sys.executable, args=["-m", "agentbuilder.library.server", namespace]
        )
    return catalog
