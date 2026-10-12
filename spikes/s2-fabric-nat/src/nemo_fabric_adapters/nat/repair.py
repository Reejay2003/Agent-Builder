"""Deterministic repair for NAT's ReAct agent (PLAN 4.4.2 step 1). Local addition, not in the upstream reference adapter.

A weak model often calls an MCP tool by its bare name (`add_numbers`) when NAT exposes it with a prefix (`demo__add_numbers`).
NAT's ReAct agent then returns "not a valid tool" and the model loops or gives up. This wraps the agent's tool lookup:
if the exact name is unknown and exactly ONE configured tool matches after trivial normalization (quotes, backticks, `()`,
case, a `<group>__` / `<group>.` prefix), use it. Ambiguous or unknown names are left alone (never guess). Every repair is
recorded in REPAIRS so it shows up in the run output; repairs are never silent.
Enable with env FABRIC_NAT_REPAIR=tool_names (read by the adapter at start)."""
from __future__ import annotations

import re
from typing import Any

REPAIRS: list[dict[str, str]] = []
_INSTALLED = False


def _clean(name: str) -> str:
    name = (name or "").strip().strip("`'\"").strip()
    return re.sub(r"\(\s*\)$", "", name).strip()


def resolve(name: str, available: list[str]) -> str | None:
    """Return the one available tool that `name` unambiguously refers to, else None."""
    want = _clean(name)
    if not want or want in available:
        return None
    low = want.lower()
    hits = {a for a in available if a.lower() == low or a.lower() == low.replace(".", "__")}
    hits |= {a for a in available if re.search(rf"(__|\.|:|/){re.escape(low)}$", a.lower())}
    return next(iter(hits)) if len(hits) == 1 else None


def install_tool_name_repair() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from nat.plugins.langchain.agent.react_agent.agent import ReActAgentGraph

    original = ReActAgentGraph._get_tool

    def _get_tool(self: Any, tool_name: str) -> Any:
        tool = original(self, tool_name)
        if tool is not None:
            return tool
        resolved = resolve(tool_name, list(self.tools_dict))
        if resolved is None:
            return None
        REPAIRS.append({"kind": "tool_name", "requested": str(tool_name), "resolved": resolved})
        return self.tools_dict[resolved]

    ReActAgentGraph._get_tool = _get_tool
    _INSTALLED = True
