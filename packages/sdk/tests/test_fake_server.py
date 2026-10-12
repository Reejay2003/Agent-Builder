import json
import urllib.error
import urllib.request

import pytest

from agentbuilder.testing import FakeModel, FakeOpenAIServer, ToolCall, Turn

TOOLS = [{"type": "function", "function": {"name": "demo__add_numbers"}}]


def post(server, body):
    req = urllib.request.Request(
        server.base_url + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer fake"},
    )
    return urllib.request.urlopen(req, timeout=10)


def test_non_streaming_tool_call_then_text():
    model = FakeModel([Turn.calls(ToolCall("add_numbers", {"a": 17.5, "b": 25})), Turn.say("42.5")])
    with FakeOpenAIServer(model) as s:
        first = json.loads(
            post(s, {"model": "m", "messages": [{"role": "user", "content": "q"}], "tools": TOOLS}).read()
        )
        call = first["choices"][0]["message"]["tool_calls"][0]
        assert first["choices"][0]["finish_reason"] == "tool_calls"
        assert call["function"]["name"] == "demo__add_numbers" and json.loads(call["function"]["arguments"]) == {
            "a": 17.5,
            "b": 25,
        }
        second = json.loads(post(s, {"model": "m", "messages": []}).read())
        assert second["choices"][0]["message"]["content"] == "42.5" and second["usage"]["total_tokens"] > 0


def sse(response):
    events = [line[6:] for line in response.read().decode().splitlines() if line.startswith("data: ")]
    return events[:-1], events[-1]


def test_streaming_reassembles_text_and_tool_calls():
    long_text = "x" * 100
    model = FakeModel([Turn(text=long_text, tool_calls=(ToolCall("add_numbers", {"a": 1}),))])
    with FakeOpenAIServer(model) as s:
        chunks, last = sse(
            post(
                s,
                {
                    "model": "m",
                    "messages": [],
                    "tools": TOOLS,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            )
        )
    assert last == "[DONE]"
    parsed = [json.loads(c) for c in chunks]
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in parsed if c["choices"])
    assert text == long_text and sum(1 for c in parsed if c["choices"] and c["choices"][0]["delta"].get("content")) > 1
    deltas = [
        c["choices"][0]["delta"]["tool_calls"]
        for c in parsed
        if c["choices"] and "tool_calls" in c["choices"][0]["delta"]
    ]
    assert deltas[0][0]["index"] == 0 and deltas[0][0]["function"]["name"] == "demo__add_numbers"
    assert [c["choices"][0]["finish_reason"] for c in parsed if c["choices"] and c["choices"][0]["finish_reason"]] == [
        "tool_calls"
    ]
    assert parsed[-1]["choices"] == [] and parsed[-1]["usage"]["total_tokens"] > 0  # usage chunk only when requested


def test_models_endpoint_and_exhausted_script():
    with FakeOpenAIServer(FakeModel([Turn.say("once")], name="my-fake")) as s:
        assert json.loads(urllib.request.urlopen(s.base_url + "/models").read())["data"][0]["id"] == "my-fake"
        post(s, {"model": "m", "messages": []})
        with pytest.raises(urllib.error.HTTPError) as e:
            post(s, {"model": "m", "messages": []})
        assert e.value.code == 500 and "fake_script_exhausted" in e.value.read().decode()


def test_server_stops_cleanly_and_uses_a_free_port():
    a, b = FakeOpenAIServer(FakeModel([])).start(), FakeOpenAIServer(FakeModel([])).start()
    try:
        assert a.base_url != b.base_url
    finally:
        a.stop()
        b.stop()
