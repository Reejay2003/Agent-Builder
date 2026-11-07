"""The model check: one real call, classified, with the key never leaking."""

import http.client
import http.server
import json
import threading

import pytest

from agentbuilder.models import Model, probe_tool_calling, resolve_model
from agentbuilder.repair import call_with_retry, retry_delay

KEY = "sk-test-0123456789abcdef"


def resolved(base_url="https://x.test/v1", key=KEY):
    spec = Model.custom("m", base_url=base_url, api_key_env="K")
    return resolve_model(spec, environ={"K": key} if key else {}, need_key=bool(key))


def reply(status, body="", headers=None):
    return lambda url, h, b: (status, headers or {}, body if isinstance(body, str) else json.dumps(body))


def tool_call(arguments='{"a": 17, "b": 25}', name="add_numbers"):
    call = {"id": "1", "type": "function", "function": {"name": name, "arguments": arguments}}
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}


@pytest.mark.parametrize(
    ("answer", "tool_calling", "mode", "ok"),
    [
        (reply(200, tool_call()), True, "auto", True),
        (reply(200, {"choices": [{"message": {"content": "42"}}]}), False, "react", True),
        (reply(200, tool_call('{"a": "x", "b": 2}')), False, "react", True),  # arguments the tool would reject
        (reply(200, tool_call("not json")), False, "react", True),
        (reply(200, tool_call(name="other")), False, "react", True),
        (reply(400, {"error": {"message": "this model does not support tools"}}), False, "react", True),
        (reply(401, "bad key"), None, None, False),
        (reply(404, "no such model"), None, None, False),
        (reply(400, "max_tokens is too large"), None, None, False),  # a 400 that is not about tools: learn nothing
        (reply(200, "<html>not json</html>"), None, None, False),
    ],
)
def test_each_answer_maps_to_a_clear_result(answer, tool_calling, mode, ok):
    result = probe_tool_calling(resolved(), post=answer)
    assert (result.tool_calling, result.agent_mode, result.ok) == (tool_calling, mode, ok)
    assert result.message


def test_a_provider_that_rejects_or_ignores_required_gets_one_more_try_with_auto():
    def provider(choice_ok):
        sent = []

        def post(url, headers, body):
            choice = json.loads(body)["tool_choice"]
            sent.append(choice)
            if choice == choice_ok:
                return 200, {}, json.dumps(tool_call())
            if choice == "required" and choice_ok == "auto":
                return 400, {}, "tool_choice required is not supported"
            return 200, {}, json.dumps({"choices": [{"message": {"content": "42"}}]})

        return post, sent

    post, sent = provider("auto")
    result = probe_tool_calling(resolved(), post=post)
    assert result.agent_mode == "auto" and sent == ["required", "auto"]
    post, sent = provider("never")  # neither works: react, after exactly two requests
    assert probe_tool_calling(resolved(), post=post).agent_mode == "react" and sent == ["required", "auto"]
    post, sent = provider("required")  # the normal case costs one request
    assert probe_tool_calling(resolved(), post=post).agent_mode == "auto" and sent == ["required"]


def test_the_request_requires_a_tool_call_and_sends_the_key_only_as_a_bearer_header():
    seen = []

    def post(url, headers, body):
        seen.append((url, headers, json.loads(body)))
        return 200, {}, json.dumps(tool_call())

    probe_tool_calling(resolved(), post=post)
    ((url, headers, payload),) = seen
    assert url == "https://x.test/v1/chat/completions" and headers["Authorization"] == f"Bearer {KEY}"
    assert payload["tool_choice"] == "required" and payload["tools"][0]["function"]["name"] == "add_numbers"
    assert KEY not in json.dumps(payload)


@pytest.mark.parametrize("error", [http.client.BadStatusLine("junk"), http.client.IncompleteRead(b"par")])
def test_a_garbled_or_cut_off_reply_is_a_plain_failure_not_a_crash(error):
    def post(*a):
        raise error

    result = probe_tool_calling(resolved(), post=post)
    assert not result.ok and result.tool_calling is None and "could not reach" in result.message


def test_a_provider_that_echoes_the_key_never_shows_it_in_the_message():
    result = probe_tool_calling(resolved(), post=reply(500, f"upstream said: bad token {KEY}"))
    assert KEY not in result.message and "****" in result.message


def test_no_key_for_a_local_model_sends_no_authorization_header():
    seen = []

    def post(url, headers, body):
        seen.append(headers)
        return 200, {}, json.dumps(tool_call())

    probe_tool_calling(resolved(key=None), post=post)
    assert "Authorization" not in seen[0]


def test_a_rate_limit_is_retried_after_the_wait_the_server_asked_for():
    answers = [(429, {"Retry-After": "2"}, "slow down"), (200, {}, json.dumps(tool_call()))]
    waits = []
    result = probe_tool_calling(resolved(), post=lambda *a: answers.pop(0), sleep=waits.append)
    assert result.tool_calling is True and waits == [2.0]


