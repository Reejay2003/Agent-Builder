"""The eval gate end to end, offline: the built-in calculator suite runs case by case on real NAT + Fabric (LocalRunner)
against the fake model and the real demo tool server, and the gate decides. SDK 0.2 exit criterion: "Eval suite runs
in CI against FakeModel". No API key, no cost. Skipped without the NVIDIA stack."""

import sys
from pathlib import Path

import pytest
from tests.conftest import EXAMPLES
from tests.fixtures_tools import demo_tools_on_path

from agentbuilder.compile import compile_agent
from agentbuilder.evals import load_suite, run_suite
from agentbuilder.runtime import credential_env, load_runner
from agentbuilder.spec import AgentSpec
from agentbuilder.testing import FakeModel, FakeOpenAIServer, ToolCall, Turn
from agentbuilder.tools import ToolCatalog

pytest.importorskip("nemo_fabric")
pytest.importorskip("agentbuilder_nat")
SERVER = Path(__file__).resolve().parents[4] / "packages" / "mcp-tools" / "demo_server.py"
pytestmark = [pytest.mark.nat, pytest.mark.skipif(not SERVER.exists(), reason="needs the repository checkout")]


def calls(name, args, answer):
    return [Turn.calls(ToolCall(name, args)), Turn.say(answer)]


# One scripted model run per case, in suite order. The words case answers WITHOUT its tool: the gate must notice.
SCRIPT = [
    *calls("add_numbers", {"a": 17.5, "b": 25}, "17.5 plus 25 is 42.5."),
    *calls("add_numbers", {"a": -8.25, "b": 3.75}, "The result is -4.5."),
    *calls("add_numbers", {"a": 0.1, "b": 0.2}, "0.1 plus 0.2 is 0.3."),
    *calls("count_words", {"text": "the quick brown fox jumps over the lazy dog"}, "There are 9 words."),
    Turn.say("That is 1 word."),  # guessed: no tool call
    Turn.say("Paris"),
    *calls("get_current_time", {"timezone": "Mars/Olympus_Mons"}, "That timezone does not exist."),
]


def test_the_calculator_suite_runs_on_real_nat_and_the_gate_blocks_a_guessed_answer():
    demo_tools_on_path()
    from demo_tools import TOOLS

    model = FakeModel(SCRIPT)
    with FakeOpenAIServer(model) as server:
        spec = AgentSpec.load(EXAMPLES / "calculator.agent.yaml")
        spec = spec.model_copy(
            update={"model": spec.model.model_copy(update={"agent_mode": "tool_calling", "base_url": server.base_url})}
        )
        catalog = ToolCatalog().add_tools("demo", TOOLS, command=sys.executable, args=[str(SERVER)])
        compiled = compile_agent(spec, catalog)
        env = credential_env(spec, compiled, environ={compiled.model.api_key_env: "sk-test-" + "e" * 32})
        report = run_suite(compiled, load_suite("calculator_v1"), runner=load_runner("local"), environ=env)
    by_id = {r.id: r for r in report.results}
    assert [r.id for r in report.results if not r.passed] == ["words-2"], [(r.id, r.why) for r in report.results]
    assert "without the required tool(s) count_words" in by_id["words-2"].why
    assert by_id["add-1"].tools_used == ("demo__add_numbers",)  # proven by the trajectory, not the answer
    assert str(report.metrics["success"]).startswith("6/7")
    assert report.gate.outcome == "block" and "without a required tool" in report.gate.reason
    assert model.remaining == 0
