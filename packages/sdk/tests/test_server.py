import http.client
import json
import threading
import time
from pathlib import Path

import pytest

from agentbuilder.compile import CompiledAgent
from agentbuilder.models.vault import TOKEN_HEADER, LocalVaultStore
from agentbuilder.observe import load
from agentbuilder.runtime import RunResult
from agentbuilder.server import LocalServer, build_server
from tests.fixtures_tools import demo_catalog
from tests.test_vault_and_runtime import KEY, _Vault

FIXTURES = Path(__file__).parent / "fixtures" / "atif"
TOKEN = "t" * 32
SPEC = {
    "name": "assistant",
    "model": {"provider": "openai", "model": "gpt-4.1-mini", "credential_ref": "secret://modelcfg/3/api_key"},
    "tools": ["demo.add_numbers"],
}


class FakeRunner:
    name = "fake"

    def __init__(self):
        self.calls: list[tuple[str, dict[str, str]]] = []

    def run(self, compiled: CompiledAgent, prompt: str, *, environ=None) -> RunResult:
        self.calls.append((prompt, dict(environ or {})))
        return RunResult(status="succeeded", text="42.5", trajectory=load(FIXTURES / "relay_tool_calling.json"))


@pytest.fixture
def api():
    vault = __import__("http.server").server.HTTPServer(("127.0.0.1", 0), _Vault)
    threading.Thread(target=vault.serve_forever, daemon=True).start()
    runner = FakeRunner()
    app = LocalServer(
        token=TOKEN,
        catalog=demo_catalog(),
        stores=[LocalVaultStore(f"http://127.0.0.1:{vault.server_port}", "tok")],
        runner_factory=lambda: runner,
        environ={},
    )
    server = build_server(app)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def call(method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        h = {TOKEN_HEADER: TOKEN, **(headers or {})}
        if host:
            h["Host"] = host
        data = json.dumps(body) if body is not None else None
        if data:
            h["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=h)
        response = conn.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if raw else None

    call.runner = runner
    yield call
    server.shutdown()
    vault.shutdown()
    app.shutdown()


def test_every_request_needs_the_token_a_loopback_host_and_no_browser_origin(api):
    assert api("GET", "/health")[0] == 200
    assert api("GET", "/health", headers={TOKEN_HEADER: "wrong"})[0] == 401
    assert api("GET", "/health", host="evil.example.com")[0] == 403  # DNS rebinding
    assert api("GET", "/health", headers={"Origin": "http://evil.example.com"})[0] == 403  # a web page calling directly


def test_tools_are_listed_with_plain_descriptions_and_risk(api):
    status, body = api("GET", "/tools")
    assert status == 200
    add = next(t for t in body["tools"] if t["id"] == "demo.add_numbers")
    assert add["risk_tier"] == 0 and add["description"] and add["input_schema"]["properties"]


def test_a_valid_spec_returns_the_yaml_the_sdk_writes_and_the_resolved_mode(api):
    status, body = api("POST", "/spec/validate", {"spec": SPEC})
    assert status == 200 and body["ok"] and body["agent_mode"] == "tool_calling"
    assert body["spec_yaml"].startswith("spec_version: 1") and body["tools"] == ["demo.add_numbers"]


def test_an_invalid_spec_returns_per_field_errors(api):
    bad = {**SPEC, "model": {**SPEC["model"], "credential_ref": "modelcfg://3/api_key"}}
    status, body = api("POST", "/spec/validate", {"spec": bad})
    assert status == 422 and not body["ok"]
    assert any(e["field"] == "model.credential_ref" for e in body["errors"])
    status, body = api("POST", "/spec/validate", {"spec": {**SPEC, "tools": ["nope.missing"]}})
    assert status == 422 and body["errors"][0]["field"] == "tools"


def _wait(api, run_id):
    for _ in range(100):
        status, body = api("GET", f"/runs/{run_id}")
        assert status == 200
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_a_run_resolves_the_key_from_the_vault_and_returns_text_and_a_trace(api):
    status, started = api("POST", "/runs", {"spec": SPEC, "prompt": "What is 17.5 plus 25?"})
    assert status == 202
    done = _wait(api, started["run_id"])
    assert done["status"] == "succeeded" and done["text"] == "42.5"
    assert (
        done["trace"]["tools_used"] == ["demo__add_numbers", "demo__count_words"]
        and done["trace"]["tokens"]["total"] == 242
    )
    first_step_with_tools = next(s for s in done["trace"]["steps"] if s["tool_calls"])
    assert first_step_with_tools["tool_calls"][0]["name"] in {"demo__add_numbers", "demo__count_words"}
    prompt, env = api.runner.calls[0]
    assert prompt == "What is 17.5 plus 25?" and env == {"AGENTBUILDER_SECRET_MODELCFG_3_API_KEY": KEY}
    assert KEY not in json.dumps(done) and KEY not in json.dumps(started)  # the key never goes back to the caller


def test_a_locked_vault_fails_the_run_with_a_message_the_user_can_act_on(api):
    locked = {**SPEC, "model": {**SPEC["model"], "credential_ref": "secret://modelcfg/locked/api_key"}}
    _, started = api("POST", "/runs", {"spec": locked, "prompt": "hi"})
    done = _wait(api, started["run_id"])
    assert done["status"] == "failed" and "locked" in done["error"] and not api.runner.calls


def test_bad_requests_get_clear_errors(api):
    assert api("POST", "/runs", {"spec": SPEC, "prompt": "  "})[0] == 422
    assert api("POST", "/runs", {"prompt": "hi"})[0] == 422  # no spec
    assert api("GET", "/runs/unknown")[0] == 404
    assert api("GET", "/nope")[0] == 404
    assert api("POST", "/spec/validate", ["not", "an", "object"])[0] == 400


def test_the_server_only_binds_to_loopback():
    with pytest.raises(ValueError, match="loopback"):
        build_server(LocalServer(token=TOKEN, catalog=demo_catalog()), host="0.0.0.0")


def test_the_server_never_resolves_env_references_from_its_own_environment(monkeypatch):
    """A shared spec can name any variable and any base_url; it must not be able to make the server send one out."""
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "not-a-real-secret-0123456789")
    runner = FakeRunner()
    app = LocalServer(token=TOKEN, catalog=demo_catalog(), runner_factory=lambda: runner)  # default environ
    spec = {
        "name": "x",
        "model": {
            "provider": "openai_compatible",
            "model": "m",
            "base_url": "https://evil.example/v1",
            "credential_ref": "env://AWS_SECRET_ACCESS_KEY",
        },
        "tools": [],
    }
    status, started = app.start_run({"spec": spec, "prompt": "hi"})
    assert status == 202
    for _ in range(100):
        _, run = app.get_run(started["run_id"])
        if run["status"] != "running":
            break
        time.sleep(0.05)
    app.shutdown()
    assert run["status"] == "failed" and "AWS_SECRET_ACCESS_KEY" in run["error"] and not runner.calls


def test_an_unexpected_error_is_a_plain_500_and_its_text_is_never_logged(api, monkeypatch, capsys):
    from agentbuilder.server import app as app_module

    def broken(model):
        raise RuntimeError(f"provider said: bad key {KEY}")

    monkeypatch.setattr(app_module, "probe_tool_calling", broken)
    model = {"provider": "openai", "model": "m", "credential_ref": "secret://modelcfg/3/api_key"}
    status, body = api("POST", "/model/check", {"model": model})
    assert status == 500 and body == {"ok": False, "errors": [{"field": "", "message": "unexpected server error"}]}
    logged = capsys.readouterr().err
    assert "unexpected RuntimeError on /model/check" in logged and KEY not in logged
    assert api("GET", "/health")[0] == 200  # the server keeps serving
