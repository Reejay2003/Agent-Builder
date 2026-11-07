"""Evals and the eval gate (PLAN 4.4.3): run a suite of cases against an agent, score each run from its trajectory, and
decide pass, pass with limited mode, or block.

    suite = load_suite("calculator_v1")
    report = run_suite(compiled, suite, runner=load_runner("local"))
    report.gate.outcome, report.metrics["success"]

The core imports no runner: any `Runner` works, including a fake one in tests.
"""

from agentbuilder.evals.scoring import CaseResult, Gate, Rate, Report, decide, run_suite, score_case
from agentbuilder.evals.suite import Case, Expect, Suite, Thresholds, load_suite

__all__ = [
    "Case",
    "CaseResult",
    "Expect",
    "Gate",
    "Rate",
    "Report",
    "Suite",
    "Thresholds",
    "decide",
    "load_suite",
    "run_suite",
    "score_case",
]
