"""LocalRunner end to end, offline and free: real NAT + real Fabric + our adapter against a fake OpenAI server."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "mcp-tools"))
pytest.importorskip("nemo_fabric")

from agentbuilder.compile import compile_agent
from agentbuilder.models.credentials import CredentialError
from agentbuilder.runtime import credential_env, load_runner
from agentbuilder.spec import AgentSpec
from agentbuilder.testing import FakeModel, FakeOpenAIServer, ToolCall, Turn
from agentbuilder.tools import ToolCatalog
from demo_tools import TOOLS

from agentbuilder_nat import LocalRunner

SPEC = ROOT / "packages" / "sdk" / "examples" / "specs" / "calculator.agent.yaml"
SERVER = ROOT / "packages" / "mcp-tools" / "demo_server.py"
KEY = "sk-test-" + "Zx9Qp2Lm7Vb4Nc1R" * 2  # key-shaped but fake: used to prove it never leaks


def agent(mode: str, base_url: str):
    spec = AgentSpec.load(SPEC)
    spec = spec.model_copy(update={"model": spec.model.model_copy(update={"agent_mode": mode, "base_url": base_url})})
    catalog = ToolCatalog().add_tools("demo", TOOLS, command=sys.executable, args=[str(SERVER)])
    return spec, compile_agent(spec, catalog)


SCRIPTS = {
    "tool_calling": [Turn.calls(ToolCall("add_numbers", {"a": 17.5, "b": 25})), Turn.say("The sum is 42.5.")],
    "react": [Turn.react("demo__add_numbers", {"a": 17.5, "b": 25}), Turn.react_final("The sum is 42.5.")],
}


@pytest.mark.parametrize("mode", ["tool_calling", "react"])
def test_a_run_returns_text_trajectory_and_token_totals(mode):
    model = FakeModel(SCRIPTS[mode])
    with FakeOpenAIServer(model) as server:
        spec, compiled = agent(mode, server.base_url)
        result = LocalRunner().run(compiled, "What is 17.5 plus 25?", environ=credential_env_for(spec, compiled))
    assert result.ok and result.text == "The sum is 42.5."
    assert result.trajectory is not None and result.trajectory.tools_used == ["demo__add_numbers"]
    assert result.trajectory.real_tool_calls[0].result == "42.5"
    assert result.total_tokens and result.total_tokens > 0
    assert model.remaining == 0


def credential_env_for(spec, compiled):
    return credential_env(spec, compiled, environ={compiled.model.api_key_env: KEY})


def test_the_runner_is_found_through_its_entry_point():
    assert isinstance(load_runner("local"), LocalRunner)


def test_a_missing_key_is_a_plain_message_and_nothing_runs():
    with FakeOpenAIServer(FakeModel([])) as server:
        _, compiled = agent("tool_calling", server.base_url)
        result = LocalRunner().run(compiled, "hi", environ={})
    assert not result.ok and compiled.model.api_key_env in (result.error or "") and result.trajectory is None


def test_the_key_reaches_the_model_and_the_environment_is_restored():
    before = dict(os.environ)
    model = FakeModel(SCRIPTS["tool_calling"])
    with FakeOpenAIServer(model) as server:
        spec, compiled = agent("tool_calling", server.base_url)
        LocalRunner().run(compiled, "hi", environ=credential_env_for(spec, compiled))
    assert os.environ.get(compiled.model.api_key_env) == before.get(compiled.model.api_key_env)
    assert os.environ.get("PYTHONPATH") == before.get("PYTHONPATH")


class _Rejecting(BaseHTTPRequestHandler):
    """A model endpoint that refuses and, like some real ones, echoes the credential it was given in the error."""

    def do_POST(self):
        token = self.headers.get("Authorization", "")
        body = json.dumps({"error": {"message": f"Incorrect API key provided: {token.removeprefix('Bearer ')}"}})
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


def test_a_rejected_key_fails_cleanly_with_a_generic_error_and_no_key():
    http = HTTPServer(("127.0.0.1", 0), _Rejecting)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        spec, compiled = agent("tool_calling", f"http://127.0.0.1:{http.server_port}/v1")
        result = LocalRunner().run(compiled, "hi", environ=credential_env_for(spec, compiled))
    finally:
        http.shutdown()
    assert not result.ok and result.error
    assert KEY not in result.error and KEY not in repr(result) and KEY not in str(result.warnings)


def test_credential_env_refuses_a_missing_reference_and_returns_nothing_for_keyless_models():
    spec, compiled = agent("tool_calling", "http://127.0.0.1:1/v1")
    with pytest.raises(CredentialError):
        credential_env(spec, compiled, environ={})
    assert credential_env(spec, compiled, environ={compiled.model.api_key_env: KEY}) == {
        compiled.model.api_key_env: KEY
    }


class _FakeOutcome:
    def __init__(self, mapping):
        self._mapping = mapping

    def to_mapping(self):
        return self._mapping


@pytest.mark.parametrize("how", ["raises", "returns_error"])
def test_redaction_removes_the_key_from_errors_that_do_carry_it(how, monkeypatch):
    """Fabric currently hides upstream error bodies, but a future version or another runner may not: force both paths."""
    import nemo_fabric

    async def fake_run(self, config, **kwargs):
        if how == "raises":
            raise RuntimeError(f"upstream said: bad key {KEY}")
        return _FakeOutcome({"status": "failed", "error": {"message": f"401 for {KEY}"}, "output": {}})

    monkeypatch.setattr(nemo_fabric.Fabric, "run", fake_run)
    spec, compiled = agent("tool_calling", "http://127.0.0.1:1/v1")
    result = LocalRunner().run(compiled, "hi", environ=credential_env_for(spec, compiled))
    assert not result.ok and "****" in (result.error or "") and KEY not in (result.error or "")


def test_two_runs_at_once_in_one_event_loop_both_finish():
    """The run lock must not freeze the event loop: this used to hang forever."""
    import asyncio

    outcome = {}

    async def both():
        with (
            FakeOpenAIServer(FakeModel(SCRIPTS["tool_calling"])) as s1,
            FakeOpenAIServer(FakeModel(SCRIPTS["tool_calling"])) as s2,
        ):
            pairs = [agent("tool_calling", s.base_url) for s in (s1, s2)]
            runs = [LocalRunner().arun(c, "hi", environ=credential_env_for(sp, c)) for sp, c in pairs]
            outcome["results"] = await asyncio.gather(*runs)

    worker = threading.Thread(target=lambda: asyncio.run(both()), daemon=True)
    worker.start()
    worker.join(timeout=120)
    assert not worker.is_alive(), "two concurrent runs deadlocked"
    assert all(r.ok for r in outcome["results"])
