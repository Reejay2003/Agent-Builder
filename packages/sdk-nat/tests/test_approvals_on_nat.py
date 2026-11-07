"""Human approvals end to end on the real stack: NAT starts the tool server, the server asks, LocalRunner answers."""

import importlib.util
import sys
import textwrap

import pytest

pytest.importorskip("nemo_fabric")

from agentbuilder.compile import compile_agent
from agentbuilder.runtime import credential_env
from agentbuilder.spec import AgentSpec
from agentbuilder.testing import FakeModel, FakeOpenAIServer, ToolCall, Turn
from agentbuilder.tools import ToolCatalog

from agentbuilder_nat import LocalRunner

TOOLS = textwrap.dedent(
    """
    import os
    from agentbuilder.tools import tool

    @tool(namespace="cal", description="Invite someone.", risk=2, side_effects="external_comms", mock_response="m")
    def invite(who: str) -> str:
        with open(os.environ.get("PROOF") or __file__ + ".ran", "w") as f:  # proof the function really ran
            f.write(who)
        return "invited " + who
    """
)
SERVER = "import sys; sys.path.insert(0, sys.argv[1]); from cal_tools import invite\n" + (
    "from agentbuilder.tools.mcp_server import main\nmain([invite], argv=sys.argv[2:])\n"
)


def _agent(tmp_path, base_url):
    (tmp_path / "cal_tools.py").write_text(TOOLS)
    (tmp_path / "server.py").write_text(SERVER)
    spec_ = importlib.util.spec_from_file_location("cal_tools", tmp_path / "cal_tools.py")
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)
    catalog = ToolCatalog().add_tools(
        "cal", [module.invite], command=sys.executable, args=[str(tmp_path / "server.py"), str(tmp_path)]
    )
    spec = AgentSpec.from_dict(
        {
            "spec_version": 1,
            "name": "inviter",
            "model": {
                "provider": "openai",
                "model": "m",
                "base_url": base_url,
                "agent_mode": "tool_calling",
                "credential_ref": "env://OPENAI_API_KEY",
            },
            "tools": ["cal.invite"],  # tier 2; approvals.tier2_external_comms defaults to require_human
        }
    )
    compiled = compile_agent(spec, catalog)
    return compiled, credential_env(spec, compiled, environ={compiled.model.api_key_env: "sk-test-" + "a" * 32})


@pytest.mark.parametrize("answer", [True, False])
def test_a_live_tier2_call_on_real_nat_runs_only_after_a_person_says_yes(tmp_path, answer):
    asked = []

    def approve(request):
        asked.append((request.tool_id, request.arguments))
        return answer

    model = FakeModel([Turn.calls(ToolCall("invite", {"who": "alice@example.com"})), Turn.say("Done.")])
    with FakeOpenAIServer(model) as server:
        compiled, env = _agent(tmp_path, server.base_url)
        assert (
            LocalRunner()
            .run(compiled, "Invite Alice", environ=env)
            .error.startswith("live runs of cal.invite need a person to approve")
        )  # no approver: refused, nothing started
        result = LocalRunner().run(compiled, "Invite Alice", environ=env, approve=approve)
    assert result.ok, result.error
    assert asked == [("cal.invite", {"who": "alice@example.com"})]
    assert (tmp_path / "cal_tools.py.ran").exists() is answer
    tool_result = str(result.trajectory.real_tool_calls[0].result)
    assert ("invited alice@example.com" in tool_result) if answer else ("a person declined" in tool_result)
