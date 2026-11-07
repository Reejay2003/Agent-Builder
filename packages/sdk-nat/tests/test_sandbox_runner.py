"""SandboxRunner. The unit tests fake the `openshell` command; the last test runs the agent in a real microVM."""

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("nemo_fabric")

from agentbuilder.compile import compile_agent
from agentbuilder.gateway import LocalGateway
from agentbuilder.library import personal_catalog
from agentbuilder.runtime import RunResult, credential_env, load_runner
from agentbuilder.spec import AgentSpec
from agentbuilder.testing import FakeModel, FakeOpenAIServer, Turn
from agentbuilder.tools import ToolCatalog, tool

from agentbuilder_nat.sandbox import SandboxRunner
from agentbuilder_nat.sandbox_main import MARKER

ROOT = Path(__file__).resolve().parents[3]
KEY = "sk-test-" + "Pw3Kd8Hs5Jf1Lq6T" * 2  # key-shaped but fake: used to prove it never leaks

SPEC_FILE = ROOT / "packages" / "sdk" / "examples" / "specs" / "personal_automation.agent.yaml"


def personal(base_url="https://api.openai.com/v1", *, mock=True, log=None):
    spec = AgentSpec.load(SPEC_FILE)
    model = spec.model.model_copy(update={"agent_mode": "react", "base_url": base_url})
    spec = spec.model_copy(update={"model": model})
    compiled = compile_agent(spec, LocalGateway().apply(personal_catalog(), mock=mock, audit_log=log))
    return spec, compiled, credential_env(spec, compiled, environ={compiled.model.api_key_env: KEY})


class FakeOpenShell:
    """Records every `openshell` call; the sandbox call answers with `sandbox_stdout`."""

    def __init__(self, sandbox_stdout="", sandbox_code=0, raises=None, providers=""):
        self.calls, self.envs, self.stdin = [], [], []
        self.sandbox_stdout, self.sandbox_code, self.raises = sandbox_stdout, sandbox_code, raises
        self.providers = providers  # what `openshell provider list` prints

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        self.stdin.append(kwargs.get("input"))
        self.envs.append(kwargs.get("env") or {})
        is_sandbox = argv[1:3] == ["sandbox", "create"]
        if is_sandbox and self.raises:
            raise self.raises
        stdout = self.sandbox_stdout if is_sandbox else self.providers if argv[1:3] == ["provider", "list"] else ""
        return SimpleNamespace(returncode=self.sandbox_code if is_sandbox else 0, stdout=stdout, stderr="")

    def call(self, verb):
        """The (argv, env, stdin) of the first call with this verb, for example "sandbox create"."""
        i = self.verbs().index(verb)
        return self.calls[i], self.envs[i], self.stdin[i]

    def verbs(self):
        return [" ".join(c[1:3]) for c in self.calls]


def ok_result():
    return MARKER + RunResult(status="succeeded", text="hello").model_dump_json()


def test_the_runner_is_registered_and_refuses_a_tool_server_that_lives_on_this_machine():
    assert load_runner("sandbox").name == "sandbox"

    @tool(namespace="mine", description="Local.", mock_response="x")
    def local_tool(q: str) -> str:
        return q

    spec = AgentSpec.from_dict(
        {
            "name": "a",
            "model": {"provider": "openai", "model": "m", "credential_ref": "env://K"},
            "tools": ["mine.local_tool"],
        }
    )
    compiled = compile_agent(spec, ToolCatalog().add_tools("mine", [local_tool], command="python", args=["x.py"]))
    fake = FakeOpenShell()
    result = SandboxRunner(run=fake).run(compiled, "hi", environ={"K": KEY})
    assert not result.ok and "mine" in result.error and "cannot run in the sandbox" in result.error
    assert fake.calls == []  # nothing was started


def test_a_missing_key_is_reported_before_anything_starts():
    _, compiled, _ = personal()
    fake = FakeOpenShell()
    result = SandboxRunner(run=fake).run(compiled, "hi", environ={})
    assert not result.ok and compiled.model.api_key_env in result.error and fake.calls == []


def test_the_key_goes_only_through_the_environment_of_the_provider_command_and_the_provider_is_deleted():
    _, compiled, env = personal()
    fake = FakeOpenShell(ok_result())
    result = SandboxRunner(run=fake).run(compiled, "my prompt", environ=env)
    assert result.ok and result.text == "hello"
    assert fake.verbs() == [
        "provider list",  # the sweep for leftovers
        "provider profile",
        "provider create",
        "sandbox create",
        "provider delete",
    ]
    assert not any(KEY in " ".join(c) for c in fake.calls)  # never in a command line
    create_argv, create_env, _ = fake.call("provider create")
    assert create_env[compiled.model.api_key_env] == KEY  # only the provider command's environment carries it
    sandbox_call, sandbox_env, _ = fake.call("sandbox create")
    assert sandbox_call[sandbox_call.index("--provider") + 1] == create_argv[create_argv.index("--name") + 1]
    assert "--no-keep" in sandbox_call and "--policy" in sandbox_call and "--no-tty" in sandbox_call
    name = sandbox_call[sandbox_call.index("--name") + 1]
    assert len(name) <= 19  # OpenShell refuses longer names (found on a real gateway)
    assert KEY not in sandbox_env.get(compiled.model.api_key_env, "")  # the sandbox command does not get the key


