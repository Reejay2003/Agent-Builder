"""Compiler D: one allow/ask/deny rule (tool_decision), its OPA bundle, and the NeMo Guardrails config."""

import json
import shutil
import subprocess

import pytest
import yaml

from agentbuilder.approvals import with_approvals
from agentbuilder.compile import (
    compile_agent,
    needs_approval,
    to_guardrails_config,
    to_opa_bundle,
    tool_decision,
)
from agentbuilder.library import personal_catalog
from agentbuilder.spec import AgentSpec

OPA_IMAGE = "openpolicyagent/opa:1.0.0"
TOOLS = ["gmail.read", "gmail.send_draft", "calendar.create_event", "sheets.read"]


def agent(**over):
    data = {"name": "a", "model": {"provider": "openai", "model": "m", "credential_ref": "env://K"}, "tools": TOOLS}
    for key, value in over.items():
        section, _, field = key.partition("__")
        data.setdefault(section, {})[field] = value
    return compile_agent(AgentSpec.from_dict(data), personal_catalog())


def decisions(c):
    return {t.id: tool_decision(c, t) for t in c.tools}


def test_the_rule_follows_the_tiers_the_approval_settings_and_limited_mode():
    assert decisions(agent()) == {
        "gmail.read": "allow",
        "gmail.send_draft": "allow",
        "calendar.create_event": "ask",
        "sheets.read": "allow",
    }
    assert decisions(agent(approvals__tier2_external_comms="allow"))["calendar.create_event"] == "allow"
    limited = agent(model__reliability={"mode": "limited"})
    assert decisions(limited)["gmail.send_draft"] == "ask"  # a weak model's drafts are checked too
    assert needs_approval(limited) == ["gmail.send_draft", "calendar.create_event"]
    assert any("limited mode" in w for w in limited.warnings)
    assert not any("model.reliability" in w for w in limited.warnings)  # limited mode is applied now


def test_limited_mode_makes_the_tool_server_ask_for_tier1_too(tmp_path):
    c = with_approvals(agent(model__reliability={"mode": "limited"}), tmp_path)
    gmail = next(s for s in c.servers if s.name == "gmail")
    assert gmail.args[gmail.args.index("--approve") + 1] == "gmail.send_draft"


def test_the_bundle_carries_the_same_decisions_and_no_secret():
    c = agent(model__reliability={"mode": "limited"})
    bundle = to_opa_bundle(c)
    data = json.loads(bundle["data.json"])["agentbuilder"]
    assert {k: v["decision"] for k, v in data["tools"].items()} == decisions(c)
    assert "env://" not in bundle["data.json"] and "K" not in json.dumps(data["tools"])


def _opa_cases(c):
    """(input, expected) pairs: every tool live, live and approved, in mock mode, plus an unknown tool."""
    for t in c.tools:
        d = tool_decision(c, t)
        yield {"tool": t.id, "mock": False, "approved": False}, d
        yield {"tool": t.id, "mock": False, "approved": True}, "allow" if d == "ask" else d
        yield {"tool": t.id, "mock": True}, "allow"
    yield {"tool": "evil.tool", "mock": True}, "deny"
    yield {"tool": "evil.tool", "mock": False, "approved": True}, "deny"


def test_a_real_opa_gives_exactly_the_sdks_answer_for_every_case(tmp_path):
    if not shutil.which("docker") or subprocess.run(["docker", "info"], capture_output=True, check=False).returncode:
        pytest.skip("docker is not available to run OPA")
    for c in (agent(), agent(model__reliability={"mode": "limited"}), agent(approvals__tier2_external_comms="allow")):
        for name, content in to_opa_bundle(c).items():
            (tmp_path / name).write_text(content)
        cases = "\n".join(
            f"test_case_{i} if {{\n\tdecision == {json.dumps(want)} with input as {json.dumps(given)}\n}}\n"
            for i, (given, want) in enumerate(_opa_cases(c))
        )
        (tmp_path / "parity_test.rego").write_text(f"package agentbuilder\n\nimport rego.v1\n\n{cases}")
        out = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{tmp_path}:/b:ro", OPA_IMAGE, "test", "/b", "-v"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if "Unable to find image" in out.stderr and out.returncode and "pull" in out.stderr.lower():
            pytest.skip(f"could not pull {OPA_IMAGE}")
        assert out.returncode == 0, out.stdout + out.stderr
        n = len(list(_opa_cases(c)))
        assert f"PASS: {n}/{n}" in out.stdout


@pytest.mark.parametrize(("profile", "has_output"), [("relaxed", False), ("standard", True), ("strict", True)])
def test_the_guardrails_config_per_profile_and_the_input_check_is_always_on(profile, has_output, monkeypatch):
    c = agent(guardrails__profile=profile)
    cfg = to_guardrails_config(c)
    assert cfg["rails"]["input"]["flows"] == ["self check input"]  # the floor
    assert ("output" in cfg["rails"]) is has_output
    assert cfg["models"][0]["api_key_env_var"] == c.model.api_key_env  # a variable name, never a value
    assert ("medical" in cfg["prompts"][0]["content"]) is (profile == "strict")
    nemoguardrails = pytest.importorskip("nemoguardrails")
    monkeypatch.setenv(c.model.api_key_env, "dummy")  # the library insists the variable exists
    loaded = nemoguardrails.RailsConfig.from_content(yaml_content=yaml.safe_dump(cfg))
    assert loaded.rails.input.flows == ["self check input"]
    assert {p.task for p in loaded.prompts} >= {"self_check_input"}


def test_the_compiler_still_says_guardrails_are_not_enforced():
    assert any("guardrails.profile" in w and "NOT applied" in w for w in agent().warnings)
