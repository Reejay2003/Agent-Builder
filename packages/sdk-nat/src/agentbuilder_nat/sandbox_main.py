"""Runs INSIDE the OpenShell sandbox: `python -m agentbuilder_nat.sandbox_main`, with one JSON line on stdin.

The payload is {"compiled": CompiledAgent, "prompt": str}, sent on stdin so the prompt never shows in a process list. It carries no key: the model key arrives as OpenShell's
placeholder in the environment and the sandbox proxy swaps in the real one for the model host only. The result goes to
stdout as one line, `AGENTBUILDER_RESULT <RunResult json>`, so the host can find it among other output."""

from __future__ import annotations

import json
import sys

from agentbuilder.compile.compiled import CompiledAgent
from agentbuilder.runtime import RunResult

MARKER = "AGENTBUILDER_RESULT "


def main() -> int:
    try:
        payload = json.loads(sys.stdin.readline())  # one line: OpenShell does not forward the end of stdin
        from agentbuilder_nat.local import LocalRunner

        result = LocalRunner().run(CompiledAgent.model_validate(payload["compiled"]), payload["prompt"])
    except Exception as exc:  # noqa: BLE001  whatever happens, the host gets a result line, not a traceback
        result = RunResult(status="failed", error=f"the agent could not start in the sandbox: {type(exc).__name__}")
    print(MARKER + result.model_dump_json(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
