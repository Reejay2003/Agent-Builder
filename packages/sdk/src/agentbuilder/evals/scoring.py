"""Score runs and decide the gate. Tool use is proven by the trajectory, never by what the answer claims."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentbuilder.compile.compiled import CompiledAgent
from agentbuilder.evals.suite import Case, Suite, Thresholds
from agentbuilder.runtime import Runner, RunResult

_ABSTAIN = re.compile(
    r"unknown|invalid|not (a )?(real|valid|recogni[sz]ed|found|exist|able)|does(n't| not) (exist|have)|couldn't|"
    r"could not|unable|no such|cannot|can't|don't know|do not know|not sure|no information",
    re.I,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class CaseResult(_Frozen):
    id: str
    category: str
    passed: bool
    why: str  # one plain reason when it failed, "" when it passed
    ran: bool  # the run finished (False: it crashed or the model output could not be used)
    no_tool_answer: bool  # a tool was required but the agent answered without one
    repaired: int
    tools_used: tuple[str, ...]
    seconds: float
    tokens: int | None
    answer: str | None


class Rate(_Frozen):
    """k out of n, with a 95% Wilson interval: small suites are noisy, so the range matters as much as the rate."""

    k: int
    n: int

    @property
    def value(self) -> float:
        return self.k / self.n if self.n else 0.0

    @property
    def low_high(self) -> tuple[float, float]:
        if not self.n:
            return 0.0, 1.0
        z, p, n = 1.96, self.value, self.n
        centre = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return max(0.0, centre - half), min(1.0, centre + half)

    def __str__(self) -> str:
        low, high = self.low_high
        return f"{self.k}/{self.n} = {self.value:.0%} (95% range {low:.0%} to {high:.0%})"


class Gate(_Frozen):
    outcome: Literal["pass", "pass_limited", "block"]
    reason: str


class Report(_Frozen):
    suite: str
    agent: str
    model: str
    results: tuple[CaseResult, ...]
    metrics: dict[str, Rate]
    latency_p95_s: float
    tokens_per_task: float | None
    gate: Gate


def _numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))]


def _used(name: str, used: Sequence[str]) -> bool:
    """`gmail.read` matches the runtime's `gmail__read` (never `sheets__read`); a bare name like `add_numbers` matches
    it in any namespace."""
    if "." in name:
        return any(u in (name, name.replace(".", "__")) for u in used)
    return any(u == name or u.endswith(f"__{name}") for u in used)


def score_case(case: Case, result: RunResult, seconds: float) -> CaseResult:
    used = tuple(result.trajectory.tools_used) if result.trajectory else ()
    answer = result.text or ""
    repaired = sum(w.startswith("repaired:") for w in result.warnings)
    missing = [t for t in case.required_tools if not _used(t, used)]
    e = case.expect
    why = ""
    if not result.ok:
        why = f"the run failed: {(result.error or '')[:120]}"
    elif missing:
        why = f"answered without the required tool(s) {', '.join(missing)}"
    elif case.forbid_tools and used:
        why = f"used a tool ({', '.join(used)}) for a question that needs none"
    elif bad := [t for t in case.never_tools if _used(t, used)]:
        why = f"called a tool it must not call here: {', '.join(bad)}"
    elif e.abstain and (not _ABSTAIN.search(answer)):
        why = "should have said it cannot answer, but answered anyway"
    elif lost := [w for w in e.contains if w.lower() not in answer.lower()]:
        why = f"the answer does not mention {', '.join(repr(w) for w in lost)}"
    elif lost_n := [n for n in e.numbers if not any(abs(x - n) <= 0.011 for x in _numbers(answer))]:
        why = f"the answer does not contain {', '.join(str(n) for n in lost_n)}"
    elif extra := [w for w in e.not_contains if w.lower() in answer.lower()]:
        why = f"the answer mentions {', '.join(repr(w) for w in extra)}"
    return CaseResult(
        id=case.id,
        category=case.category,
        passed=not why,
        why=why,
        ran=result.ok,
        no_tool_answer=result.ok and bool(case.required_tools) and not used,
        repaired=repaired,
        tools_used=used,
        seconds=round(seconds, 3),
        tokens=result.total_tokens,
        answer=result.text,
    )


def decide(metrics: dict[str, Rate], t: Thresholds) -> Gate:
    success, no_tool = metrics["success"], metrics["no_tool_answer"]
    if no_tool.value >= t.max_no_tool_answer and no_tool.k:
        return Gate(
            outcome="block",
            reason=f"it answered without a required tool in {no_tool} of the cases that need one "
            f"(limit {t.max_no_tool_answer:.0%}): its answers would be guesses. Try a model that uses tools reliably.",
        )
    if success.value >= t.success:
        return Gate(outcome="pass", reason=f"success {success} meets the bar of {t.success:.0%}")
    if success.value >= t.limited_success:
        return Gate(
            outcome="pass_limited",
            reason=f"success {success} is below {t.success:.0%} but at least {t.limited_success:.0%}: publish only in "
            "limited mode (a person approves every change; PLAN 4.4.1)",
        )
    return Gate(
        outcome="block",
        reason=f"success {success} is below {t.limited_success:.0%}. Try a stronger model or fewer tools.",
    )


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def run_suite(
    compiled: CompiledAgent,
    suite: Suite,
    *,
    runner: Runner,
    environ: dict[str, str] | None = None,
    on_case: Callable[[CaseResult], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Report:
    """Run every case once, in order (one at a time keeps a rate-limited free tier usable)."""
    results = []
    for case in suite.cases:
        started = clock()
        result = runner.run(compiled, case.prompt, environ=environ)
        scored = score_case(case, result, clock() - started)
        results.append(scored)
        if on_case:
            on_case(scored)
    n = len(results)
    need_tool = [r for r, c in zip(results, suite.cases, strict=True) if c.required_tools]
    metrics = {
        "success": Rate(k=sum(r.passed for r in results), n=n),
        "ran": Rate(k=sum(r.ran for r in results), n=n),
        "no_tool_answer": Rate(k=sum(r.no_tool_answer for r in need_tool), n=len(need_tool)),
        "repaired": Rate(k=sum(r.repaired > 0 for r in results), n=n),
    }
    tokens = [r.tokens for r in results if r.tokens is not None]
    return Report(
        suite=suite.name,
        agent=compiled.name,
        model=compiled.model.model,
        results=tuple(results),
        metrics=metrics,
        latency_p95_s=_p95([r.seconds for r in results]),
        tokens_per_task=(sum(tokens) / len(tokens)) if tokens else None,
        gate=decide(metrics, suite.thresholds),
    )
