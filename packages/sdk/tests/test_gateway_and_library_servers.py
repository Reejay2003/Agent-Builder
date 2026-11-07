import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agentbuilder.compile import compile_agent, to_openshell_policy
from agentbuilder.gateway import LocalGateway, default_audit_log
from agentbuilder.library import personal_catalog
from agentbuilder.runtime import RunResult
from agentbuilder.server import LocalServer
from agentbuilder.spec import AgentSpec
from agentbuilder.tools import ToolCatalog, manifests_document
from tests.conftest import EXAMPLES
from tests.fixtures_tools import demo_catalog

MANIFEST = Path(__file__).resolve().parents[2] / "tool-manifests" / "personal_tools.manifest.json"


async def call(args, tool, arguments, env=None):
    params = StdioServerParameters(command=sys.executable, args=args, env=env)
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        listed = sorted(t.name for t in (await s.list_tools()).tools)
        out = await s.call_tool(tool, arguments)
        return listed, out


def server_args(catalog, name):
    binding = catalog.server(name)
    return [*binding.args]


# ---- the library servers over real MCP ---------------------------------------------------------------------------


def test_each_namespace_serves_only_its_own_tools_and_mock_mode_touches_nothing(tmp_path):
    catalog = personal_catalog()
    home = {"HOME": str(tmp_path), "PATH": os.environ["PATH"]}  # no Google sign-in exists in this home
    log = tmp_path / "calls.jsonl"
    expected = {
        "gmail": ["read", "send_draft"],
        "calendar": ["create_event", "list_events"],
        "sheets": ["read"],
        "web": ["search"],
    }
    for ns, names in expected.items():
        server = [*server_args(catalog, ns), "--mock", "--log", str(log)]
        listed, out = asyncio.run(call(server, names[0], _sample_args(ns), env=home))
        assert listed == names and not out.isError, (ns, out.content)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [c["id"] for c in calls] == ["gmail.read", "calendar.create_event", "sheets.read", "web.search"]
    assert all(c["mock"] is True for c in calls)


def _sample_args(ns):
    return {
        "gmail": {"query": "is:unread"},
        "calendar": {"title": "x", "start": "2026-11-06T09:00:00Z", "end": "2026-11-06T10:00:00Z", "attendees": []},
        "sheets": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "cell_range": "A1:B2"},
        "web": {"query": "python"},
    }[ns]


def test_without_mock_and_without_a_sign_in_the_tool_says_how_to_sign_in(tmp_path):
    catalog = personal_catalog()
    env = {"HOME": str(tmp_path), "PATH": os.environ["PATH"]}
    _, out = asyncio.run(call(server_args(catalog, "gmail"), "read", {"query": "x"}, env=env))
    assert out.isError and "ab auth google" in out.content[0].text


def test_the_committed_manifest_matches_the_tool_definitions():
    from agentbuilder.library.catalog import TOOLS_BY_NAMESPACE

    tools = [t for ts in TOOLS_BY_NAMESPACE.values() for t in ts]
    generated = manifests_document(
        "agentbuilder-personal",
        "agentbuilder.library (python -m agentbuilder.library.server <namespace>)",
        [t.manifest for t in tools],
    )
    assert json.loads(MANIFEST.read_text()) == generated, (
        "regenerate packages/tool-manifests/personal_tools.manifest.json"
    )


def test_the_template_compiles_to_least_privilege_network_rules():
    spec = AgentSpec.load(EXAMPLES / "personal_automation.agent.yaml")
    policy = to_openshell_policy(compile_agent(spec, personal_catalog()))
    hosts = {k: sorted(e["host"] for e in v["endpoints"]) for k, v in policy["network_policies"].items()}
    assert hosts == {
        "tools_gmail": ["gmail.googleapis.com", "oauth2.googleapis.com"],
        "tools_calendar": ["oauth2.googleapis.com", "www.googleapis.com"],
        "tools_sheets": ["oauth2.googleapis.com", "sheets.googleapis.com"],
        "tools_web": ["html.duckduckgo.com"],
    }
    access = {k: {e["access"] for e in v["endpoints"]} for k, v in policy["network_policies"].items()}
    assert access["tools_sheets"] == {"read-only"} and access["tools_gmail"] == {"read-write"}


# ---- the gateway ------------------------------------------------------------------------------------------------


def test_gateway_adds_mock_and_the_shared_log_to_sdk_servers_without_changing_the_original(tmp_path):
    original = personal_catalog()
    log = str(tmp_path / "state" / "calls.jsonl")
    wrapped = LocalGateway().apply(original, mock=True, audit_log=log)
    for name in ("gmail", "calendar", "sheets", "web"):
        assert wrapped.server(name).args[-3:] == ["--mock", "--log", log]
        assert "--mock" not in original.server(name).args  # the input is untouched
    assert (tmp_path / "state").is_dir() and wrapped.tool_ids == original.tool_ids
    live = LocalGateway().apply(original, mock=False)
    assert "--mock" not in live.server("gmail").args and "--log" not in live.server("gmail").args


