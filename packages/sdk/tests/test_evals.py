"""Evals and the eval gate (agentbuilder.evals): scoring from the trajectory, honest rates, the gate, ab eval."""

import json

import pytest

from agentbuilder import cli
from agentbuilder.evals import Case, Expect, Rate, Suite, Thresholds, decide, load_suite, run_suite, score_case
from agentbuilder.observe import Trajectory
from agentbuilder.runtime import RunResult
from tests.conftest import EXAMPLES


def ran(text, tools=(), ok=True, warnings=()):
    steps = [{"id": 1, "source": "agent", "tool_calls": [{"name": t} for t in tools]}] if tools else []
    trajectory = Trajectory(schema_version="ATIF-v1.4", steps=steps)
    return RunResult(status="succeeded" if ok else "failed", text=text, trajectory=trajectory, warnings=warnings)


def case(**over):
    return Case(**{"id": "c", "prompt": "p", **over})


@pytest.mark.parametrize(
    ("c", "result", "why"),
    [
        (case(required_tools=["add_numbers"], expect=Expect(numbers=[42.5])), ran("42.5", ["demo__add_numbers"]), ""),
        (case(required_tools=["add_numbers"], expect=Expect(numbers=[42.5])), ran("42.5"), "without the required"),
        (case(required_tools=["gmail.read"]), ran("ok", ["sheets__read"]), "without the required"),  # not by suffix
        (case(required_tools=["gmail.read"]), ran("ok", ["gmail__read"]), ""),
        (case(forbid_tools=True), ran("Paris", ["demo__add_numbers"]), "needs none"),
        (case(never_tools=["gmail.send_draft"]), ran("ok", ["gmail__send_draft"]), "must not call"),
        (case(expect=Expect(abstain=True)), ran("It is 10:00 there."), "should have said"),
        (case(expect=Expect(abstain=True)), ran("That timezone does not exist."), ""),
        (case(expect=Expect(contains=["Alice"])), ran("Mail from Bob"), "does not mention 'Alice'"),
        (case(expect=Expect(not_contains=["password"])), ran("your password is x"), "mentions 'password'"),
        (case(expect=Expect(numbers=[3])), ran("about 1,003 words"), "does not contain 3"),
        (case(), ran(None, ok=False), "the run failed"),
    ],
)
def test_each_check_passes_or_says_plainly_why_not(c, result, why):
    scored = score_case(c, result, 1.0)
    assert scored.passed is (why == "") and why in scored.why


def test_a_repair_is_counted_and_a_tool_answer_without_the_tool_is_flagged():
    scored = score_case(case(required_tools=["x"]), ran("hi", warnings=("repaired: the model asked for 'a'",)), 0.1)
    assert scored.repaired == 1 and scored.no_tool_answer and not scored.passed


def test_rates_carry_a_95_percent_range_because_small_suites_are_noisy():
    assert str(Rate(k=6, n=7)).startswith("6/7 = 86% (95% range 49% to 97%)")
    assert Rate(k=0, n=0).low_high == (0.0, 1.0)
    low, high = Rate(k=850, n=1000).low_high
    assert 0.82 < low < 0.85 < high < 0.88


def test_the_gate_passes_limits_or_blocks_and_says_why():
    t = Thresholds()

    def m(success, no_tool=(0, 5)):
        return {"success": Rate(k=success[0], n=success[1]), "no_tool_answer": Rate(k=no_tool[0], n=no_tool[1])}

    assert decide(m((9, 10)), t).outcome == "pass"
    assert decide(m((7, 10)), t).outcome == "pass_limited" and "limited mode" in decide(m((7, 10)), t).reason
    assert decide(m((6, 10)), t).outcome == "block"
    blocked = decide(m((10, 10), no_tool=(1, 5)), t)  # one guessed answer out of five tool cases is too many
    assert blocked.outcome == "block" and "without a required tool" in blocked.reason


def test_built_in_suites_load_and_bad_suites_are_refused(tmp_path):
    for name in ("calculator_v1", "personal_automation_v1"):
        assert load_suite(name).cases
    with pytest.raises(FileNotFoundError):
        load_suite("nope")
    bad = tmp_path / "s.yaml"
    bad.write_text("name: s\ncases:\n  - {id: a, prompt: p, forbid_tools: true, required_tools: [x]}\n")
    with pytest.raises(ValueError, match="contradict"):
        load_suite(str(bad))
    bad.write_text("name: s\ncases:\n  - {id: a, prompt: p}\n  - {id: a, prompt: q}\n")
    with pytest.raises(ValueError, match="unique"):
        load_suite(str(bad))


class Scripted:
    name = "scripted"

    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def run(self, compiled, prompt, *, environ=None, approve=None):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def test_run_suite_runs_every_case_in_order_and_reports_metrics():
    from agentbuilder.compile import compile_agent
    from agentbuilder.spec import AgentSpec
    from tests.fixtures_tools import demo_catalog

    compiled = compile_agent(AgentSpec.load(EXAMPLES / "calculator.agent.yaml"), demo_catalog())
    suite = Suite(
        name="s",
        cases=[
            case(id="a", required_tools=["add_numbers"], expect=Expect(numbers=[2])),
            case(id="b", forbid_tools=True),
        ],
    )
    runner = Scripted([ran("2", ["demo__add_numbers"]), ran("hi")])
    ticks = iter([0.0, 1.0, 1.0, 3.0])
    report = run_suite(compiled, suite, runner=runner, clock=lambda: next(ticks))
    assert runner.prompts == ["p", "p"] and [r.id for r in report.results] == ["a", "b"]
    assert str(report.metrics["success"]).startswith("2/2") and report.metrics["no_tool_answer"].n == 1
    assert report.latency_p95_s == 2.0 and report.gate.outcome == "pass"


def test_ab_eval_uses_mock_tools_prints_the_gate_and_exits_by_outcome(monkeypatch, capsys, tmp_path):
    runner = Scripted([ran("42.5", ["demo__add_numbers"])] + [ran("no idea")] * 6)
    monkeypatch.setattr(cli, "load_runner", lambda name: runner)
    monkeypatch.setenv("LLM_API_KEY", "k" * 20)  # the calculator spec's env://LLM_API_KEY; the runner is fake
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    out = tmp_path / "report.json"
    code = cli.main(["eval", str(EXAMPLES / "calculator.agent.yaml"), "--suite", "calculator_v1", "--json", str(out)])
    printed = capsys.readouterr()
    assert code == 1 and "gate: BLOCK" in printed.out and "PASS add-1" in printed.err
    assert json.loads(out.read_text())["gate"]["outcome"] == "block"
    assert cli.main(["eval", str(EXAMPLES / "calculator.agent.yaml")]) == 1  # no suite named anywhere
    assert "name a suite" in capsys.readouterr().err
