import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agentbuilder.compile import compile_agent
from agentbuilder.models.credentials import CredentialError
from agentbuilder.models.vault import TOKEN_HEADER, LocalVaultStore
from agentbuilder.runtime import RunnerNotInstalled, RunResult, credential_env, load_runner
from agentbuilder.spec import AgentSpec
from tests.fixtures_tools import demo_catalog

KEY = "sk-vault-" + "Qw3Er5Ty7Ui9Op1A" * 2


class _Vault(BaseHTTPRequestHandler):
    """Stands in for the web app's internal secrets endpoint."""

    def do_GET(self):
        if self.headers.get(TOKEN_HEADER) != "tok":
            return self._reply(401, {})
        name = self.path.removeprefix("/api/internal/secrets/")
        if name == "modelcfg/3/api_key":
            self._reply(200, {"value": KEY})
        elif name == "modelcfg/locked/api_key":
            self._reply(423, {"error": "vault_locked"})
        else:
            self._reply(404, {})

    def _reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def vault_url():
    server = HTTPServer(("127.0.0.1", 0), _Vault)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_the_vault_store_returns_a_key_and_none_for_an_unknown_name(vault_url):
    store = LocalVaultStore(vault_url, "tok")
    assert store.get("modelcfg/3/api_key") == KEY
    assert store.get("modelcfg/99/api_key") is None


def test_a_locked_vault_and_a_wrong_token_give_plain_messages(vault_url):
    with pytest.raises(CredentialError, match="locked"):
        LocalVaultStore(vault_url, "tok").get("modelcfg/locked/api_key")
    with pytest.raises(CredentialError, match="token"):
        LocalVaultStore(vault_url, "wrong").get("modelcfg/3/api_key")


def test_an_unreachable_vault_is_a_credential_error_not_a_crash():
    with pytest.raises(CredentialError, match="cannot reach"):
        LocalVaultStore("http://127.0.0.1:1", "tok", timeout=1).get("modelcfg/3/api_key")


def test_the_vault_must_be_on_this_machine():
    with pytest.raises(ValueError, match="this machine"):
        LocalVaultStore("http://example.com", "tok")
    with pytest.raises(ValueError, match="token"):
        LocalVaultStore("http://127.0.0.1:3000", "")


def _agent(ref):
    spec = AgentSpec.from_dict(
        {
            "name": "x",
            "model": {"provider": "openai", "model": "gpt-4.1-mini", "credential_ref": ref},
            "tools": ["demo.add_numbers"],
        }
    )
    return spec, compile_agent(spec, demo_catalog())


def test_a_vault_reference_becomes_the_environment_variable_the_runner_reads(vault_url):
    spec, compiled = _agent("secret://modelcfg/3/api_key")
    env = credential_env(spec, compiled, environ={}, stores=[LocalVaultStore(vault_url, "tok")])
    assert env == {"AGENTBUILDER_SECRET_MODELCFG_3_API_KEY": KEY} and compiled.model.api_key_env in env


def test_an_env_reference_reads_the_named_variable_and_a_missing_one_is_refused():
    spec, compiled = _agent("env://OPENAI_API_KEY")
    assert credential_env(spec, compiled, environ={"OPENAI_API_KEY": KEY}) == {"OPENAI_API_KEY": KEY}
    with pytest.raises(CredentialError, match="OPENAI_API_KEY"):
        credential_env(spec, compiled, environ={})


def test_a_model_without_a_key_needs_no_environment():
    spec = AgentSpec.from_dict({"name": "x", "model": {"provider": "ollama", "model": "llama3"}, "tools": []})
    assert credential_env(spec, compile_agent(spec, demo_catalog()), environ={}) == {}


def test_asking_for_a_runner_that_is_not_installed_says_how_to_get_one():
    with pytest.raises(RunnerNotInstalled, match="pip install"):
        load_runner("does-not-exist")


def test_a_run_result_is_frozen_and_reports_ok():
    r = RunResult(status="succeeded", text="hi")
    assert r.ok and r.total_tokens is None
    with pytest.raises(ValueError, match="frozen"):
        r.text = "changed"  # type: ignore[misc]


def test_a_redirect_from_the_vault_is_not_followed_so_the_token_cannot_travel(vault_url):
    seen = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get(TOKEN_HEADER))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    target = HTTPServer(("127.0.0.1", 0), Target)
    threading.Thread(target=target.serve_forever, daemon=True).start()

    class Redirector(_Vault):
        def do_GET(self):
            self.send_response(307)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/stolen")
            self.send_header("Content-Length", "0")
            self.end_headers()

    redirecting = HTTPServer(("127.0.0.1", 0), Redirector)
    threading.Thread(target=redirecting.serve_forever, daemon=True).start()
    try:
        with pytest.raises(CredentialError, match="redirected"):
            LocalVaultStore(f"http://127.0.0.1:{redirecting.server_port}", "tok").get("modelcfg/3/api_key")
    finally:
        target.shutdown()
        redirecting.shutdown()
    assert seen == []  # the second server never received a request
