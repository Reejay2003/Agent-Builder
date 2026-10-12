"""A real NAT agent (with a real MCP tool server) runs against the fake OpenAI server: no API key, no cost, no network.
Needs the NVIDIA stack and the repo checkout, so it is skipped elsewhere (marker: nat)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agentbuilder.testing import FakeModel, FakeOpenAIServer, ToolCall, Turn

ROOT = Path(__file__).resolve().parents[4]
NAT = shutil.which("nat") or str(ROOT / ".venv" / "bin" / "nat")
pytestmark = [
    pytest.mark.nat,
    pytest.mark.skipif(not Path(NAT).exists(), reason="NAT is not installed"),
    pytest.mark.skipif(not (ROOT / "agents" / "mcp-agent").exists(), reason="needs the repository checkout"),
]


def run_agent(config: str, model: FakeModel, question: str) -> str:
    with FakeOpenAIServer(model) as server:
        env = {
            **os.environ,
            "LLM_BASE_URL": server.base_url,
            "LLM_API_KEY": "fake-key",
            "LLM_MODEL": "fake-model",
            "PATH": f"{Path(NAT).parent}:{os.environ['PATH']}",
        }
        out = subprocess.run(
            [NAT, "run", "--config_file", f"agents/mcp-agent/{config}", "--input", question],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
    return out.stdout + out.stderr


def test_tool_calling_agent_runs_end_to_end_offline():
    model = FakeModel([Turn.calls(ToolCall("add_numbers", {"a": 17.5, "b": 25})), Turn.say("The sum is 42.5.")])
    text = run_agent("workflow-tool_calling.yml", model, "What is 17.5 plus 25? Use the tools.")
    assert "The sum is 42.5." in text
    assert model.remaining == 0
    # the real MCP tool ran and its result was sent back to the "model" on the second request
    second = model.requests[1].messages
    assert any("42.5" in str(m.get("content")) and m.get("role") == "tool" for m in second)
    assert "demo_tools__add_numbers" in model.requests[0].tool_names


def test_react_agent_runs_end_to_end_offline():
    model = FakeModel([Turn.react("demo_tools__add_numbers", {"a": 2, "b": 3}), Turn.react_final("The answer is 5.0.")])
    text = run_agent("workflow-react.yml", model, "What is 2 plus 3? Use the tools.")
    assert "The answer is 5.0." in text
    assert model.remaining == 0
