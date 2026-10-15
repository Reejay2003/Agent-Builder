import json

import pytest
import yaml

from agentbuilder.compile import CompileError, compile_agent, to_fabric_config, to_nat_workflow, to_nat_yaml
from agentbuilder.spec import AgentSpec
from tests.conftest import EXAMPLES, assert_golden
from tests.fixtures_tools import demo_catalog, full_catalog

KEY = "sk-proj-" + "a1B2c3D4e5F6g7H8i9J0" * 3


def calc() -> AgentSpec:
    return AgentSpec.load(EXAMPLES / "calculator.agent.yaml")


def personal() -> AgentSpec:
    return AgentSpec.load(EXAMPLES / "personal_automation.agent.yaml")


def fabric_json(c, **kw) -> str:
    return json.dumps(to_fabric_config(c, adapter_dir="/adapter", **kw), indent=2) + "\n"


def test_golden_calculator_tool_calling():
    c = compile_agent(calc(), demo_catalog())
    assert c.model.agent_mode == "tool_calling"
    assert_golden("calculator.nat.yaml", to_nat_yaml(c))
    assert_golden("calculator.fabric.json", fabric_json(c))


def test_golden_calculator_react():
    spec = calc().model_copy(update={"model": calc().model.model_copy(update={"agent_mode": "react"})})
    c = compile_agent(spec, demo_catalog())
    assert c.model.agent_mode == "react"
    assert_golden("calculator.react.nat.yaml", to_nat_yaml(c))
    assert_golden("calculator.react.fabric.json", fabric_json(c))


def test_golden_personal_automation_with_relay():
    c = compile_agent(personal(), full_catalog())
    assert_golden("personal.nat.yaml", to_nat_yaml(c))
    assert_golden("personal.fabric.json", fabric_json(c, relay_output_dir="/out/relay"))


def test_compile_is_deterministic():
    a, b = compile_agent(calc(), demo_catalog()), compile_agent(calc(), demo_catalog())
    assert a == b and to_nat_yaml(a) == to_nat_yaml(b) and fabric_json(a) == fabric_json(b)


def test_each_server_exposes_only_the_tools_the_spec_asked_for():
    spec = AgentSpec.from_dict(
        {"name": "x", "model": {"provider": "openai", "model": "gpt-4.1-mini"}, "tools": ["demo.add_numbers"]}
    )
    nat = to_nat_workflow(compile_agent(spec, demo_catalog()))
    assert nat["function_groups"]["demo"]["include"] == ["add_numbers"]  # not count_words / get_current_time
    fab = to_fabric_config(compile_agent(spec, demo_catalog()))
    assert fab["mcp"]["servers"]["demo"]["allowed_tools"] == ["add_numbers"]


def test_no_secret_ever_reaches_the_output():
    spec = AgentSpec.from_dict(
        {
            "name": "x",
            "model": {"provider": "openai", "model": "gpt-4.1-mini", "credential_ref": "env://OPENAI_API_KEY"},
        }
    )
    c = compile_agent(spec, demo_catalog(), environ={"OPENAI_API_KEY": KEY})
    blob = to_nat_yaml(c) + fabric_json(c) + repr(c) + c.model_dump_json()
    assert KEY not in blob
    assert (
        "${OPENAI_API_KEY}" in to_nat_yaml(c)
        and to_fabric_config(c)["models"]["default"]["api_key_env"] == "OPENAI_API_KEY"
    )


def test_compiling_needs_no_key_at_all():
    compile_agent(calc(), demo_catalog(), environ={})  # a missing key is a run-time problem, not a compile-time one


def test_secret_reference_maps_to_a_predictable_variable_with_a_warning():
    c = compile_agent(personal(), full_catalog())
    assert c.model.api_key_env == "AGENTBUILDER_SECRET_LLM_PRIMARY"
    assert any("AGENTBUILDER_SECRET_LLM_PRIMARY" in w for w in c.warnings)


def test_unknown_tool_ids_are_a_clear_compile_error():
    with pytest.raises(CompileError, match=r"gmail\.read"):
        compile_agent(personal(), demo_catalog())


def test_tier3_tools_are_refused_by_default_and_allowed_when_explicitly_relaxed():
    data = {"name": "x", "model": {"provider": "openai", "model": "gpt-4.1-mini"}, "tools": ["finance.refund"]}
    with pytest.raises(CompileError, match="tier 3"):
        compile_agent(AgentSpec.from_dict(data), full_catalog())
    relaxed = AgentSpec.from_dict({**data, "approvals": {"tier3_destructive": "require_human"}})
    assert compile_agent(relaxed, full_catalog()).tools[0].risk_tier == 3


def test_unenforced_approvals_are_warned_about_loudly():
    c = compile_agent(personal(), full_catalog())
    assert any("calendar.create_event" in w and "NOT enforced" in w for w in c.warnings)
    quiet = AgentSpec.from_dict(
        {"name": "x", "model": {"provider": "openai", "model": "m"}, "tools": ["demo.add_numbers"]}
    )
    assert compile_agent(quiet, demo_catalog()).warnings == []


