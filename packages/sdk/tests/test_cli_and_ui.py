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

        def run(self, compiled, prompt, *, environ=None):
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


def test_ui_starts_both_servers_hands_the_web_app_its_tokens_and_stops_cleanly(tmp_path):
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
