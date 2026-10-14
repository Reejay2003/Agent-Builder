"""The demo tools, defined with the SDK. Served by demo_server.py; manifest: packages/tool-manifests/demo_tools.manifest.json."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agentbuilder.tools import tool


@tool(
    namespace="demo",
    description="Tells the agent the current date and time in a chosen timezone. Reads the computer clock only.",
    rate_limit_per_minute=60,
    mock_response="2026-01-01 12:00:00 UTC (Thursday)",
)
def get_current_time(timezone: str = "UTC") -> str:
    try:
        return datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S %Z (%A)")
    except ZoneInfoNotFoundError:
        return f"Unknown timezone '{timezone}'. Use an IANA name such as 'Asia/Kolkata'."


@tool(namespace="demo", description="Adds two numbers. Pure calculation.", rate_limit_per_minute=120, mock_response=3.0)
def add_numbers(a: float, b: float) -> float:
    return a + b


@tool(namespace="demo", description="Counts the words in text the agent gives it. Pure calculation.", rate_limit_per_minute=120, mock_response=5)
def count_words(text: str) -> int:
    return len(text.split())


TOOLS = [get_current_time, add_numbers, count_words]
