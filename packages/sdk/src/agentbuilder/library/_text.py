"""Helpers that make untrusted text (mail, events, web pages) and tool inputs safe to pass around."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from agentbuilder.library.google import ToolError

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]")  # control and bidi-override characters
_EMAIL = re.compile(r"^[^@\s<>,;\"'\\]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")


def clean(value: object, limit: int) -> str:
    """One line of plain text, at most `limit` characters, with control characters removed."""
    text = " ".join(_CONTROL.sub(" ", str(value or "")).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def email(value: str) -> str:
    """A single plain address. Anything that could add a recipient or a header (comma, newline, <>) is refused."""
    if len(value) > 254 or not _EMAIL.match(value.strip()):
        raise ToolError(f"'{clean(value, 60)}' is not a single plain email address like name@example.com")
    return value.strip()


def timestamp(value: str, name: str) -> datetime:
    """An ISO 8601 time with a timezone, for example 2026-11-06T09:00:00+05:30 or ...Z."""
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ToolError(f"{name} must be an ISO 8601 time like 2026-11-06T09:00:00+05:30") from None
    if parsed.tzinfo is None:
        raise ToolError(f"{name} needs a timezone, for example 2026-11-06T09:00:00+05:30 or ...Z")
    return parsed


def time_range(start: str, end: str, *, max_days: int) -> tuple[datetime, datetime]:
    a, b = timestamp(start, "start"), timestamp(end, "end")
    if b <= a:
        raise ToolError("end must be after start")
    if b - a > timedelta(days=max_days):
        raise ToolError(f"the time range may be at most {max_days} days")
    return a, b
