"""Demo MCP server (stdio) for the Agent Builder tool store. Three read-only, side-effect-free tools.
Manifest: packages/tool-manifests/demo_tools.manifest.json   Run standalone: python packages/mcp-tools/demo_server.py
"""
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-builder-demo")
import sys

CALL_LOG = os.environ.get("AB_TOOL_LOG", "/tmp/ab-demo-tool-calls.jsonl")  # audit log used by tests as proof a tool really ran
if "--log" in sys.argv:  # per-run log path (lets tests run in parallel)
    CALL_LOG = sys.argv[sys.argv.index("--log") + 1]


def _log(tool: str, **args) -> None:
    with open(CALL_LOG, "a") as f:
        f.write(json.dumps({"t": time.time(), "tool": tool, "args": args}) + "\n")


@mcp.tool()
def get_current_time(timezone: str = "UTC") -> str:
    """Return the current date and time in an IANA timezone such as 'Asia/Kolkata' or 'UTC'."""
    _log("get_current_time", timezone=timezone)
    try:
        return datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S %Z (%A)")
    except ZoneInfoNotFoundError:
        return f"Unknown timezone '{timezone}'. Use an IANA name such as 'Asia/Kolkata'."


@mcp.tool()
def add_numbers(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    _log("add_numbers", a=a, b=b)
    return a + b


@mcp.tool()
def count_words(text: str) -> int:
    """Count the words in a piece of text."""
    _log("count_words")
    return len(text.split())


if __name__ == "__main__":
    mcp.run(transport="stdio")
