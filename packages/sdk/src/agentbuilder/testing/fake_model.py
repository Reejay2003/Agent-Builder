"""A scripted fake LLM for offline, deterministic, free tests.

    model = FakeModel([Turn.calls(ToolCall("add_numbers", {"a": 1, "b": 2})), Turn.say("The sum is 3.")])

Each call to `respond()` plays the next scripted turn. Tool names in a script may be bare (`add_numbers`); they are
resolved against the tools the agent actually offered (suffix match, e.g. `demo__add_numbers`), because runtimes
add prefixes the test should not care about. Every request is recorded in `model.requests` for assertions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: Mapping[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class Turn:
    """One scripted model reply: text, tool calls, or both."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage | None = None

    @staticmethod
    def say(text: str) -> Turn:
        return Turn(text=text)

    @staticmethod
    def calls(*calls: ToolCall) -> Turn:
        return Turn(tool_calls=tuple(calls))

    @staticmethod
    def react(tool: str, args: Mapping[str, Any], thought: str = "I should use a tool.") -> Turn:
        """A ReAct-format reply (text the framework parses), for agents that do not use native tool calling."""
        return Turn(text=f"Thought: {thought}\nAction: {tool}\nAction Input: {json.dumps(dict(args))}")

    @staticmethod
    def react_final(answer: str) -> Turn:
        return Turn(text=f"Thought: I now know the final answer\nFinal Answer: {answer}")


@dataclass(frozen=True)
class ModelResponse:
    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage
    finish_reason: str


@dataclass(frozen=True)
class RecordedRequest:
    messages: tuple[Mapping[str, Any], ...]
    tool_names: tuple[str, ...]


class ScriptExhausted(RuntimeError):
    """The agent asked for more model turns than the script provides."""


def _tool_names(tools: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    names = []
    for t in tools:
        fn = t.get("function", t)
        if isinstance(fn, Mapping) and isinstance(fn.get("name"), str):
            names.append(fn["name"])
    return tuple(names)


def _resolve(name: str, available: Sequence[str]) -> str:
    if name in available or not available:
        return name
    hits = [a for a in available if re.search(rf"(__|\.|:|/){re.escape(name)}$", a)]
    return hits[0] if len(hits) == 1 else name


class FakeModel:
    def __init__(self, script: Sequence[Turn], *, name: str = "fake-model", repeat_last: bool = False) -> None:
        self.name = name
        self._script = list(script)
        self._repeat_last = repeat_last
        self._next = 0
        self.requests: list[RecordedRequest] = []

    @property
    def remaining(self) -> int:
        return max(0, len(self._script) - self._next)

    def respond(self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]] = ()) -> ModelResponse:
        available = _tool_names(tools)
        self.requests.append(RecordedRequest(tuple(dict(m) for m in messages), available))
        if self._next >= len(self._script):
            if not (self._repeat_last and self._script):
                raise ScriptExhausted(
                    f"{self.name}: script has {len(self._script)} turns but turn {self._next + 1} was requested"
                )
            turn = self._script[-1]
        else:
            turn = self._script[self._next]
            self._next += 1
        calls = tuple(
            ToolCall(_resolve(c.name, available), dict(c.args), c.id or f"call_{self._next}_{i}")
            for i, c in enumerate(turn.tool_calls)
        )
        prompt = max(1, len(json.dumps(list(messages), default=str)) // 4)  # deterministic rough token estimate
        usage = turn.usage or Usage(prompt, max(1, len(turn.text) // 4 + 8 * len(calls)))
        return ModelResponse(turn.text, calls, usage, "tool_calls" if calls else "stop")
