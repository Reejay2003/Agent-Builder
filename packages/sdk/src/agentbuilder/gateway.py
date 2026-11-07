"""The tool gateway: the one place that decides HOW tool servers are started for a run.

Today it is a thin local wrapper: it can switch every tool to mock mode (nothing touches a live system) and point every
tool server at one shared audit log. The interface is deliberately tiny so another implementation, for example one
backed by a LiteLLM proxy or a dedicated MCP gateway service, can replace `LocalGateway` without changing any caller.
Which tools a run may use is NOT decided here: that is the spec's tool list, enforced by the compiler (`allowed_tools`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from agentbuilder.tools.catalog import McpServerBinding, ToolCatalog


class Gateway(Protocol):
    def apply(self, catalog: ToolCatalog, *, mock: bool = False, audit_log: str | None = None) -> ToolCatalog:
        """A catalog whose servers are started the way this gateway wants."""
        ...


def default_audit_log() -> str:
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "agentbuilder"
    return str(state / "tool-calls.jsonl")


class LocalGateway:
    """Appends `--mock` and `--log <file>` to every SDK-built tool server. Servers it did not build (a bring-your-own
    MCP server) are left alone, and a mock request for them is refused because mock mode could not be guaranteed."""

    def apply(self, catalog: ToolCatalog, *, mock: bool = False, audit_log: str | None = None) -> ToolCatalog:
        if audit_log:
            Path(audit_log).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        out = ToolCatalog()
        for name, binding in catalog.servers.items():
            extra: list[str] = []
            if binding.gateway_flags:
                extra += (["--mock"] if mock else []) + (["--log", audit_log] if audit_log else [])
            elif mock:
                raise ValueError(f"mock mode is not available for server '{name}' (it was not built with the SDK)")
            out.add_server(
                McpServerBinding(
                    name=name,
                    command=binding.command,
                    args=[*binding.args, *extra],
                    gateway_flags=binding.gateway_flags,
                ),
                [r.manifest for r in catalog.tools_of(name)],
            )
        return out
