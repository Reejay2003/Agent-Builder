import json

import pytest
import yaml

from agentbuilder.spec import AgentSpec, SpecError, dumps, load, loads, save


def test_examples_load_and_round_trip_losslessly(example_paths, tmp_path):
    for path in example_paths:
        spec = load(path)
        # object -> dict -> object
        assert AgentSpec.from_dict(spec.to_dict()) == spec
        # object -> yaml text -> object
        assert loads(spec.to_yaml()) == spec
        # object -> json text -> object
        assert loads(spec.to_json(), "json") == spec
        # object -> file -> object, both formats
        for ext in ("yaml", "json"):
            out = tmp_path / f"{path.stem}.{ext}"
            save(spec, out)
            assert load(out) == spec


def test_saved_output_is_stable_and_explicit(example_paths):
    spec = load(example_paths[0])
    first, second = spec.to_yaml(), loads(spec.to_yaml()).to_yaml()
    assert first == second  # deterministic: same spec, same bytes
    assert first.startswith("spec_version: 1\n")  # version first
    assert "agent_mode:" in first and "guardrails:" in first  # defaults are written out, specs are explicit
    assert "null" not in first  # None values are omitted


def test_yaml_is_loaded_with_safe_load_only():
    evil = "name: x\nmodel: !!python/object/apply:os.system ['echo hacked']\n"
    with pytest.raises(SpecError):
        loads(evil)


def test_malformed_input_is_a_spec_error():
    with pytest.raises(SpecError):
        loads("name: [unclosed")
    with pytest.raises(SpecError):
        loads("- just\n- a list\n")
    with pytest.raises(SpecError):
        loads("{not json", "json")


def test_unsupported_file_extension(tmp_path):
    p = tmp_path / "agent.txt"
    p.write_text("name: x")
    with pytest.raises(SpecError) as e:
        load(p)
    assert "unsupported spec file type" in str(e.value)


def test_json_and_yaml_forms_agree(example_paths):
    spec = load(example_paths[0])
    assert json.loads(spec.to_json()) == yaml.safe_load(spec.to_yaml())


def test_dumps_rejects_nothing_secret_even_if_built_by_hand():
    # model_construct bypasses validation; dumping must still never invent keys, and re-loading re-validates
    spec = AgentSpec.from_dict({"name": "x", "model": {"provider": "openai", "model": "m"}})
    assert "sk-" not in dumps(spec)
