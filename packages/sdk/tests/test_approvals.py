"""Human approvals: the tool server asks through a folder, the host answers (agentbuilder.approvals)."""

import asyncio
import json
import sys
import textwrap
import threading

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agentbuilder import approvals
from agentbuilder.approvals import (
    ApprovalRequest,
    ApprovalWatcher,
    terminal_approver,
    wait_for_approval,
    with_approvals,
)
from agentbuilder.compile import compile_agent, to_nat_workflow, unapproved_live_tools
from agentbuilder.gateway import LocalGateway
from agentbuilder.library import personal_catalog
from agentbuilder.spec import AgentSpec
from agentbuilder.tools import ToolCatalog
from agentbuilder.tools.catalog import McpServerBinding

SERVER = textwrap.dedent(
    """
    import pathlib, sys
    from agentbuilder.tools import tool
    from agentbuilder.tools.mcp_server import main

    @tool(namespace="cal", description="Invite people.", risk=2, side_effects="external_comms", mock_response="m")
    def invite(who: str) -> str:
        pathlib.Path(sys.argv[-1]).write_text(who)  # proof the function really ran
        return "invited " + who

    if __name__ == "__main__":
        main([invite], argv=sys.argv[1:-1])
    """
)


async def _call(script, args, ran):
    params = StdioServerParameters(command=sys.executable, args=[str(script), *args, str(ran)])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        out = await s.call_tool("invite", {"who": "alice@example.com"})
        return out.isError, out.content[0].text


@pytest.mark.parametrize("answer", [True, False])
def test_the_tool_server_runs_the_tool_only_after_a_yes_and_the_person_sees_the_exact_payload(tmp_path, answer):
    script, ran, log, folder = tmp_path / "srv.py", tmp_path / "ran.txt", tmp_path / "calls.jsonl", tmp_path / "ask"
    script.write_text(SERVER)
    seen = []

    def approve(request):
        seen.append(request)
        return answer

    args = ["--log", str(log), "--approvals", str(folder), "--approve", "cal.invite"]
    with ApprovalWatcher(folder, approve):
        is_error, text = asyncio.run(_call(script, args, ran))
    assert [(r.tool_id, r.risk_tier, r.arguments) for r in seen] == [("cal.invite", 2, {"who": "alice@example.com"})]
    assert ran.exists() is answer and is_error is not answer
    assert text == "invited alice@example.com" if answer else "a person declined" in text
    assert json.loads(log.read_text())["approval"] == ("approved" if answer else "declined")
    assert list(folder.iterdir()) == []  # request and decision files are cleaned up
    assert oct(folder.stat().st_mode & 0o777) == "0o700"


def test_mock_mode_never_asks_and_a_tool_not_listed_never_waits(tmp_path):
    script, ran = tmp_path / "srv.py", tmp_path / "ran.txt"
    script.write_text(SERVER)
    folder = tmp_path / "ask"
    folder.mkdir()
    is_error, text = asyncio.run(_call(script, ["--mock", "--approvals", str(folder), "--approve", "cal.invite"], ran))
    assert (is_error, text, ran.exists()) == (False, "m", False)
    is_error, text = asyncio.run(_call(script, ["--approvals", str(folder), "--approve", "other.tool"], ran))
    assert not is_error and ran.exists()  # the approval list names the tools; an unlisted tool is not asked about


def test_no_answer_in_time_is_a_no(tmp_path):
    clock = iter(range(0, 100, 10))
    assert wait_for_approval(tmp_path, "x.y", 2, {}, timeout=25, sleep=lambda s: None, clock=lambda: next(clock)) == (
        "expired"
    )
    assert list(tmp_path.iterdir()) == []


def test_an_approver_that_crashes_counts_as_no(tmp_path):
    def broken(request):
        raise RuntimeError("the approval UI is down")

    result = []
    with ApprovalWatcher(tmp_path / "ask", broken):
        t = threading.Thread(target=lambda: result.append(wait_for_approval(tmp_path / "ask", "x.y", 2, {}, timeout=5)))
        t.start()
        t.join(10)
    assert result == ["declined"]


def test_the_terminal_approver_shows_the_payload_and_needs_an_explicit_yes():
    request = ApprovalRequest(id="a", tool_id="cal.invite", risk_tier=2, arguments={"who": "bob"}, created=0)
    shown = []
    assert terminal_approver(ask=lambda q: "y", show=shown.append)(request) is True
    assert '"who": "bob"' in shown[0] and "cal.invite (tier 2)" in shown[0]
    for reply in ("", "n", "yes please", "Y E S"):
        assert terminal_approver(ask=lambda q, r=reply: r, show=shown.append)(request) is False

    def closed(q):
        raise EOFError

    assert terminal_approver(ask=closed, show=shown.append)(request) is False


def _personal(catalog):
    spec = AgentSpec.from_dict(
        {
            "spec_version": 1,
            "name": "a",
            "model": {"provider": "openai", "model": "m"},
            "tools": ["calendar.create_event", "calendar.list_events", "gmail.read"],
        }
    )
    return compile_agent(spec, catalog)


def test_only_live_sdk_servers_holding_a_tool_that_needs_approval_are_told_to_ask(tmp_path):
    c = with_approvals(_personal(personal_catalog()), tmp_path)
    args = {s.name: s.args for s in c.servers}
    assert args["calendar"][-4:] == ["--approvals", str(tmp_path), "--approve", "calendar.create_event"]
    assert "--approvals" not in args["gmail"]  # nothing there needs a person
    assert unapproved_live_tools(c) == []
    groups = to_nat_workflow(c)["function_groups"]
    assert groups["calendar"]["tool_call_timeout"] == int(approvals.APPROVAL_TIMEOUT) + 60  # NAT's default is 60 s
    assert "tool_call_timeout" not in groups["gmail"]

    mocked = with_approvals(_personal(LocalGateway().apply(personal_catalog(), mock=True)), tmp_path)
    assert not any("--approvals" in s.args for s in mocked.servers)  # mock never asks

    manifests = [t.manifest for t in personal_catalog().resolve(["calendar.create_event", "calendar.list_events"])]
    byo = ToolCatalog().add_server(McpServerBinding(name="calendar", command="theirs", args=[]), manifests)
    byo = byo.add_server(
        McpServerBinding(name="gmail", command="theirs", args=[]),
        [t.manifest for t in personal_catalog().resolve(["gmail.read"])],
    )
    assert unapproved_live_tools(with_approvals(_personal(byo), tmp_path)) == ["calendar.create_event"]
