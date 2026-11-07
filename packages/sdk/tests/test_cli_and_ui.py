import json
import sys
import urllib.request
from pathlib import Path

import pytest

from agentbuilder import cli
from agentbuilder.models.vault import TOKEN_HEADER
from agentbuilder.runtime import RunResult
from agentbuilder.ui import UiSession, _free_port, find_web_dir
from tests.conftest import EXAMPLES
from tests.fixtures_tools import demo_catalog

CALC = str(EXAMPLES / "calculator.agent.yaml")


@pytest.fixture(autouse=True)
def tools(monkeypatch):
    monkeypatch.setattr(cli, "load_catalog", lambda ref: demo_catalog())


def test_validate_reports_how_the_agent_will_run(capsys):
    assert cli.main(["validate", CALC]) == 0
    assert "tool_calling mode with 3 tool(s)" in capsys.readouterr().out


def test_a_bad_spec_prints_every_problem_and_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.agent.yaml"
    bad.write_text(
        "spec_version: 1\nname: x\nmodel: {provider: openai, model: m, credential_ref: sk-abcdefghijklmnop123456}\n"
    )
    assert cli.main(["validate", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "credential_ref" in err and "abcdefghijklmnop" not in err


@pytest.mark.parametrize(
    "fmt, needle",
    [("nat", "workflow:"), ("fabric", "target_id"), ("policy", "filesystem_policy"), ("provider", "credentials:")],
)
def test_compile_prints_each_format(fmt, needle, capsys):
    assert cli.main(["compile", CALC, "--format", fmt]) == 0
    assert needle in capsys.readouterr().out


def test_run_prints_the_answer_and_fails_with_a_message_when_the_run_fails(monkeypatch, capsys):
    class Fake:
        def __init__(self, result):
            self.result = result

        def run(self, compiled, prompt, *, environ=None, approve=None):
            return self.result

    monkeypatch.setenv("LLM_API_KEY", "k" * 20)
    monkeypatch.setattr(cli, "load_runner", lambda name: Fake(RunResult(status="succeeded", text="42.5")))
    assert cli.main(["run", CALC, "what is 17.5 + 25?"]) == 0 and capsys.readouterr().out.strip() == "42.5"
    monkeypatch.setattr(cli, "load_runner", lambda name: Fake(RunResult(status="failed", error="model said no")))
    assert cli.main(["run", CALC, "x"]) == 1 and "model said no" in capsys.readouterr().err


def test_run_without_the_key_variable_says_which_one(monkeypatch, capsys):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        cli, "load_runner", lambda name: object()
    )  # CI has no runner installed; the key check comes first
    assert cli.main(["run", CALC, "x"]) == 1
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_the_repository_web_app_is_found():
    web = find_web_dir()
    assert web is not None and (web / "package.json").is_file()


def test_ui_starts_both_servers_hands_the_web_app_its_tokens_and_stops_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "web.py").write_text(
        "import http.server as h, os, sys\n"
        "env = os.environ\n"
        "open(sys.argv[2], 'w').write(env['AGENTBUILDER_API_URL'] + '\\n' + env['AGENTBUILDER_API_TOKEN'])\n"
        "h.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), h.SimpleHTTPRequestHandler).serve_forever()\n"
    )
    port, seen = _free_port(), tmp_path / "env.txt"
    session = UiSession(
        demo_catalog(),
        web_port=port,
        open_browser=False,
        web_command=[sys.executable, str(tmp_path / "web.py"), str(port), str(seen)],
        web_dir=tmp_path,
        startup_timeout=30,
    )
    session.start()
    try:
        assert session._app is not None and session._app.audit_log == str(
            tmp_path / "state" / "agentbuilder" / "tool-calls.jsonl"
        )  # UI test runs leave a record of every tool call
        api_url, token = Path(seen).read_text().split("\n")
        assert api_url == session.api_url and len(token) >= 32
        request = urllib.request.Request(f"{api_url}/tools", headers={TOKEN_HEADER: token})
        assert json.load(urllib.request.urlopen(request, timeout=5))["tools"]
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{api_url}/tools", timeout=5)  # no token
        assert refused.value.code == 401
    finally:
        session.stop()
    assert session._web is not None and session._web.poll() is not None  # the web process is gone


def test_ui_fails_fast_when_the_web_app_dies_on_start(tmp_path):
    session = UiSession(
        demo_catalog(),
        web_port=_free_port(),
        open_browser=False,
        web_command=[sys.executable, "-c", "raise SystemExit(3)"],
        web_dir=tmp_path,
        startup_timeout=30,
    )
    with pytest.raises(RuntimeError, match="exited with code 3"):
        session.start()


