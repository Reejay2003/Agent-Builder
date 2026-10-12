"""Plain-assert tests for our adapter additions (no LLM, no network). Run: make test"""
import os, sys, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from nemo_fabric_adapters.nat import repair


def test_resolve():
    av = ["demo__add_numbers", "demo__count_words", "demo__get_current_time"]
    assert repair.resolve("add_numbers", av) == "demo__add_numbers"       # bare name -> prefixed
    assert repair.resolve("`add_numbers`", av) == "demo__add_numbers"     # quotes/backticks
    assert repair.resolve("add_numbers()", av) == "demo__add_numbers"     # trailing ()
    assert repair.resolve("DEMO__ADD_NUMBERS", av) == "demo__add_numbers" # case
    assert repair.resolve("demo.add_numbers", av) == "demo__add_numbers"  # dotted group form
    assert repair.resolve("demo__add_numbers", av) is None                # already exact: no repair
    assert repair.resolve("add", av) is None                              # partial name: never guess
    assert repair.resolve("nonexistent", av) is None
    assert repair.resolve("add_numbers", ["a__add_numbers", "b__add_numbers"]) is None  # ambiguous: never guess
    assert repair.resolve("", av) is None


def test_patched_lookup_logs_every_repair():
    from nat.plugins.langchain.agent.react_agent.agent import ReActAgentGraph
    repair.install_tool_name_repair()
    stub = types.SimpleNamespace(tools_dict={"demo__add_numbers": "TOOL"})
    repair.REPAIRS.clear()
    assert ReActAgentGraph._get_tool(stub, "demo__add_numbers") == "TOOL"
    assert repair.REPAIRS == []                                            # exact hit: nothing logged
    assert ReActAgentGraph._get_tool(stub, "add_numbers") == "TOOL"
    assert repair.REPAIRS == [{"kind": "tool_name", "requested": "add_numbers", "resolved": "demo__add_numbers"}]  # never silent
    assert ReActAgentGraph._get_tool(stub, "unknown") is None
    assert len(repair.REPAIRS) == 1


def test_relay_events_import_and_install():
    from nemo_fabric_adapters.nat import relay_events
    relay_events.install_typed_relay_events()
    relay_events.install_typed_relay_events()  # idempotent
    assert relay_events._jsonable({"a": [1, "x" * 5000]})["a"][1].__len__() == 2000  # long values are truncated


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok  ", name)
