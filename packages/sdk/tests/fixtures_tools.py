"""Tool fixtures for compiler tests: the demo tools plus a few realistic, risk-tiered ones (stubs; never called)."""

import sys
from pathlib import Path

from agentbuilder.tools import ToolCatalog, tool

DEMO_DIR = Path(__file__).resolve().parents[2] / "mcp-tools"  # packages/mcp-tools


@tool(namespace="demo", description="Adds two numbers. Pure calculation.", mock_response=3.0)
def add_numbers(a: float, b: float) -> float:
    return a + b


@tool(namespace="demo", description="Counts the words in text. Pure calculation.", mock_response=5)
def count_words(text: str) -> int:
    return len(text.split())


@tool(
    namespace="demo",
    description="Current date and time in a timezone.",
    mock_response="2026-01-01 12:00:00 UTC (Thursday)",
)
def get_current_time(timezone: str = "UTC") -> str:
    return "now"


@tool(
    namespace="gmail",
    description="Read recent email headers and bodies.",
    scopes=["gmail.readonly"],
    egress_hosts=["gmail.googleapis.com"],
    creds_required=["google_oauth"],
)
def read(query: str, limit: int = 10) -> list[str]:
    return []


@tool(
    namespace="gmail",
    description="Create an email draft for the user to review. Does not send.",
    risk=1,
    scopes=["gmail.compose"],
    egress_hosts=["gmail.googleapis.com"],
    creds_required=["google_oauth"],
)
def send_draft(to: str, subject: str, body: str) -> str:
    return "draft"


@tool(
    namespace="calendar",
    description="List calendar events in a date range.",
    scopes=["calendar.readonly"],
    egress_hosts=["www.googleapis.com"],
    creds_required=["google_oauth"],
)
def list_events(start: str, end: str) -> list[str]:
    return []


@tool(
    namespace="calendar",
    description="Create a calendar event; invites other people.",
    risk=2,
    side_effects="external_comms",
    scopes=["calendar.events"],
    egress_hosts=["www.googleapis.com"],
    creds_required=["google_oauth"],
)
def create_event(title: str, start: str, end: str, attendees: list[str]) -> str:
    return "event"


@tool(
    namespace="sheets",
    name="read",
    description="Read cells from a spreadsheet.",
    scopes=["sheets.readonly"],
    egress_hosts=["sheets.googleapis.com"],
    creds_required=["google_oauth"],
)
def read_sheet(sheet_id: str, cell_range: str) -> list[list[str]]:
    return []


@tool(namespace="web", description="Search the web and return result snippets.", egress_hosts=["search.example.org"])
def search(query: str) -> list[str]:
    return []


@tool(
    namespace="finance",
    description="Refund an order to the customer's card.",
    risk=3,
    side_effects="financial",
    egress_hosts=["api.payments.example.com"],
    creds_required=["payments_key"],
)
def refund(order_id: str, amount: float) -> str:
    return "refunded"


def demo_catalog(server_script: str = "packages/mcp-tools/demo_server.py", python: str = "python") -> ToolCatalog:
    return ToolCatalog().add_tools(
        "demo", [get_current_time, add_numbers, count_words], command=python, args=[server_script]
    )


def full_catalog() -> ToolCatalog:
    cat = demo_catalog()
    cat.add_tools("gmail", [read, send_draft], command="python", args=["gmail_server.py"])
    cat.add_tools("calendar", [list_events, create_event], command="python", args=["calendar_server.py"])
    cat.add_tools("finance", [refund], command="python", args=["finance_server.py"])
    cat.add_tools("sheets", [read_sheet], command="python", args=["sheets_server.py"])
    cat.add_tools("web", [search], command="python", args=["web_server.py"])
    return cat


def demo_tools_on_path() -> None:
    """Make packages/mcp-tools importable (the real demo tool definitions)."""
    if str(DEMO_DIR) not in sys.path:
        sys.path.insert(0, str(DEMO_DIR))
