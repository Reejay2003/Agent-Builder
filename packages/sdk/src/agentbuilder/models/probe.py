"""The model check (PLAN 4.4.1, reduced to one call by the 2026-11-05 decision).

One chat completion offers the model a single tool and requires it to call it. That one call proves four things at once:
the endpoint answers, the key is accepted, the model exists, and the model can use tools. The result tells the wizard
what to write into the spec: `agent_mode: auto` when native tool calling works, `react` when it does not.
A probe is a sample, not proof: the eval gate does the real measuring."""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from agentbuilder.models.credentials import redact
from agentbuilder.models.providers import ResolvedModel
from agentbuilder.repair import call_with_retry

TOOL = {
    "type": "function",
    "function": {
        "name": "add_numbers",
        "description": "Add two numbers.",
        "parameters": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
}


@dataclass(frozen=True)
class ProbeResult:
    ok: bool  # the model answered the call; False for a bad key, a missing model, an unreachable server
    tool_calling: bool | None  # None when the call itself failed, so nothing was learned
    agent_mode: Literal["auto", "react"] | None  # what the wizard should write; None = leave the spec alone
    message: str  # plain words for the user


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None  # a redirect would carry the key to another host


_OPENER = urllib.request.build_opener(_NoRedirect)


def _post(url: str, headers: Mapping[str, str], body: bytes) -> tuple[int, Mapping[str, str], str]:
    request = urllib.request.Request(url, data=body, headers=dict(headers))
    try:
        with _OPENER.open(request, timeout=30) as response:
            reply = response.read(1_000_000).decode("utf-8", "replace")
            return int(response.status), _titled(response.headers), reply
    except urllib.error.HTTPError as exc:
        return exc.code, _titled(exc.headers), exc.read(20_000).decode("utf-8", "replace")


def _titled(headers: Any) -> dict[str, str]:
    return {k.title(): v for k, v in headers.items()}  # header names are case-insensitive; look them up as Retry-After


def _valid_call(payload: Any) -> bool:
    try:
        call = payload["choices"][0]["message"]["tool_calls"][0]["function"]
        args = json.loads(call["arguments"])
        return bool(
            call["name"] == "add_numbers"
            and all(isinstance(args[k], (int, float)) and not isinstance(args[k], bool) for k in ("a", "b"))
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def probe_tool_calling(
    model: ResolvedModel,
    *,
    post: Callable[..., tuple[int, Mapping[str, str], str]] = _post,
    sleep: Callable[[float], None] = time.sleep,
) -> ProbeResult:
    """Spends one request. A second one only when the first says "no tools": some providers reject or ignore
    `tool_choice: required` although the model can call tools, so it is asked once more with `auto` before the wizard
    is told to fall back to ReAct. Each request may be repeated twice after a 429 or 5xx with a short wait."""
    first = _attempt(model, "required", post, sleep)
    if first.tool_calling is False:
        second = _attempt(model, "auto", post, sleep)
        if second.tool_calling:
            return second
    return first


def _attempt(
    model: ResolvedModel,
    tool_choice: str,
    post: Callable[..., tuple[int, Mapping[str, str], str]],
    sleep: Callable[[float], None],
) -> ProbeResult:
    headers = {"Content-Type": "application/json"}
    if model.api_key:
        headers["Authorization"] = f"Bearer {model.api_key.reveal()}"
    body = json.dumps(
        {
            "model": model.model,
            "messages": [{"role": "user", "content": "What is 17 plus 25? Use the add_numbers tool."}],
            "tools": [TOOL],
            "tool_choice": tool_choice,
        }
    ).encode()
    try:
        status, _, text = call_with_retry(
            lambda: post(f"{model.base_url}/chat/completions", headers, body), sleep=sleep
        )
    except (OSError, http.client.HTTPException) as exc:  # HTTPException: a garbled or cut-off reply
        return ProbeResult(False, None, None, f"could not reach {model.base_url} ({type(exc).__name__})")
    text = redact(text, [model.api_key])
    if 200 <= status < 300:
        try:
            payload = json.loads(text)
        except ValueError:
            return ProbeResult(False, None, None, "the endpoint answered, but not in the OpenAI chat format")
        if _valid_call(payload):
            return ProbeResult(True, True, "auto", "works, and the model can use tools")
        return ProbeResult(
            True, False, "react", "works, but the model did not call the tool when told to: it will run in ReAct mode"
        )
    detail = text[:200].replace("\n", " ")
    if status in (401, 403):
        return ProbeResult(False, None, None, "the key was rejected: check it and try again")
    if status == 404:
        return ProbeResult(False, None, None, "the endpoint or the model name was not found: check both")
    if status in (400, 422) and any(w in text.lower() for w in ("tool", "function")):
        return ProbeResult(True, False, "react", f"this model does not support tool calling ({detail}): ReAct mode")
    if status == 429:
        return ProbeResult(False, None, None, "rate limited or out of quota: try again later")
    return ProbeResult(False, None, None, f"the provider answered HTTP {status}: {detail}")