def test_an_exhausted_quota_is_not_retried_and_says_so():
    calls, waits = [], []

    def post(*a):
        calls.append(1)
        return 429, {"Retry-After": "3600"}, "daily quota"

    result = probe_tool_calling(resolved(), post=post, sleep=waits.append)
    assert len(calls) == 1 and not waits and not result.ok and "quota" in result.message


def test_retry_helper_stops_after_the_given_retries_and_never_retries_a_bad_key():
    calls = []

    def always_503():
        calls.append(1)
        return 503, {}, "down"

    assert call_with_retry(always_503, retries=2, sleep=lambda s: None)[0] == 503 and len(calls) == 3
    calls.clear()
    assert call_with_retry(lambda: (calls.append(1), (401, {}, ""))[1], sleep=lambda s: None)[0] == 401
    assert len(calls) == 1
    assert retry_delay(0, "abc", max_wait=10) == 1.0 and retry_delay(2, None, max_wait=10) == 4.0
    assert retry_delay(0, "11", max_wait=10) is None and retry_delay(0, "-1", max_wait=10) is None


def test_the_real_http_path_sends_the_request_and_does_not_follow_a_redirect():
    hits: list[tuple[str, str | None]] = []

    class Other(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(("other", self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    other = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Other)

    class First(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            hits.append(("first", self.headers.get("Authorization")))
            self.send_response(307)
            self.send_header("Location", f"http://127.0.0.1:{other.server_port}/steal")
            self.end_headers()

        def log_message(self, *a):
            pass

    first = http.server.ThreadingHTTPServer(("127.0.0.1", 0), First)
    for server in (first, other):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = probe_tool_calling(resolved(f"http://127.0.0.1:{first.server_port}/v1"))
    finally:
        first.shutdown()
        other.shutdown()
    assert hits == [("first", f"Bearer {KEY}")] and not result.ok  # the key never reached the second host


# ---- the server endpoint and the CLI command ---------------------------------------------------------------------


def _server(monkeypatch, result, environ=None):
    from agentbuilder.models import ProbeResult
    from agentbuilder.server import LocalServer
    from agentbuilder.server import app as app_module
    from agentbuilder.tools import ToolCatalog

    seen = []

    def fake(model):
        seen.append(model)
        return ProbeResult(*result)

    monkeypatch.setattr(app_module, "probe_tool_calling", fake)
    return LocalServer(token="t", catalog=ToolCatalog(), environ=environ or {}), seen


MODEL = {"provider": "openai", "model": "gpt-4.1-mini", "credential_ref": "env://OPENAI_API_KEY"}


def test_the_endpoint_returns_what_the_wizard_should_write_and_uses_the_servers_own_key_source(monkeypatch):
    app, seen = _server(monkeypatch, (True, True, "auto", "works"), {"OPENAI_API_KEY": KEY})
    try:
        status, body = app.check_model({"model": MODEL})
    finally:
        app.shutdown()
    assert status == 200 and body == {"ok": True, "tool_calling": True, "agent_mode": "auto", "message": "works"}
    assert seen[0].api_key.reveal() == KEY and KEY not in json.dumps(body)


def test_the_endpoint_reports_a_missing_key_and_a_bad_model_as_field_errors(monkeypatch):
    from agentbuilder.server.app import _Invalid

    app, seen = _server(monkeypatch, (True, True, "auto", "works"))
    try:
        with pytest.raises(_Invalid) as no_key:
            app.check_model({"model": MODEL})
        with pytest.raises(_Invalid) as not_object:
            app.check_model({"model": "gpt"})
        with pytest.raises(_Invalid) as bad_provider:
            app.check_model({"model": {"provider": "nope", "model": "m"}})
    finally:
        app.shutdown()
    assert no_key.value.problems[0]["field"] == "model.credential_ref"
    assert not_object.value.problems[0]["field"] == "model"
    assert bad_provider.value.problems[0]["field"].startswith("model")
    assert not seen  # nothing was sent anywhere


def test_probe_model_command_prints_the_result_and_the_mode_to_use(monkeypatch, capsys, tmp_path):
    from agentbuilder import cli
    from agentbuilder.models import ProbeResult

    spec = tmp_path / "a.agent.yaml"
    spec.write_text("spec_version: 1\nname: a\nmodel: {provider: ollama, model: llama3}\n")
    monkeypatch.setattr(cli, "probe_tool_calling", lambda m: ProbeResult(True, False, "react", "no tools here"))
    assert cli.main(["probe-model", str(spec)]) == 0
    out = capsys.readouterr()
    assert "no tools here" in out.out and "model.agent_mode to react" in out.out and "one real request" in out.err
    monkeypatch.setattr(cli, "probe_tool_calling", lambda m: ProbeResult(False, None, None, "key rejected"))
    assert cli.main(["probe-model", str(spec)]) == 1