def test_ui_refuses_a_port_that_another_program_already_uses(tmp_path):
    import http.server
    import threading

    other = http.server.ThreadingHTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    session = UiSession(demo_catalog(), web_port=other.server_port, open_browser=False, web_command=["true"])
    try:
        with pytest.raises(RuntimeError, match="already listening"):
            session.start()
    finally:
        other.shutdown()
    assert session._server is None  # nothing was started


def test_tools_lists_every_tool_with_its_tier_and_network_access(capsys, monkeypatch):
    from agentbuilder.library import personal_catalog

    monkeypatch.setattr(cli, "load_catalog", lambda ref: personal_catalog(demo_catalog()))
    assert cli.main(["tools"]) == 0
    out = capsys.readouterr().out
    assert "gmail.send_draft" in out and "tier 1 (writes)" in out and "calendar.create_event" in out and "tier 2" in out
    assert "html.duckduckgo.com" in out and "oauth2.googleapis.com" not in out  # the token host is plumbing, not shown


def test_run_mock_starts_every_tool_server_in_mock_mode(monkeypatch, capsys, tmp_path):
    seen = []

    class Fake:
        def run(self, compiled, prompt, *, environ=None, approve=None):
            seen.append(compiled)
            return RunResult(status="succeeded", text="done")

    monkeypatch.setenv("LLM_API_KEY", "k" * 20)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "load_runner", lambda name: Fake())
    assert cli.main(["run", CALC, "hi", "--mock"]) == 0 and cli.main(["run", CALC, "hi"]) == 0
    assert "--mock" in seen[0].servers[0].args and "--mock" not in seen[1].servers[0].args
    assert seen[0].servers[0].args[-2:] == ["--log", str(tmp_path / "state" / "agentbuilder" / "tool-calls.jsonl")]


def test_auth_status_and_revoke_work_on_the_saved_file_and_never_print_secrets(monkeypatch, tmp_path, capsys):
    token = tmp_path / "google-token.json"
    monkeypatch.setenv("AGENTBUILDER_GOOGLE_TOKEN_FILE", str(token))
    assert cli.main(["auth", "status"]) == 1 and "not signed in" in capsys.readouterr().out
    token.write_text(
        json.dumps(
            {
                "client_id": "c",
                "client_secret": "SECRET-VALUE",
                "refresh_token": "REFRESH-VALUE",
                "scopes": ["gmail.readonly"],
                "saved_at": 1,
            }
        )
    )
    assert cli.main(["auth", "status"]) == 0
    shown = capsys.readouterr().out
    assert (
        "signed in" in shown
        and "gmail.readonly" in shown
        and "SECRET-VALUE" not in shown
        and "REFRESH-VALUE" not in shown
    )
    assert "7 days" in shown  # saved long ago: the Testing-mode expiry note appears
    monkeypatch.setattr("agentbuilder.library.google._json_request", lambda *a, **k: {})  # no real call to Google
    assert cli.main(["auth", "revoke"]) == 0 and not token.exists()


def test_auth_google_without_a_client_file_explains_the_setup_steps(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["auth", "google"])
    assert "client-secret" in str(stop.value)
    assert "Desktop app" in capsys.readouterr().err


def test_a_live_tier2_run_without_a_terminal_is_refused_before_any_runner_starts(monkeypatch, capsys, tmp_path):
    spec = tmp_path / "a.agent.yaml"
    spec.write_text(
        "spec_version: 1\nname: a\nmodel: {provider: openai, model: m, credential_ref: env://LLM_API_KEY}\n"
        "tools: [calendar.create_event]\n"
    )
    monkeypatch.setenv("LLM_API_KEY", "k" * 20)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "load_runner", lambda name: pytest.fail("no runner may start"))
    from agentbuilder.library import personal_catalog

    monkeypatch.setattr(cli, "load_catalog", lambda ref: personal_catalog())
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)  # a script or CI: no one to ask
    assert cli.main(["run", str(spec), "hi"]) == 1
    assert "calendar.create_event need a person to approve each call" in capsys.readouterr().err

    seen = {}

    class Runner:
        def run(self, compiled, prompt, *, environ=None, approve=None):
            seen["approve"] = approve
            return RunResult(status="succeeded", text="done")

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)  # a person at a terminal: the run asks them
    monkeypatch.setattr(cli, "load_runner", lambda name: Runner())
    assert cli.main(["run", str(spec), "hi"]) == 0
    assert callable(seen["approve"])


def test_doctor_reports_a_missing_mcp_package(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_spec", lambda name: None if name == "mcp" else object())
    assert cli.main(["doctor"]) == 1
    assert "FAIL mcp package (runs the tool servers): pip install 'agentbuilder[mcp]'" in capsys.readouterr().out


def test_probe_model_has_no_tools_flag():
    with pytest.raises(SystemExit):  # argparse refuses an option the command would silently ignore
        cli.parser().parse_args(["probe-model", "x.agent.yaml", "--tools", "m:a"])