def test_gateway_refuses_mock_for_a_server_it_cannot_make_safe():
    from agentbuilder.tools import McpServerBinding, ToolManifest

    byo = ToolCatalog().add_server(
        McpServerBinding(name="thirdparty", command="npx", args=["some-server"]),
        [ToolManifest(id="thirdparty.go", mcp_name="go", description_plain="Does a thing.", input_schema={})],
    )
    assert LocalGateway().apply(byo, mock=False).server("thirdparty").args == ["some-server"]
    with pytest.raises(ValueError, match="mock mode is not available"):
        LocalGateway().apply(byo, mock=True)


def test_the_default_audit_log_lives_in_the_users_state_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert default_audit_log() == str(tmp_path / "agentbuilder" / "tool-calls.jsonl")


# ---- the server's `mock` switch ---------------------------------------------------------------------------------

SPEC = {
    "name": "assistant",
    "model": {"provider": "openai", "model": "gpt-4.1-mini", "credential_ref": "env://OPENAI_API_KEY"},
    "tools": ["demo.add_numbers"],
}


class Capture:
    name = "capture"

    def __init__(self):
        self.compiled = []

    def run(self, compiled, prompt, *, environ=None):
        self.compiled.append(compiled)
        return RunResult(status="succeeded", text="ok")


def run_and_wait(app, body):
    status, started = app.start_run(body)
    assert status == 202
    for _ in range(100):
        _, run = app.get_run(started["run_id"])
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("did not finish")


def test_a_test_run_is_mock_by_default_and_live_only_when_asked(tmp_path):
    capture = Capture()
    app = LocalServer(
        token="t",
        catalog=demo_catalog(),
        runner_factory=lambda: capture,
        environ={"OPENAI_API_KEY": "k" * 20},
        audit_log=str(tmp_path / "log.jsonl"),
    )
    try:
        assert run_and_wait(app, {"spec": SPEC, "prompt": "hi"})["status"] == "succeeded"
        assert run_and_wait(app, {"spec": SPEC, "prompt": "hi", "mock": False})["status"] == "succeeded"
    finally:
        app.shutdown()
    assert "--mock" in capture.compiled[0].servers[0].args and "--mock" not in capture.compiled[1].servers[0].args
    assert capture.compiled[0].servers[0].args[-2:] == ["--log", str(tmp_path / "log.jsonl")]


def test_a_non_boolean_mock_is_a_field_error():
    from agentbuilder.server.app import _Invalid

    app = LocalServer(token="t", catalog=demo_catalog())
    try:
        with pytest.raises(_Invalid) as bad:
            app.start_run({"spec": SPEC, "prompt": "hi", "mock": "yes"})
    finally:
        app.shutdown()
    assert bad.value.problems[0]["field"] == "mock"


def test_live_run_of_a_tier2_tool_is_refused_until_approvals_exist_but_mock_and_allow_work():
    from agentbuilder.library import personal_catalog
    from agentbuilder.server.app import _Invalid

    spec = {**SPEC, "tools": ["calendar.create_event"]}
    capture = Capture()
    app = LocalServer(
        token="t",
        catalog=personal_catalog(),
        runner_factory=lambda: capture,
        environ={"OPENAI_API_KEY": "k" * 20},
    )
    try:
        with pytest.raises(_Invalid) as bad:
            app.start_run({"spec": spec, "prompt": "hi", "mock": False})
        assert bad.value.problems[0]["field"] == "mock"
        assert "calendar.create_event" in bad.value.problems[0]["message"] and not capture.compiled
        assert run_and_wait(app, {"spec": spec, "prompt": "hi"})["status"] == "succeeded"  # mock is fine
        allowed = {**spec, "approvals": {"tier2_external_comms": "allow"}}
        assert run_and_wait(app, {"spec": allowed, "prompt": "hi", "mock": False})["status"] == "succeeded"
    finally:
        app.shutdown()


def test_only_finished_runs_are_forgotten_and_too_many_waiting_runs_are_refused(monkeypatch):
    import threading

    from agentbuilder.server import app as app_module

    monkeypatch.setattr(app_module, "MAX_RUNS", 3)
    release = threading.Event()

    class Slow:
        name = "slow"

        def run(self, compiled, prompt, *, environ=None):
            release.wait(10)
            return RunResult(status="succeeded", text=prompt)

    app = LocalServer(token="t", catalog=demo_catalog(), runner_factory=Slow, environ={"OPENAI_API_KEY": "k" * 20})
    try:
        ids = [app.start_run({"spec": SPEC, "prompt": f"p{i}"})[1]["run_id"] for i in range(3)]  # 2 run, 1 waits
        status, body = app.start_run({"spec": SPEC, "prompt": "one too many"})
        assert status == 429 and "too many runs" in body["errors"][0]["message"]
        assert all(app.get_run(i)[0] == 200 for i in ids)  # nothing still running was dropped
        release.set()
        for i in ids:
            for _ in range(100):
                if app.get_run(i)[1]["status"] != "running":
                    break
                time.sleep(0.05)
        new = app.start_run({"spec": SPEC, "prompt": "later"})[1]["run_id"]
        assert app.get_run(new)[0] == 200 and app.get_run(ids[0])[0] == 404  # the oldest FINISHED run made room
    finally:
        release.set()
        app.shutdown()
