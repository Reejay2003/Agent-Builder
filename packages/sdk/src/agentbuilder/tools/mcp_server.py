"""Serve decorated tools as an MCP stdio server (needs the `mcp` extra: pip install "agentbuilder[mcp]").

Every call is appended to an audit log (JSON lines: time, tool, arguments, mock) so tests and reviewers can PROVE a tool
ran, independent of what the model said. `--mock` returns each tool's `mock_response` without running the function:
test mode must never touch live systems (PLAN 7.3).

    if __name__ == "__main__":
        main([add_numbers, count_words])          # reads --log PATH and --mock from the command line
"""

from __future__ import annotations

import functools
import json
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

from agentbuilder.tools.decorator import Tool


def _audit(path: str | None, tool: Tool, arguments: dict[str, Any], mock: bool) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"t": time.time(), "tool": tool.mcp_name, "id": tool.id, "args": arguments, "mock": mock},
                    default=str,
                )
                + "\n"
            )


def _wrap(tool: Tool, log_path: str | None, mock: bool) -> Callable[..., Any]:
    @functools.wraps(tool.fn)
    def run(*args: Any, **kwargs: Any) -> Any:
        _audit(log_path, tool, kwargs or {"_positional": list(args)}, mock)
        return tool.manifest.mock_response if mock else tool.fn(*args, **kwargs)

    return run


def build_server(
    tools: Sequence[Tool], *, name: str = "agentbuilder-tools", log_path: str | None = None, mock: bool = False
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError('serving tools needs the MCP package: pip install "agentbuilder[mcp]"') from exc
    ids = [t.id for t in tools]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate tool ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    server = FastMCP(name)
    for t in tools:
        server.add_tool(_wrap(t, log_path, mock), name=t.mcp_name, description=t.manifest.description_plain)
    return server


def main(tools: Sequence[Tool], *, name: str = "agentbuilder-tools", argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    log_path = args[args.index("--log") + 1] if "--log" in args else None
    build_server(tools, name=name, log_path=log_path, mock="--mock" in args).run(transport="stdio")