def test_mutating_tools_are_warned_about_even_when_a_sandbox_preset_is_set():
    base = {"name": "x", "model": {"provider": "openai", "model": "m"}, "tools": ["gmail.send_draft"]}
    for extra in ({}, {"sandbox": {"policy_preset": "p"}}):
        warnings = compile_agent(AgentSpec.from_dict({**base, **extra}), full_catalog()).warnings
        assert any(
            "gmail.send_draft" in w and "nothing restricts it yet" in w for w in warnings
        )  # a preset changes nothing yet


def test_fields_that_are_accepted_but_not_applied_are_listed():
    spec = AgentSpec.from_dict(
        {
            "name": "x",
            "model": {
                "provider": "openai",
                "model": "m",
                "max_tokens": 100,
                "reliability": {"repair": {"steps": ["tool_names"]}},
                "routing": {"provider": "switchyard", "algorithm": "escalation"},
            },
            "guardrails": {"profile": "strict"},
            "sandbox": {"policy_preset": "p"},
            "evals": {"suite": "s"},
            "knowledge": {"collections": ["kb"]},
            "channels": [{"type": "web_chat"}],
        }
    )
    (warning,) = [w for w in compile_agent(spec, demo_catalog()).warnings if "NOT applied yet" in w]
    for field in (
        "guardrails.profile",
        "model.reliability",
        "model.routing",
        "model.max_tokens",
        "sandbox.policy_preset",
        "evals.suite",
        "knowledge",
        "channels",
    ):
        assert field in warning, field
    assert "integrations" not in warning and "voice" not in warning  # only what was actually set


def test_defaults_do_not_trigger_the_not_applied_warning():
    spec = AgentSpec.from_dict(
        {"name": "x", "model": {"provider": "openai", "model": "m"}, "tools": ["demo.add_numbers"]}
    )
    assert compile_agent(spec, demo_catalog()).warnings == []


def test_max_tokens_is_not_emitted_because_the_nat_adapter_rejects_it():
    spec = AgentSpec.from_dict({"name": "x", "model": {"provider": "openai", "model": "m", "max_tokens": 50}})
    c = compile_agent(spec, demo_catalog())
    assert "max_tokens" not in str(to_nat_workflow(c)) and "max_tokens" not in str(to_fabric_config(c))


def test_instructions_are_rendered_and_mapped_for_both_agent_types():
    for mode in ("react", "tool_calling"):
        spec = calc().model_copy(update={"model": calc().model.model_copy(update={"agent_mode": mode})})
        c = compile_agent(spec, demo_catalog())
        assert c.instructions.startswith("A careful assistant.\n\nRules:\n- Use the tools")
        assert to_nat_workflow(c)["workflow"]["additional_instructions"] == c.instructions
        assert to_fabric_config(c)["instructions"]["system"] == {"content": c.instructions, "mode": "append"}


def test_react_only_settings_stay_out_of_tool_calling_configs():
    c = compile_agent(calc(), demo_catalog())
    assert "parse_agent_response_max_retries" not in to_nat_workflow(c)["workflow"]
    assert "parse_agent_response_max_retries" not in to_fabric_config(c)["workflow"]["settings"]
    r = calc().model_copy(update={"model": calc().model.model_copy(update={"agent_mode": "react"})})
    assert to_nat_workflow(compile_agent(r, demo_catalog()))["workflow"]["parse_agent_response_max_retries"] == 3


def test_ollama_needs_no_key_and_nvidia_hosted_maps_its_provider():
    ollama = AgentSpec.from_dict({"name": "x", "model": {"provider": "ollama", "model": "llama3"}})
    c = compile_agent(ollama, demo_catalog())
    assert c.model.api_key_env is None and "api_key" not in to_nat_workflow(c)["llms"]["main_llm"]
    assert "api_key_env" not in to_fabric_config(c)["models"]["default"]
    nv = AgentSpec.from_dict(
        {"name": "x", "model": {"provider": "nvidia_hosted", "model": "m", "credential_ref": "env://NVIDIA_API_KEY"}}
    )
    assert to_fabric_config(compile_agent(nv, demo_catalog()))["models"]["default"]["provider"] == "nvidia"


def test_relay_option_adds_telemetry_settings_and_an_artifact_root():
    cfg = to_fabric_config(compile_agent(calc(), demo_catalog()), relay_output_dir="/o")
    assert cfg["telemetry"] == {"providers": {"relay": {}}} and cfg["runtime"]["artifacts"] == "/o/fabric-artifacts"
    assert cfg["relay"]["observability"]["atif"]["enabled"] is True
    plain = to_fabric_config(compile_agent(calc(), demo_catalog()))
    assert "relay" not in plain and "telemetry" not in plain and "artifacts" not in plain["runtime"]


def test_nat_yaml_is_valid_yaml_with_a_do_not_edit_header():
    text = to_nat_yaml(compile_agent(calc(), demo_catalog()))
    assert (
        text.startswith("# Generated by agentbuilder")
        and yaml.safe_load(text)["workflow"]["_type"] == "tool_calling_agent"
    )
