"""Read ATIF v1.7 trajectories (what an agent run did, step by step) into small typed objects.

Two producers write ATIF and both are supported:
- NeMo Relay through our adapter (one file per run): one agent step per model call, with model name, token counts, tool
  calls (name + arguments) and tool results.
- `nat eval` (a list of items, each with a `trajectory`): the same format, but mixed with LangChain/LangGraph internals
  (`RunnableSequence`, `conditional_edge`, ...) that `real_tool_calls` filters out.
Nested sub-agent trajectories are flattened in document order. Tool RESULTS are only reliable in the Relay format.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Names NAT's LangGraph agents report as "tool calls" that are graph plumbing, not tools.
INTERNAL_NAMES = frozenset(
    {"agent", "tool", "LangGraph", "RunnableSequence", "conditional_edge", "ChatPromptTemplate", "PromptPassthrough"}
)


class TrajectoryError(ValueError):
    """The input is not an ATIF v1.x trajectory."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ToolCall(_Frozen):
    id: str | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    status: str | None = None


class Step(_Frozen):
    id: int
    source: str  # "user" | "agent" | "system"
    text: str = ""
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    timestamp: str | None = None


class Trajectory(_Frozen):
    schema_version: str
    agent_name: str | None = None
    model_name: str | None = None
    steps: tuple[Step, ...] = ()
    reported_prompt_tokens: int | None = None
    reported_completion_tokens: int | None = None

    @property
    def llm_steps(self) -> tuple[Step, ...]:
        """One per model call: agent steps that name a model."""
        return tuple(s for s in self.steps if s.source == "agent" and s.model)

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return tuple(c for s in self.steps for c in s.tool_calls)

    @property
    def real_tool_calls(self) -> tuple[ToolCall, ...]:
        """Tool calls without LangChain/LangGraph plumbing (only matters for `nat eval` output)."""
        return tuple(c for c in self.tool_calls if c.name not in INTERNAL_NAMES)

    @property
    def tools_used(self) -> list[str]:
        return sorted({c.name for c in self.real_tool_calls})

    @property
    def prompt_tokens(self) -> int:
        return (
            self.reported_prompt_tokens
            if self.reported_prompt_tokens is not None
            else sum(s.prompt_tokens or 0 for s in self.steps)
        )

    @property
    def completion_tokens(self) -> int:
        return (
            self.reported_completion_tokens
            if self.reported_completion_tokens is not None
            else sum(s.completion_tokens or 0 for s in self.steps)
        )

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def final_text(self) -> str | None:
        """The last non-empty message an agent step produced."""
        return next((s.text for s in reversed(self.steps) if s.source == "agent" and s.text.strip()), None)


def _results_by_call(observation: Mapping[str, Any] | None) -> dict[str, tuple[Any, str | None]]:
    out: dict[str, tuple[Any, str | None]] = {}
    for r in (observation or {}).get("results") or []:
        extra = r.get("extra") or {}
        tool_result = extra.get("tool_result")
        if isinstance(tool_result, Mapping):
            out[str(r.get("source_call_id"))] = (tool_result.get("content"), tool_result.get("status"))
        elif "content" in r:
            out[str(r.get("source_call_id"))] = (r["content"], None)
    return out


def _step(raw: Mapping[str, Any]) -> Step:
    results = _results_by_call(raw.get("observation"))
    calls = []
    for c in raw.get("tool_calls") or []:
        call_id = c.get("tool_call_id")
        result, status = results.get(str(call_id), (None, None))
        calls.append(
            ToolCall(
                id=call_id,
                name=str(c.get("function_name", "")),
                arguments=dict(c.get("arguments") or {}),
                result=result,
                status=status,
            )
        )
    metrics = raw.get("metrics") or {}
    return Step(
        id=int(raw.get("step_id", 0)),
        source=str(raw.get("source", "")),
        text=str(raw.get("message") or ""),
        model=raw.get("model_name"),
        prompt_tokens=metrics.get("prompt_tokens"),
        completion_tokens=metrics.get("completion_tokens"),
        tool_calls=tuple(calls),
        timestamp=raw.get("timestamp"),
    )


def _flatten(raw: Mapping[str, Any]) -> list[Step]:
    steps = [_step(s) for s in raw.get("steps") or []]
    for sub in raw.get("subagent_trajectories") or []:
        steps.extend(_flatten(sub))
    return steps


def from_dict(raw: Mapping[str, Any]) -> Trajectory:
    version = raw.get("schema_version")
    if not isinstance(version, str) or not version.startswith("ATIF-v1."):
        raise TrajectoryError(f"not an ATIF v1.x trajectory (schema_version={version!r})")
    if not isinstance(raw.get("steps"), list):
        raise TrajectoryError("trajectory has no 'steps' list")
    agent = raw.get("agent") or {}
    final = raw.get("final_metrics") or {}
    return Trajectory(
        schema_version=version,
        agent_name=agent.get("name"),
        model_name=agent.get("model_name"),
        steps=tuple(_flatten(raw)),
        reported_prompt_tokens=final.get("total_prompt_tokens"),
        reported_completion_tokens=final.get("total_completion_tokens"),
    )


def load(path: str | Path) -> Trajectory:
    """Load one trajectory file (a Relay `nemo-relay-atif-*.json`)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrajectoryError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TrajectoryError(f"{path} is not a single trajectory (a list is a `nat eval` file: use load_eval)")
    return from_dict(data)


def load_eval(path: str | Path) -> dict[str, Trajectory]:
    """Load a `nat eval` `workflow_output_atif.json` (a list of items) as {item_id: Trajectory}."""
    try:
        items = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrajectoryError(f"cannot read {path}: {exc}") from exc
    if not isinstance(items, list):
        raise TrajectoryError(f"{path} is not a `nat eval` item list")
    return {
        str(i.get("item_id")): from_dict(i["trajectory"]) for i in items if isinstance(i, Mapping) and "trajectory" in i
    }
