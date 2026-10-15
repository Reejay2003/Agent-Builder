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
import os
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

from agentbuilder.tools.decorator import Tool
from agentbuilder.tools.manifest import ensure_unique


def _audit(path: str | None, tool: Tool, arguments: dict[str, Any], mock: bool, log_args: bool) -> None:
    """Append one JSON line per call. Argument VALUES are not written unless `log_args` (they may hold passwords or
    message bodies); the file is created private (0600)."""
    if path:
        args = arguments if log_args else {k: f"{type(v).__name__}({len(str(v))})" for k, v in arguments.items()}
        record = {"t": time.time(), "tool": tool.mcp_name, "id": tool.id, "args": args, "mock": mock}
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600)  # also tightens a file that already existed with wider permissions
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def _wrap(tool: Tool, log_path: str | None, mock: bool, log_args: bool) -> Callable[..., Any]:
    @functools.wraps(tool.fn)
    def run(*args: Any, **kwargs: Any) -> Any:
        _audit(log_path, tool, kwargs or {"_positional": list(args)}, mock, log_args)
        return tool.manifest.mock_response if mock else tool.fn(*args, **kwargs)

    return run


def build_server(
    tools: Sequence[Tool],
    *,
    name: str = "agentbuilder-tools",
    log_path: str | None = None,
    mock: bool = False,
    log_args: bool = False,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError('serving tools needs the MCP package: pip install "agentbuilder[mcp]"') from exc
    ensure_unique([t.manifest for t in tools])
    if mock and (missing := [t.id for t in tools if t.manifest.mock_response is None]):
        raise ValueError(
            f"--mock needs a mock_response on every tool; missing: {missing} (use {{}} if a tool returns nothing)"
        )
    server = FastMCP(name)
    for t in tools:
        server.add_tool(_wrap(t, log_path, mock, log_args), name=t.mcp_name, description=t.manifest.description_plain)
    return server


def main(tools: Sequence[Tool], *, name: str = "agentbuilder-tools", argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    log_path = args[args.index("--log") + 1] if "--log" in args else None
    build_server(tools, name=name, log_path=log_path, mock="--mock" in args, log_args="--log-args" in args).run(
        transport="stdio"
    )
