import json

import pytest

from agentbuilder.tools import (
    McpServerBinding,
    Tool,
    ToolArgumentError,
    ToolCatalog,
    ToolDefinitionError,
    ToolManifest,
    UnknownToolError,
    manifests_document,
    tool,
)


@tool(namespace="demo", description="Add two numbers.", mock_response=3.0)
def add_numbers(a: float, b: float) -> float:
    return a + b


@tool(namespace="demo")
def count_words(text: str, lowercase: bool = False) -> int:
    """Count the words in a text.

    Extra detail that users do not see in the wizard.
    """
    return len((text.lower() if lowercase else text).split())


def test_safe_defaults_and_derived_manifest():
    m = add_numbers.manifest
    assert (m.id, m.mcp_name, m.risk_tier, m.side_effects) == ("demo.add_numbers", "add_numbers", 0, "none")
    assert m.egress_hosts == [] and m.fs_paths == [] and m.creds_required == []
    assert m.description_plain == "Add two numbers."
    assert count_words.manifest.description_plain == "Count the words in a text."  # first docstring line only


def test_input_schema_comes_from_type_hints():
    s = add_numbers.input_schema
    assert s["type"] == "object" and set(s["properties"]) == {"a", "b"} and s["required"] == ["a", "b"]
    assert s["properties"]["a"]["type"] == "number"
    cw = count_words.input_schema
    assert cw["required"] == ["text"] and cw["properties"]["lowercase"]["default"] is False
    assert "title" not in s


def test_tool_still_behaves_like_the_function():
    assert add_numbers(2, 3) == 5
    assert isinstance(add_numbers, Tool) and add_numbers.id == "demo.add_numbers"


def test_call_validates_arguments():
    assert add_numbers.call({"a": 1, "b": 2.5}) == 3.5
    assert count_words.call({"text": "A b", "lowercase": True}) == 2
    with pytest.raises(ToolArgumentError, match=r"demo\.add_numbers"):
        add_numbers.call({"a": "x", "b": 1})
    with pytest.raises(ToolArgumentError):
        add_numbers.call({"a": 1})  # missing b
    with pytest.raises(ToolArgumentError):
        add_numbers.call({"a": 1, "b": 2, "c": 3})  # unknown argument


def test_definition_errors():
    with pytest.raises(ToolDefinitionError, match="description"):

        @tool
        def no_doc(a: int) -> int:
            return a

    with pytest.raises(ToolDefinitionError, match="annotation"):

        @tool(description="x")
        def untyped(a) -> int:  # type: ignore[no-untyped-def]
            return a

    with pytest.raises(ToolDefinitionError, match=r"\*args"):

        @tool(description="x")
        def variadic(*a: int) -> int:
            return 0

    with pytest.raises(ToolDefinitionError, match="risk"):

        @tool(description="x", risk=7)
        def bad_risk(a: int) -> int:
            return a

    with pytest.raises(ToolDefinitionError, match="JSON"):

        @tool(description="x", mock_response=object())
        def bad_mock(a: int) -> int:
            return a


def test_risk_cannot_understate_side_effects():
    with pytest.raises(ToolDefinitionError, match="needs risk >= 2"):

        @tool(description="Send an email", side_effects="external_comms", risk=1)
        def send(to: str) -> str:
            return to

    @tool(description="Send an email", side_effects="external_comms", risk=2, egress_hosts=["smtp.example.com"])
    def send_ok(to: str) -> str:
        return to

    assert send_ok.manifest.risk_tier == 2

    @tool(description="Refund", risk=3)
    def refund(order: str) -> str:
        return order

    assert refund.manifest.side_effects == "destructive"  # default effect follows the tier


@pytest.mark.parametrize("hosts", [["https://x.com"], ["x.com/path"], ["has space.com"], ["-bad.com"]])
def test_bad_hosts_rejected(hosts):
    with pytest.raises(ValueError):
        ToolManifest(id="a.b", mcp_name="b", description_plain="d", egress_hosts=hosts)


def test_good_hosts_and_paths():
    m = ToolManifest(
        id="a.b",
        mcp_name="b",
        description_plain="d",
        egress_hosts=["api.example.com", "*.example.org"],
        fs_paths=["/tmp/x"],
    )
    assert m.egress_hosts == ["api.example.com", "*.example.org"]
    for bad in (["relative/path"], ["/tmp/../etc"]):
        with pytest.raises(ValueError):
            ToolManifest(id="a.b", mcp_name="b", description_plain="d", fs_paths=bad)


def test_catalog_resolves_and_reports_unknown_ids():
    cat = ToolCatalog().add_tools("demo", [add_numbers, count_words], command="python", args=["server.py"])
    got = cat.resolve(["demo.count_words", "demo.add_numbers"])
    assert [t.id for t in got] == ["demo.count_words", "demo.add_numbers"] and got[0].server == "demo"
    assert cat.server("demo") == McpServerBinding(name="demo", command="python", args=["server.py"])
    with pytest.raises(UnknownToolError, match=r"gmail\.read"):
        cat.resolve(["demo.add_numbers", "gmail.read"])
    with pytest.raises(ValueError, match="already"):
        cat.add_tools("other", [add_numbers], command="python")


def test_manifests_document_is_json_and_stable():
    doc = manifests_document("demo", "x.py", [add_numbers.manifest, count_words.manifest])
    assert json.loads(json.dumps(doc)) == doc and [t["id"] for t in doc["tools"]] == [
        "demo.add_numbers",
        "demo.count_words",
    ]
