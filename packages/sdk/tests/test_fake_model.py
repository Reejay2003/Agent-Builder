import pytest

from agentbuilder.testing import FakeModel, ScriptExhausted, ToolCall, Turn, Usage

TOOLS = [
    {"type": "function", "function": {"name": "demo__add_numbers"}},
    {"type": "function", "function": {"name": "demo__count_words"}},
]


def test_script_plays_in_order_and_is_deterministic():
    def run():
        m = FakeModel([Turn.calls(ToolCall("add_numbers", {"a": 1, "b": 2})), Turn.say("done")])
        r1 = m.respond([{"role": "user", "content": "hi"}], TOOLS)
        r2 = m.respond([{"role": "user", "content": "hi"}], TOOLS)
        return r1, r2, m

    r1, r2, m = run()
    assert r1.finish_reason == "tool_calls" and r1.tool_calls[0].args == {"a": 1, "b": 2}
    assert r2.finish_reason == "stop" and r2.text == "done"
    assert (r1, r2) == run()[:2]
    assert m.remaining == 0


def test_bare_tool_names_resolve_to_the_prefixed_tool_offered():
    m = FakeModel([Turn.calls(ToolCall("count_words", {"text": "a b"}))])
    assert m.respond([], TOOLS).tool_calls[0].name == "demo__count_words"


def test_ambiguous_or_unknown_names_are_left_alone():
    tools = [{"function": {"name": "a__add"}}, {"function": {"name": "b__add"}}]
    m = FakeModel([Turn.calls(ToolCall("add")), Turn.calls(ToolCall("nope"))])
    assert m.respond([], tools).tool_calls[0].name == "add"
    assert m.respond([], tools).tool_calls[0].name == "nope"


def test_exhausted_script_fails_loudly_unless_repeat_last():
    m = FakeModel([Turn.say("only")])
    m.respond([])
    with pytest.raises(ScriptExhausted):
        m.respond([])
    r = FakeModel([Turn.say("again")], repeat_last=True)
    assert [r.respond([]).text for _ in range(3)] == ["again"] * 3


def test_requests_are_recorded_for_assertions():
    m = FakeModel([Turn.say("x")])
    m.respond([{"role": "user", "content": "question"}], TOOLS)
    assert m.requests[0].messages[0]["content"] == "question"
    assert m.requests[0].tool_names == ("demo__add_numbers", "demo__count_words")


def test_usage_is_explicit_or_estimated():
    m = FakeModel([Turn("x", usage=Usage(10, 5)), Turn.say("y")])
    assert m.respond([]).usage.total_tokens == 15
    assert m.respond([{"role": "user", "content": "z" * 400}]).usage.prompt_tokens >= 100


def test_react_helpers_produce_parseable_text():
    t = Turn.react("add_numbers", {"a": 1})
    assert "Action: add_numbers" in t.text and 'Action Input: {"a": 1}' in t.text
    assert "Final Answer: 3" in Turn.react_final("3").text
