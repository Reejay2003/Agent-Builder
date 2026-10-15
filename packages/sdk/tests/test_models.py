import pytest

from agentbuilder.models import (
    CredentialError,
    Model,
    Secret,
    lookup,
    redact,
    resolve_agent_mode,
    resolve_credential,
    resolve_model,
    secret_env_name,
    tier_for_rate,
)
from agentbuilder.models.capabilities import table
from agentbuilder.spec import AgentSpec, ModelSpec

KEY = "sk-proj-" + "a1B2c3D4e5F6g7H8i9J0" * 3


def test_secret_never_prints_its_value():
    s = Secret(KEY)
    assert KEY not in repr(s) and KEY not in str(s) and KEY not in f"{s}" and KEY not in f"{[s]}"
    assert s.reveal() == KEY and bool(s) and not Secret("")


def test_env_reference_resolves_and_trims_a_trailing_newline():
    assert resolve_credential("env://K", environ={"K": KEY + "\n"}).reveal() == KEY
    assert resolve_credential(None) is None


@pytest.mark.parametrize("value", ["sk-proj-abc def", "sk-proj-abc\ndef", "sk-proj-abc\tdef"])
def test_key_with_whitespace_inside_is_refused_with_a_helpful_message(value):
    with pytest.raises(CredentialError, match="unbroken line") as e:
        resolve_credential("env://K", environ={"K": value})
    assert "abc" not in str(e.value) and "def" not in str(e.value)  # the value is never echoed


@pytest.mark.parametrize("env", [{}, {"K": ""}, {"K": "   "}])
def test_missing_or_empty_key_is_refused(env):
    with pytest.raises(CredentialError):
        resolve_credential("env://K", environ=env)


def test_raw_keys_and_bad_schemes_are_refused():
    for ref in (KEY, "http://x", "file:///etc/passwd", "env:/K"):
        with pytest.raises(CredentialError, match="by reference only"):
            resolve_credential(ref, environ={})


def test_secret_references_use_stores_then_a_predictable_env_name():
    class Store:
        def get(self, name):
            return {"llm/primary": KEY}.get(name)

    assert resolve_credential("secret://llm/primary", stores=[Store()], environ={}).reveal() == KEY
    assert secret_env_name("llm/primary") == "AGENTBUILDER_SECRET_LLM_PRIMARY"
    env = {"AGENTBUILDER_SECRET_LLM_OTHER": KEY}
    assert resolve_credential("secret://llm/other", environ=env).reveal() == KEY
    with pytest.raises(CredentialError, match="AGENTBUILDER_SECRET_NOPE"):
        resolve_credential("secret://nope", environ={})


def test_redact_scrubs_values_but_not_short_noise():
    assert redact(f"Authorization: Bearer {KEY} done", [Secret(KEY)]) == "Authorization: Bearer **** done"
    assert redact("abc", [Secret("abc"), None]) == "abc"  # too short to be a real key: left alone


def test_constructors_reference_provider_conventional_env_vars():
    assert Model.openai("gpt-4.1-mini").credential_ref == "env://OPENAI_API_KEY"
    assert Model.openrouter("x/y:free").credential_ref == "env://OPENROUTER_API_KEY"
    assert Model.openai("m", api_key_env="LLM_API_KEY").credential_ref == "env://LLM_API_KEY"
    assert Model.ollama("llama3").credential_ref is None
    c = Model.custom("m", base_url="http://localhost:8000/v1")
    assert c.provider == "openai_compatible" and c.credential_ref == "env://LLM_API_KEY"
    with pytest.raises(TypeError):
        Model.custom("m")  # type: ignore[call-arg]  # base_url is required


def test_constructors_build_valid_specs_that_round_trip():
    spec = AgentSpec(name="a", model=Model.openai("gpt-4.1-mini", temperature=0))
    assert AgentSpec.loads(spec.to_yaml()) == spec


def test_resolve_model_fills_defaults_and_hides_the_key():
    r = resolve_model(Model.openai("gpt-4.1-mini"), environ={"OPENAI_API_KEY": KEY})
    assert r.base_url == "https://api.openai.com/v1" and r.api_key_env == "OPENAI_API_KEY" and r.api_key.reveal() == KEY
    assert KEY not in repr(r)
    local = resolve_model(Model.ollama("llama3"), environ={})
    assert local.base_url == "http://localhost:11434/v1" and local.api_key is None
    custom = resolve_model(Model.custom("m", base_url="http://x:1/v1/", api_key_env="K"), environ={"K": KEY})
    assert custom.base_url == "http://x:1/v1"  # trailing slash trimmed


def test_resolve_model_can_skip_the_key_for_compile_and_validate():
    r = resolve_model(Model.openai("gpt-4.1-mini"), environ={}, need_key=False)
    assert r.api_key is None and r.api_key_env == "OPENAI_API_KEY"
    with pytest.raises(CredentialError):
        resolve_model(Model.openai("gpt-4.1-mini"), environ={})


def test_tier_thresholds():
    assert [tier_for_rate(r) for r in (1.0, 0.99, 0.98, 0.95, 0.9, 0.85, 0.84)] == [
        "strong",
        "strong",
        "standard",
        "standard",
        "limited",
        "limited",
        "unsuitable",
    ]


def test_capability_table_is_consistent_with_its_own_rules():
    for c in table():
        if c.tier_source == "measured":
            best = c.modes[c.recommended_agent_mode]  # type: ignore[index]
            assert c.tier == tier_for_rate(best.rate), c.model
        assert c.evidence, f"{c.model}: every row needs evidence"


def test_lookup_exact_prefix_and_unknown():
    assert lookup("openai", "gpt-4.1-mini").tier == "strong"
    assert lookup("openai", "gpt-4.1-mini-2025-04-14").model == "gpt-4.1-mini"  # dated snapshot -> family
    assert lookup("openai", "gpt-4.1-nano-20250414").model == "gpt-4.1-nano"  # compact date form too
    for guess in ("gpt-4.1-mini-experimental-preview", "gpt-4.1-minimal", "gpt-4.1-mini-2025"):
        assert lookup("openai", guess) is None, guess  # a shared name prefix is a guess, not evidence
    assert lookup("openai", "totally-new") is None and lookup("ollama", "gpt-4.1-mini") is None


def test_auto_agent_mode_follows_the_table_and_explicit_always_wins():
    assert resolve_agent_mode(Model.openai("gpt-4.1-nano")) == "tool_calling"
    assert resolve_agent_mode(Model.openai("never-heard-of-it")) == "tool_calling"  # sensible default for unknown
    assert resolve_agent_mode(Model.openai("gpt-4.1-mini", agent_mode="react")) == "react"
    assert resolve_agent_mode(ModelSpec(provider="openai", model="x", agent_mode="tool_calling")) == "tool_calling"
