"""Compiler output checked against the REAL Fabric planner and our adapter's NAT config builder (offline)."""

from pathlib import Path

import pytest
from tests.fixtures_tools import demo_catalog

from agentbuilder.compile import compile_agent, to_fabric_config
from agentbuilder.spec import AgentSpec

ROOT = Path(__file__).resolve().parents[4]
ADAPTER = ROOT / "services" / "runner" / "nat_adapter"
pytestmark = [pytest.mark.nat, pytest.mark.skipif(not ADAPTER.exists(), reason="needs the repository checkout")]


def _plan(model: dict, tmp_path):
    nemo_fabric = pytest.importorskip("nemo_fabric")
    spec = AgentSpec.from_dict({"name": "x", "model": model, "tools": ["demo.add_numbers"]})
    mapping = to_fabric_config(compile_agent(spec, demo_catalog()), adapter_dir=str(ADAPTER))
    return (
        nemo_fabric.Fabric().plan(nemo_fabric.FabricConfig.model_validate(mapping), base_dir=str(tmp_path)).to_mapping()
    )


def test_nvidia_hosted_becomes_a_nim_llm_in_nat(tmp_path, monkeypatch):
    plan = _plan({"provider": "nvidia_hosted", "model": "nvidia/m", "credential_ref": "env://NVIDIA_API_KEY"}, tmp_path)
    monkeypatch.syspath_prepend(str(ADAPTER / "src"))
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    from nemo_fabric_adapter_contract.models import AgentConfig
    from nemo_fabric_adapters.nat.adapter import build_nat_config_mapping

    llm = build_nat_config_mapping(AgentConfig.from_mapping(plan["agent_config"]))["llms"]["default"]
    assert llm["_type"] == "nim" and llm["base_url"] == "https://integrate.api.nvidia.com/v1"


def test_a_spec_with_max_tokens_still_plans_because_it_is_not_emitted(tmp_path):
    plan = _plan(
        {"provider": "openai", "model": "gpt-4.1-mini", "credential_ref": "env://K", "max_tokens": 256}, tmp_path
    )
    assert plan["agent_name"] == "x"  # Fabric refused this plan before max_tokens was removed from the emitters
