"""Serve decorated tools as an MCP stdio server (needs the `mcp` extra: pip install "agentbuilder[mcp]").

Every call is appended to an audit log (JSON lines: time, tool, arguments, mock) so tests and reviewers can PROVE a tool
ran, independent of what the model said. `--mock` returns each tool's `mock_response` without running the function:
test mode must never touch live systems (PLAN 7.3).

    if __name__ == "__main__":
        main([add_numbers, count_words])          # reads --log PATH, --mock and --approvals DIR --approve IDS
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from agentbuilder.tools.decorator import Tool
from agentbuilder.tools.manifest import ensure_unique

MAX_LOG_BYTES = 10 * 1024 * 1024  # the audit log rotates at 10 MB and keeps one older file


def _audit(
    path: str | None, tool: Tool, arguments: dict[str, Any], mock: bool, log_args: bool, approval: str | None = None
) -> None:
    """Append one JSON line per call. Argument VALUES are not written unless `log_args` (they may hold passwords or
    message bodies); the file is created private (0600). Past MAX_LOG_BYTES the file becomes `<name>.1` (replacing
    the previous one) and a new file starts, so the log never takes more than about twice that."""
    if path:
        import fcntl  # POSIX only, like _take_slot

        args = arguments if log_args else {k: f"{type(v).__name__}({len(str(v))})" for k, v in arguments.items()}
        record = {"t": time.time(), "tool": tool.mcp_name, "id": tool.id, "args": args, "mock": mock}
        if approval:
            record["approval"] = approval  # approved, declined or expired
        for attempt in range(2):  # a full file is rotated, then the line goes into the fresh one
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            os.fchmod(fd, 0o600)  # also tightens a file that already existed with wider permissions
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)  # tool servers of several runs share this file
                mine = os.fstat(f.fileno())
                if mine.st_size < MAX_LOG_BYTES or attempt:
                    f.write(json.dumps(record, default=str) + "\n")
                    return
                # Rotate only if `path` is still the file we hold: another server may have rotated it while we waited.
                with contextlib.suppress(FileNotFoundError):
                    if os.path.samestat(mine, os.stat(path)):
                        os.replace(path, f"{path}.1")


def _recent_calls(times: list[float], now: float) -> list[float]:
    return [t for t in times if now - t < 60]  # a sliding one-minute window


def _take_slot(path: Path | None, memory: list[float], limit: int) -> bool:
    """Count one call against `limit` per minute. With a path (the gateway gave an audit log), the count lives in a
    file next to it, locked, so it holds across runs and tool processes; without one it is per process."""
    now = time.time()
    if path is None:
        memory[:] = _recent_calls(memory, now)
        if len(memory) >= limit:
            return False
        memory.append(now)
        return True
    import fcntl  # POSIX only, like the rest of the tool servers' supported platforms (macOS, Linux)

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        times = _recent_calls([float(x) for x in f.read().split() if x.replace(".", "", 1).isdigit()], now)
        allowed = len(times) < limit
        if allowed:
            times.append(now)
        f.seek(0)
        f.truncate()
        f.write("\n".join(repr(t) for t in times))
    return allowed


def _wrap(
    tool: Tool, log_path: str | None, mock: bool, log_args: bool, approvals: str | None = None
) -> Callable[..., Any]:
    """`approvals`: the run's approval folder when a person must approve each live call of this tool."""
    limit = tool.manifest.rate_limits.per_minute
    counter = Path(log_path).with_name("rate-limits") / tool.id if log_path else None
    memory: list[float] = []
    lock = threading.Lock()

    @functools.wraps(tool.fn)
    def run(*args: Any, **kwargs: Any) -> Any:
        if limit and not mock:  # mock touches nothing live, so it spends no quota
            with lock:
                if not _take_slot(counter, memory, limit):
                    raise RuntimeError(f"{tool.id} is limited to {limit} calls a minute; wait a little and try again")
        arguments = kwargs or {"_positional": list(args)}
        approval = None
        if approvals and not mock:  # after the rate limit, so a looping model cannot flood a person with requests
            from agentbuilder.approvals import wait_for_approval

            approval = wait_for_approval(approvals, tool.id, tool.manifest.risk_tier, arguments)
        _audit(log_path, tool, arguments, mock, log_args, approval)
        if approval == "declined":
            raise RuntimeError(f"a person declined this {tool.id} call, so it did not run; do not try it again")
        if approval == "expired":
            raise RuntimeError(f"no one approved this {tool.id} call in time, so it did not run")
        return tool.manifest.mock_response if mock else tool.fn(*args, **kwargs)

    return run


def build_server(
    tools: Sequence[Tool],
    *,
    name: str = "agentbuilder-tools",
    log_path: str | None = None,
    mock: bool = False,
    log_args: bool = False,
    approvals: str | None = None,
    approve: Sequence[str] = (),
) -> Any:
    """`approvals` + `approve`: the run's approval folder and the ids of the tools that must ask a person first."""
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
        asks = approvals if t.id in approve else None
        server.add_tool(
            _wrap(t, log_path, mock, log_args, asks), name=t.mcp_name, description=t.manifest.description_plain
        )
    return server


def main(tools: Sequence[Tool], *, name: str = "agentbuilder-tools", argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)

    def value(flag: str) -> str | None:
        return args[args.index(flag) + 1] if flag in args else None

    build_server(
        tools,
        name=name,
        log_path=value("--log"),
        mock="--mock" in args,
        log_args="--log-args" in args,
        approvals=value("--approvals"),
        approve=(value("--approve") or "").split(","),
    ).run(transport="stdio")