def test_the_provider_is_deleted_even_when_the_sandbox_fails_and_errors_never_show_the_key():
    _, compiled, env = personal()
    fake = FakeOpenShell(raises=subprocess.TimeoutExpired(["openshell"], 5))
    result = SandboxRunner(run=fake).run(compiled, "hi", environ=env)
    assert not result.ok and "TimeoutExpired" in result.error
    assert fake.verbs()[-2:] == ["sandbox delete", "provider delete"]  # the VM is removed, then the key

    noisy = FakeOpenShell(sandbox_stdout=f"boom, the key was {KEY}", sandbox_code=1)
    result = SandboxRunner(run=noisy).run(compiled, "hi", environ=env)
    assert not result.ok and "no result" in result.error and KEY not in result.error and "****" in result.error
    assert noisy.verbs()[-1] == "provider delete"


def test_a_provider_left_by_a_killed_run_is_deleted_but_a_running_one_and_other_providers_are_not():
    import time

    old, fresh = f"ab-{int(time.time()) - 3600}-a1b2", f"ab-{int(time.time()) - 10}-d4e5"
    listing = f"NAME  TYPE  CREDENTIAL_KEYS\nopenrouter  openrouter  1\n{old}  x  1\n{fresh}  x  1\nab-notours  x  1\n"
    _, compiled, env = personal()
    fake = FakeOpenShell(ok_result(), providers=listing)
    SandboxRunner(run=fake, timeout=300).run(compiled, "hi", environ=env)
    deleted = [c[3] for c in fake.calls if c[1:3] == ["provider", "delete"]]
    assert old in deleted and fresh not in deleted and "openrouter" not in deleted and "ab-notours" not in deleted


def test_a_missing_openshell_program_is_a_plain_failure():
    _, compiled, env = personal()
    result = SandboxRunner(run=FakeOpenShell(raises=FileNotFoundError("openshell"))).run(compiled, "hi", environ=env)
    assert not result.ok and "FileNotFoundError" in result.error


def test_the_audit_log_path_is_dropped_with_a_warning_and_servers_use_the_image_python(tmp_path):
    _, compiled, env = personal(log=str(tmp_path / "log.jsonl"))
    assert any("--log" in s.args for s in compiled.servers)
    fake = FakeOpenShell(ok_result())
    result = SandboxRunner(run=fake).run(compiled, "hi", environ=env)
    assert any("audit log is not collected" in w for w in result.warnings)
    import json

    sandbox_call, _, sent_line = fake.call("sandbox create")
    assert "hi" not in sandbox_call  # the prompt is not on the command line (`ps` would show it)
    assert sent_line.endswith("\n") and sent_line.count("\n") == 1  # exactly one line: the reader stops there
    sent = json.loads(sent_line)
    assert sent["prompt"] == "hi" and KEY not in json.dumps(sent)
    for server in sent["compiled"]["servers"]:
        assert server["command"] == "/opt/venv/bin/python" and "--log" not in server["args"]


def test_both_runners_refuse_a_live_tier2_tool_without_approval_even_if_the_caller_did_not_check():
    from agentbuilder_nat import LocalRunner

    spec = AgentSpec.from_dict(
        {
            "name": "a",
            "model": {"provider": "openai", "model": "m", "credential_ref": "env://K"},
            "tools": ["calendar.create_event"],
        }
    )
    live = compile_agent(spec, personal_catalog())
    fake = FakeOpenShell()
    for runner in (LocalRunner(), SandboxRunner(run=fake)):
        result = runner.run(live, "hi", environ={"K": KEY})
        assert not result.ok and "need a person to approve each call" in result.error
    # The sandbox's tool servers run inside the VM, where the host cannot watch an approval folder: still refused.
    result = SandboxRunner(run=fake).run(live, "hi", environ={"K": KEY}, approve=lambda request: True)
    assert not result.ok and "the sandbox runner cannot ask for approvals yet" in result.error
    assert fake.calls == []  # no sandbox, no provider holding the key


# ---- the real thing ------------------------------------------------------------------------------------------

_ENV = {
    **os.environ,
    "PATH": os.pathsep.join(
        [p for p in ("/Applications/Docker.app/Contents/Resources/bin", "/opt/homebrew/bin") if os.path.isdir(p)]
        + [os.environ["PATH"]]
    ),
}


@pytest.mark.openshell
def test_the_agent_runs_inside_a_real_microvm_with_mock_tools_and_the_key_stays_out():
    """Fake model on this machine (reached as host.openshell.internal), mock Gmail tool inside the sandbox."""
    if not shutil.which("openshell", path=_ENV["PATH"]):
        pytest.skip("openshell is not installed")
    status = subprocess.run(["openshell", "status"], capture_output=True, text=True, timeout=30, env=_ENV, check=False)
    if "Connected" not in status.stdout:
        pytest.skip("no OpenShell gateway is running")
    model = FakeModel(
        [Turn.react("gmail__read", {"query": "is:unread"}), Turn.react_final("You have mail from Alice.")]
    )
    with FakeOpenAIServer(model, host="127.0.0.1") as server:
        port = server.base_url.rsplit(":", 1)[1].split("/")[0]
        _, compiled, env = personal(f"http://host.openshell.internal:{port}/v1")
        result = SandboxRunner().run(compiled, "Any unread mail?", environ=env)
    if not result.ok and "failed to resolve vm sandbox image" in (result.error or ""):
        pytest.skip("the sandbox image is not built: make sandbox-image-sdk")
    assert result.ok and result.text == "You have mail from Alice.", result.error
    assert result.trajectory.tools_used == ["gmail__read"]
    assert "Lunch on Friday?" in str(result.trajectory.real_tool_calls[0].result)  # the mock tool ran in the sandbox
    assert model.remaining == 0  # the model call really crossed the sandbox boundary
    assert KEY not in result.model_dump_json()
    leftovers = subprocess.run(
        ["openshell", "provider", "list"], capture_output=True, text=True, env=_ENV, check=False
    ).stdout
    assert "ab-" not in leftovers  # the per-run provider (and the key it held) is gone
