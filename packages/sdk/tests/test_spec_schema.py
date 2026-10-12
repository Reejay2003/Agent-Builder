import json

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

from agentbuilder.spec.schema import SCHEMA_PATH, agent_spec_json_schema, schema_text


def test_committed_schema_is_up_to_date():
    # If this fails after an intentional model change, run: python -m agentbuilder.spec.schema --write
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_text()


def test_schema_is_itself_valid():
    Draft202012Validator.check_schema(agent_spec_json_schema())


def test_example_specs_validate_against_the_schema(example_paths):
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    for path in example_paths:
        validator.validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "bad",
    [
        {"model": {"provider": "openai", "model": "m"}},  # missing name
        {"name": "x", "model": {"provider": "nope", "model": "m"}},
        {"name": "x", "model": {"provider": "openai", "model": "m"}, "extra": 1},
    ],
)
def test_schema_rejects_what_the_models_reject(bad):
    with pytest.raises(ValidationError):
        Draft202012Validator(agent_spec_json_schema()).validate(bad)
