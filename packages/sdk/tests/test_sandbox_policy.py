import pytest
import yaml

from agentbuilder.compile import (
    CompileError,
    compile_agent,
    to_openshell_policy,
    to_openshell_provider_profile,
    to_openshell_yaml,
)
from agentbuilder.spec import AgentSpec
from agentbuilder.tools import ToolCatalog, tool
from tests.conftest import EXAMPLES, assert_golden
from tests.fixtures_tools import demo_catalog, full_catalog


def personal():
    return compile_agent(AgentSpec.load(EXAMPLES / "personal_automation.agent.yaml"), full_catalog())


def spec_with(tools, model=None):
    model = model or {"provider": "openai", "model": "gpt-4.1-mini", "credential_ref": "env://OPENAI_API_KEY"}
    return AgentSpec.from_dict({"name": "x", "model": model, "tools": tools})


def test_golden_policy_and_provider_profile():
    c = personal()
    assert_golden("personal.openshell-policy.yaml", to_openshell_yaml(to_openshell_policy(c), "sandbox policy"))
    assert_golden(
        "personal.openshell-provider.yaml", to_openshell_yaml(to_openshell_provider_profile(c), "provider profile")
    )


def test_each_tool_server_gets_exactly_its_declared_hosts():
    net = to_openshell_policy(personal())["network_policies"]
    hosts = {k: [e["host"] for e in v["endpoints"]] for k, v in net.items()}
    assert hosts == {
        "tools_gmail": ["gmail.googleapis.com"],
        "tools_calendar": ["www.googleapis.com"],
        "tools_sheets": ["sheets.googleapis.com"],
        "tools_web": ["search.example.org"],
    }  # demo tools declare no hosts, so they get no network rule at all


def test_read_only_tools_get_read_only_access_and_writing_tools_read_write():
    net = to_openshell_policy(personal())["network_policies"]
    assert net["tools_sheets"]["endpoints"][0]["access"] == "read-only"  # sheets.read
    assert net["tools_web"]["endpoints"][0]["access"] == "read-only"  # web.search
    assert net["tools_gmail"]["endpoints"][0]["access"] == "read-write"  # send_draft is tier 1
    assert net["tools_calendar"]["endpoints"][0]["access"] == "read-write"  # create_event is tier 2


def test_allowed_binaries_are_the_parameter_not_a_hardcoded_path():
    net = to_openshell_policy(personal(), binaries=["/custom/python"])["network_policies"]
    assert all(v["binaries"] == [{"path": "/custom/python"}] for v in net.values())


def test_agents_without_network_tools_get_no_network_rules_at_all():
    c = compile_agent(spec_with(["demo.add_numbers"]), demo_catalog())
    policy = to_openshell_policy(c)
    assert "network_policies" not in policy  # deny by default
    assert policy["process"] == {"run_as_user": "1000", "run_as_group": "1000"}


def test_file_paths_follow_what_the_tool_does_with_them():
    @tool(namespace="files", description="Read reports.", fs_paths=["/data/reports"])
    def read_report(name: str) -> str:
        return ""

    @tool(namespace="files", description="Save a note.", risk=1, fs_paths=["/data/notes"])
    def save_note(text: str) -> str:
        return ""

    cat = ToolCatalog().add_tools("files", [read_report, save_note], command="python")
    fs = to_openshell_policy(compile_agent(spec_with(["files.read_report", "files.save_note"]), cat))[
        "filesystem_policy"
    ]
    assert "/data/notes" in fs["read_write"] and "/data/reports" not in fs["read_write"]
    assert "/data/reports" in fs["read_only"] and "/tmp" in fs["read_write"]
    assert set(fs["read_only"]).isdisjoint(fs["read_write"])


def test_policy_is_deterministic_and_valid_yaml():
    a, b = personal(), personal()
    assert to_openshell_yaml(to_openshell_policy(a), "p") == to_openshell_yaml(to_openshell_policy(b), "p")
    assert yaml.safe_load(to_openshell_yaml(to_openshell_policy(a), "p"))["version"] == 1


def test_provider_profile_describes_how_the_key_is_delivered_without_containing_it():
    c = compile_agent(
        spec_with(["demo.add_numbers"]), demo_catalog(), environ={"OPENAI_API_KEY": "sk-proj-" + "a1B2c3D4" * 5}
    )
    p = to_openshell_provider_profile(c)
    assert p["id"] == "agentbuilder-openai" and p["credentials"][0]["env_vars"] == ["OPENAI_API_KEY"]
    assert p["endpoints"][0]["host"] == "api.openai.com" and p["endpoints"][0]["port"] == 443
    assert "a1B2c3D4" not in str(p)  # a name, never a value


def test_no_key_means_no_provider_and_loopback_models_are_refused():
    ollama = compile_agent(spec_with(["demo.add_numbers"], {"provider": "ollama", "model": "llama3"}), demo_catalog())
    assert ollama.model.api_key_env is None and to_openshell_provider_profile(ollama) is None
    local = compile_agent(
        spec_with(
            ["demo.add_numbers"],
            {
                "provider": "openai_compatible",
                "model": "m",
                "base_url": "http://localhost:8000/v1",
                "credential_ref": "env://K",
            },
        ),
        demo_catalog(),
    )
    with pytest.raises(CompileError, match="loopback"):
        to_openshell_provider_profile(local)


def test_custom_port_and_scheme_are_respected():
    c = compile_agent(
        spec_with(
            ["demo.add_numbers"],
            {
                "provider": "openai_compatible",
                "model": "m",
                "base_url": "http://gateway.internal:8080/v1",
                "credential_ref": "env://K",
            },
        ),
        demo_catalog(),
    )
    (endpoint,) = to_openshell_provider_profile(c)["endpoints"]
    assert (endpoint["host"], endpoint["port"]) == ("gateway.internal", 8080)
