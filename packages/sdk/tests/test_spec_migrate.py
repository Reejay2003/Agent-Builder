import pytest

from agentbuilder.spec import AgentSpec, SpecVersionError, migrate
from tests.conftest import minimal


def test_newer_spec_version_is_refused():
    with pytest.raises(SpecVersionError) as e:
        AgentSpec.from_dict({**minimal(), "spec_version": 2})
    assert "newer than this SDK" in str(e.value)


@pytest.mark.parametrize("bad", [0, -1, "1", True, 1.5])
def test_invalid_versions_refused(bad):
    with pytest.raises(SpecVersionError):
        migrate.upgrade({**minimal(), "spec_version": bad})


def test_missing_version_defaults_to_1():
    assert AgentSpec.from_dict(minimal()).spec_version == 1


def test_migration_chain_runs_in_order(monkeypatch):
    calls = []

    def v1_to_v2(d):
        calls.append("1->2")
        return {**d, "renamed": d.pop("old")}

    def v2_to_v3(d):
        calls.append("2->3")
        return d

    monkeypatch.setattr(migrate, "MIGRATIONS", {1: v1_to_v2, 2: v2_to_v3})
    out = migrate.upgrade({"spec_version": 1, "old": "x"}, target=3)
    assert calls == ["1->2", "2->3"] and out["spec_version"] == 3 and out["renamed"] == "x"


def test_missing_migration_step_is_an_error(monkeypatch):
    monkeypatch.setattr(migrate, "MIGRATIONS", {})
    with pytest.raises(SpecVersionError):
        migrate.upgrade({"spec_version": 1}, target=2)
