"""Where tools live: which MCP server provides which tool id.

The compiler resolves a spec's tool ids through a catalog."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from agentbuilder.tools.decorator import Tool
from agentbuilder.tools.manifest import ToolManifest


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class McpServerBinding(_Strict):
    name: str
    command: str
    args: list[str] = Field(default_factory=list)


class ResolvedTool(_Strict):
    id: str
    server: str
    mcp_name: str
    manifest: ToolManifest


class UnknownToolError(KeyError):
    """A spec references tool ids the catalog does not provide."""


class ToolCatalog:
    def __init__(self) -> None:
        self._servers: dict[str, McpServerBinding] = {}
        self._tools: dict[str, ResolvedTool] = {}

    def add_server(self, server: McpServerBinding, manifests: Sequence[ToolManifest]) -> ToolCatalog:
        if server.name in self._servers:
            raise ValueError(f"server '{server.name}' is already in the catalog")
        for m in manifests:
            if m.id in self._tools:
                raise ValueError(f"tool id '{m.id}' is already provided by server '{self._tools[m.id].server}'")
        self._servers[server.name] = server
        for m in manifests:
            self._tools[m.id] = ResolvedTool(id=m.id, server=server.name, mcp_name=m.mcp_name, manifest=m)
        return self

    def add_tools(self, server_name: str, tools: Sequence[Tool], command: str, args: Sequence[str] = ()) -> ToolCatalog:
        """Register Python tools that a `main(tools)` script serves over MCP stdio at `command args`."""
        return self.add_server(
            McpServerBinding(name=server_name, command=command, args=list(args)), [t.manifest for t in tools]
        )

    @property
    def tool_ids(self) -> list[str]:
        return sorted(self._tools)

    def server(self, name: str) -> McpServerBinding:
        return self._servers[name]

    def resolve(self, ids: Sequence[str]) -> list[ResolvedTool]:
        missing = [i for i in ids if i not in self._tools]
        if missing:
            raise UnknownToolError(
                f"unknown tool ids: {', '.join(missing)} (catalog provides: {', '.join(self.tool_ids) or 'nothing'})"
            )
        return [self._tools[i] for i in ids]

    def servers_for(self, tools: Sequence[ResolvedTool]) -> Mapping[str, McpServerBinding]:
        return {t.server: self._servers[t.server] for t in tools}
