"""Human approval of risky tool calls (PLAN 16.4: `approve=callback`; Tier 2 actions call it with the exact payload).

The pause happens INSIDE the tool server, where mock mode is also enforced, so the model cannot talk its way past it:

1. The runner gives each tool server that holds a tool needing approval two flags: `--approvals <dir>` (a private
   folder of this run) and `--approve <tool ids>`.
2. Before such a tool runs live, the server writes `<dir>/<id>.request.json` (tool, tier, the exact arguments) and
   waits for `<dir>/<id>.decision.json`. No decision within APPROVAL_TIMEOUT counts as "no".
3. On the host, `ApprovalWatcher` sees the request, calls the run's `approve(request) -> bool` and writes the decision.
   `ab run` asks in the terminal; the local server parks the request on the run for the web app to answer.

Files rather than a socket: the tool server is started by NAT, not by us, and a folder needs no port, token or
protocol. The folder is created 0700 and the files 0600 because they hold the real argument values.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentbuilder.compile import APPROVAL_TIMEOUT, CompiledAgent, needs_approval

POLL = 0.2


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    tool_id: str
    risk_tier: int
    arguments: dict[str, Any]
    created: float


Approver = Callable[[ApprovalRequest], bool]


def with_approvals(c: CompiledAgent, folder: str | os.PathLike[str]) -> CompiledAgent:
    """`c` with every live (not `--mock`) SDK-built tool server that holds a tool needing approval told to ask first.
    A server the SDK did not build would ignore the flags, so it is left as is and `unapproved_live_tools` still
    reports its tools: the runner refuses the run instead."""
    ask = set(needs_approval(c))
    servers = []
    for s in c.servers:
        ids = [t.id for t in c.tools_for(s.name) if t.id in ask]
        if ids and s.gateway_flags and "--mock" not in s.args:
            s = s.model_copy(update={"args": [*s.args, "--approvals", str(folder), "--approve", ",".join(ids)]})
        servers.append(s)
    return c.model_copy(update={"servers": servers})


def _write_private(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str)
    os.replace(tmp, path)  # the reader never sees half a file


# ---- tool-server side ---------------------------------------------------------------------------------------------


def wait_for_approval(
    folder: str | os.PathLike[str],
    tool_id: str,
    risk_tier: int,
    arguments: dict[str, Any],
    *,
    timeout: float = APPROVAL_TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Ask, wait, and return "approved", "declined" or "expired"."""
    rid = secrets.token_hex(8)
    base = Path(folder)
    request, decision = base / f"{rid}.request.json", base / f"{rid}.decision.json"
    _write_private(
        request,
        {"id": rid, "tool_id": tool_id, "risk_tier": risk_tier, "arguments": arguments, "created": time.time()},
    )
    deadline = clock() + timeout
    try:
        while clock() < deadline:
            with contextlib.suppress(FileNotFoundError, json.JSONDecodeError):
                answer = json.loads(decision.read_text(encoding="utf-8"))
                return "approved" if answer.get("approved") is True else "declined"
            sleep(POLL)
        return "expired"
    finally:
        for p in (request, decision):
            p.unlink(missing_ok=True)


# ---- host side ----------------------------------------------------------------------------------------------------


class ApprovalWatcher:
    """Answers the tool servers' requests in `folder` with `approve`, one at a time, until stopped.

    An approver that raises counts as "no": a broken approval path must never run the tool."""

    def __init__(self, folder: str | os.PathLike[str], approve: Approver) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.folder, 0o700)
        self._approve = approve
        self._seen: set[str] = set()
        self._stop = threading.Event()
        # Daemon: a terminal prompt nobody answers must not keep the process alive after the run has ended.
        self._thread = threading.Thread(target=self._loop, name="agentbuilder-approvals", daemon=True)

    def __enter__(self) -> ApprovalWatcher:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2 * POLL)

    def _loop(self) -> None:
        while not self._stop.is_set():
            for path in sorted(self.folder.glob("*.request.json")):
                self._answer(path)
            self._stop.wait(POLL)

    def _answer(self, path: Path) -> None:
        try:
            request = ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # gone (the tool gave up) or not a request we wrote
        if request.id in self._seen:
            return
        self._seen.add(request.id)
        try:
            approved = self._approve(request) is True
        except Exception:
            approved = False
        if path.exists():  # the tool is still waiting
            _write_private(self.folder / f"{request.id}.decision.json", {"approved": approved})


def describe(request: ApprovalRequest) -> str:
    """The exact payload, as a person should see it before saying yes."""
    return f"{request.tool_id} (tier {request.risk_tier}) wants to run with:\n" + json.dumps(
        request.arguments, indent=2, ensure_ascii=False, default=str
    )


def terminal_approver(ask: Callable[[str], str] = input, show: Callable[[str], None] | None = None) -> Approver:
    """`ab run`'s approver: shows the exact payload and asks; anything but y/yes is no."""
    import sys

    def approve(request: ApprovalRequest) -> bool:
        (show or (lambda text: print(text, file=sys.stderr, flush=True)))(describe(request))
        try:
            return ask("approve this action? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            return False

    return approve


__all__ = [
    "APPROVAL_TIMEOUT",
    "ApprovalRequest",
    "ApprovalWatcher",
    "Approver",
    "describe",
    "needs_approval",
    "terminal_approver",
    "wait_for_approval",
    "with_approvals",
]
