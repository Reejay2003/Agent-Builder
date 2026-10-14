"""spec -> compile -> RUN, offline: the compiled configs execute on real NAT and real Fabric (with our adapter)
against the fake OpenAI server and the real SDK-served MCP tool server. No API key, no cost.
Skipped without the NVIDIA stack."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tests.conftest import EXAMPLES
from tests.fixtures_tools import demo_tools_on_path

from agentbuilder.compile import compile_agent, to_fabric_config, to_nat_yaml
from agentbuilder.spec import AgentSpec
from agentbuilder.testing import FakeModel, FakeOpenAIServer, ToolCall, Turn
from agentbuilder.tools import ToolCatalog

ROOT = Path(__file__).resolve().parents[4]
NAT = shutil.which("nat") or str(ROOT / ".venv" / "bin" / "nat")
ADAPTER = ROOT / "services" / "runner" / "nat_adapter"
SERVER = ROOT / "packages" / "mcp-tools" / "demo_server.py"
pytestmark = [
    pytest.mark.nat,
    pytest.mark.skipif(not Path(NAT).exists(), reason="NAT is not installed"),
    pytest.mark.skipif(not SERVER.exists(), reason="needs the repository checkout"),
]


def script_for(mode: str) -> list[Turn]:
    if mode == "tool_calling":
        return [Turn.calls(ToolCall("add_numbers", {"a": 17.5, "b": 25})), Turn.say("The sum is 42.5.")]
    return [Turn.react("demo__add_numbers", {"a": 17.5, "b": 25}), Turn.react_final("The sum is 42.5.")]


def compiled(mode: str, base_url: str, tool_log: Path):
    demo_tools_on_path()
    from demo_tools import TOOLS  # the real demo tools, defined with the SDK

    spec = AgentSpec.load(EXAMPLES / "calculator.agent.yaml")
    spec = spec.model_copy(update={"model": spec.model.model_copy(update={"agent_mode": mode, "base_url": base_url})})
    catalog = ToolCatalog().add_tools("demo", TOOLS, command=sys.executable, args=[str(SERVER), "--log", str(tool_log)])
    return compile_agent(spec, catalog)


def tool_calls(log: Path) -> list[str]:
    return [json.loads(line)["tool"] for line in log.read_text().splitlines()] if log.exists() else []


def assert_instructions_reached_the_model(model: FakeModel) -> None:
    first = json.dumps(model.requests[0].messages)
    assert "careful assistant" in first and "Use the tools for any arithmetic" in first


@pytest.mark.parametrize("mode", ["tool_calling", "react"])
def test_compiled_nat_yaml_runs_on_real_nat(mode, tmp_path):
    model, log = FakeModel(script_for(mode)), tmp_path / "tools.jsonl"
    with FakeOpenAIServer(model) as server:
        c = compiled(mode, server.base_url, log)
        cfg = tmp_path / "workflow.yml"
        cfg.write_text(to_nat_yaml(c))
        env = {**os.environ, "LLM_API_KEY": "fake-key", "PATH": f"{Path(NAT).parent}:{os.environ['PATH']}"}
        out = subprocess.run(
            [NAT, "run", "--config_file", str(cfg), "--input", "What is 17.5 plus 25? Use the tools."],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
    assert "The sum is 42.5." in out.stdout + out.stderr
    assert tool_calls(log) == ["add_numbers"]  # the real tool really ran, and only that one
    assert model.remaining == 0
    assert_instructions_reached_the_model(model)


@pytest.mark.parametrize("mode", ["tool_calling", "react"])
def test_compiled_fabric_config_runs_through_our_adapter(mode, tmp_path, monkeypatch):
    nemo_fabric = pytest.importorskip("nemo_fabric")
    model, log = FakeModel(script_for(mode)), tmp_path / "tools.jsonl"
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("PYTHONPATH", str(ADAPTER / "src"))
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}:{os.environ['PATH']}")
    # Fabric picks the adapter host's Python from ADAPTER_PYTHON (or VIRTUAL_ENV), NOT from PATH. Without it the host
    # may start under another interpreter and fail with "No module named nemo_fabric_adapters.common".
    monkeypatch.setenv("ADAPTER_PYTHON", sys.executable)
    with FakeOpenAIServer(model) as server:
        c = compiled(mode, server.base_url, log)
        mapping = to_fabric_config(c, adapter_dir=str(ADAPTER))
        config = nemo_fabric.FabricConfig.model_validate(mapping)  # the compiler's output is a valid FabricConfig
        result = asyncio.run(
            nemo_fabric.Fabric().run(config, base_dir=str(tmp_path), input="What is 17.5 plus 25? Use the tools.")
        )
    out = result.to_mapping()
    assert out["status"] == "succeeded", out.get("error")
    assert "The sum is 42.5." in str(out["output"]["response"])
    assert tool_calls(log) == ["add_numbers"] and model.remaining == 0
    assert_instructions_reached_the_model(model)
