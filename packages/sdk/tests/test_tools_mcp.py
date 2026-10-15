"""The SDK's MCP server wrapper, exercised through a real MCP client over stdio."""

import asyncio
import json
import sys
import textwrap

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = textwrap.dedent(
    """
    from agentbuilder.tools import tool
    from agentbuilder.tools.mcp_server import main

    @tool(namespace="demo", description="Add two numbers.", mock_response=-1.0)
    def add_numbers(a: float, b: float) -> float:
        return a + b

    @tool(namespace="demo", description="Count words.", mock_response=0)
    def count_words(text: str) -> int:
        return len(text.split())

    if __name__ == "__main__":
        main([add_numbers, count_words])
    """
)


async def _session(script, extra_args):
    params = StdioServerParameters(command=sys.executable, args=[str(script), *extra_args])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = (await s.list_tools()).tools
        out = await s.call_tool("add_numbers", {"a": 2, "b": 40.5})
        return tools, out.content[0].text


def test_server_lists_tools_runs_them_and_writes_an_audit_log(tmp_path):
    script, log = tmp_path / "srv.py", tmp_path / "calls.jsonl"
    script.write_text(SERVER)
    tools, text = asyncio.run(_session(script, ["--log", str(log), "--log-args"]))
    assert sorted(t.name for t in tools) == ["add_numbers", "count_words"]
    assert {t.name: t.description for t in tools}["add_numbers"] == "Add two numbers."
    assert text == "42.5"
    schema = next(t for t in tools if t.name == "add_numbers").inputSchema
    assert set(schema["properties"]) == {"a", "b"}
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert (
        rows[0]["tool"] == "add_numbers"
        and rows[0]["id"] == "demo.add_numbers"
        and rows[0]["args"] == {"a": 2, "b": 40.5}
    )
    assert rows[0]["mock"] is False


def test_audit_log_hides_argument_values_by_default_and_is_private(tmp_path):
    script, log = tmp_path / "srv.py", tmp_path / "calls.jsonl"
    script.write_text(SERVER)
    asyncio.run(_session(script, ["--log", str(log)]))
    row = json.loads(log.read_text().splitlines()[0])
    assert row["tool"] == "add_numbers" and "40.5" not in log.read_text()
    assert row["args"] == {"a": "float(3)", "b": "float(4)"}  # type and size only, never the value
    assert oct(log.stat().st_mode & 0o777) == "0o600"


def test_server_refuses_clashing_names_and_missing_mocks():
    from agentbuilder.tools import tool
    from agentbuilder.tools.mcp_server import build_server

    @tool(namespace="a", name="read", description="A.", mock_response="a")
    def a(q: str) -> str:
        return ""

    @tool(namespace="b", name="read", description="B.", mock_response="b")
    def b(q: str) -> str:
        return ""

    @tool(namespace="c", description="C.")  # no mock_response
    def c(q: str) -> str:
        return ""

    with pytest.raises(ValueError, match="share the MCP tool name 'read'"):
        build_server([a, b])
    with pytest.raises(ValueError, match=r"mock_response on every tool; missing: \['c.c'\]"):
        build_server([a, c], mock=True)
    build_server([a, c])  # a missing mock matters only in mock mode


def test_mock_mode_returns_the_mock_and_never_runs_the_function(tmp_path):
    script, log = tmp_path / "srv.py", tmp_path / "calls.jsonl"
    script.write_text(SERVER)
    _, text = asyncio.run(_session(script, ["--mock", "--log", str(log)]))
    assert text == "-1.0"  # the mock_response, not 42.5
    assert json.loads(log.read_text().splitlines()[0])["mock"] is True
