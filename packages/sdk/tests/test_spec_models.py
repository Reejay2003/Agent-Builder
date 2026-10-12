import pytest

from agentbuilder.spec import AgentSpec, SpecError
from tests.conftest import minimal


def test_minimal_spec_gets_safe_defaults():
    spec = AgentSpec.from_dict(minimal())
    assert spec.spec_version == 1
    assert spec.model.agent_mode == "auto"
    assert spec.guardrails.profile == "standard"
    assert spec.approvals.tier2_external_comms == "require_human"  # safe by default
    assert spec.approvals.tier3_destructive == "block"
    assert spec.tools == []


def test_unknown_fields_are_errors():
    with pytest.raises(SpecError) as e:
        AgentSpec.from_dict({**minimal(), "toolz": []})
    assert "toolz" in str(e.value)
    with pytest.raises(SpecError):
        AgentSpec.from_dict({"name": "demo", "model": {"provider": "openai", "model": "m", "temprature": 0}})


@pytest.mark.parametrize("name", ["", "Has Caps", "-leading", "x" * 64, "has space", "ünï"])
def test_bad_names_rejected(name):
    with pytest.raises(SpecError):
        AgentSpec.from_dict({**minimal(), "name": name})


@pytest.mark.parametrize(
    "ref", ["sk-proj-abcdefghijklmnopqrstuvwxyz0123456789", "my-secret", "http://x", "secret://", ""]
)
def test_credentials_must_be_references(ref):
    data = minimal()
    data["model"]["credential_ref"] = ref
    with pytest.raises(SpecError) as e:
        AgentSpec.from_dict(data)
    assert "credential_ref" in str(e.value)


@pytest.mark.parametrize("ref", ["secret://llm/primary", "env://LLM_API_KEY", "secret://a.b-c_d/e"])
def test_reference_forms_accepted(ref):
    data = minimal()
    data["model"]["credential_ref"] = ref
    assert AgentSpec.from_dict(data).model.credential_ref == ref


@pytest.mark.parametrize(
    "key",
    [
        "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
        "sk-or-v1-0123456789abcdef0123456789abcdef",
        "AKIAABCDEFGHIJKLMNOP",
        "ghp_abcdefghijklmnopqrstuvwxyz0123",
    ],
)
def test_key_like_values_rejected_anywhere(key):
    data = minimal()
    data["instructions"] = {"rules": [f"use this key: {key}"]}
    with pytest.raises(SpecError) as e:
        AgentSpec.from_dict(data)
    assert "instructions.rules[0]" in str(e.value) or "looks like an API key" in str(e.value)
    data2 = minimal()
    data2["metadata"] = {"note": key}
    with pytest.raises(SpecError):
        AgentSpec.from_dict(data2)


def test_ordinary_text_is_not_flagged():
    data = minimal()
    data["instructions"] = {"persona": "Use the sk tool. A skeleton key is fine. sk-short"}
    AgentSpec.from_dict(data)


def test_duplicate_tool_ids_rejected():
    with pytest.raises(SpecError) as e:
        AgentSpec.from_dict({**minimal(), "tools": ["gmail.read", {"id": "gmail.read"}]})
    assert "duplicate tool ids: gmail.read" in str(e.value)


@pytest.mark.parametrize("tool_id", ["Gmail.Read", "gmail..read", ".gmail", "gmail read", ""])
def test_bad_tool_ids_rejected(tool_id):
    with pytest.raises(SpecError):
        AgentSpec.from_dict({**minimal(), "tools": [tool_id]})


def test_tool_shorthand_and_object_forms_are_equal():
    a = AgentSpec.from_dict({**minimal(), "tools": ["demo.add_numbers"]})
    b = AgentSpec.from_dict({**minimal(), "tools": [{"id": "demo.add_numbers", "settings": {}}]})
    assert a == b


def test_openai_compatible_requires_base_url():
    data = minimal()
    data["model"] = {"provider": "openai_compatible", "model": "x"}
    with pytest.raises(SpecError) as e:
        AgentSpec.from_dict(data)
    assert "base_url" in str(e.value)
    data["model"]["base_url"] = "not a url"
    with pytest.raises(SpecError):
        AgentSpec.from_dict(data)
    data["model"]["base_url"] = "http://localhost:11434/v1"
    assert AgentSpec.from_dict(data).model.base_url == "http://localhost:11434/v1"


def test_value_ranges():
    for patch in (
        {"temperature": 3},
        {"temperature": -1},
        {"max_tokens": 0},
        {"agent_mode": "magic"},
        {"provider": "nope"},
    ):
        data = minimal()
        data["model"].update(patch)
        with pytest.raises(SpecError):
            AgentSpec.from_dict(data)


def test_specs_are_immutable():
    spec = AgentSpec.from_dict(minimal())
    with pytest.raises(Exception):  # noqa: B017 - pydantic raises ValidationError for frozen models
        spec.name = "other"  # type: ignore[misc]


def test_error_lists_every_problem_with_its_path():
    with pytest.raises(SpecError) as e:
        AgentSpec.from_dict({"name": "BAD", "model": {"provider": "nope", "model": ""}, "tools": ["X"]})
    problems = " | ".join(e.value.problems)
    assert (
        "name:" in problems and "model.provider:" in problems and "model.model:" in problems and "tools.0" in problems
    )
