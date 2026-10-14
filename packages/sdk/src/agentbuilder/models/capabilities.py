"""What we KNOW about models, with evidence. Never guessed: unknown models stay unknown.

The table (`capabilities.yaml`) is seeded from our own measurements (spikes S14/S4). A model's tier comes from the
success rate of its recommended agent mode on our task suite: strong >= 99%, standard >= 95%, limited >= 85%, else
unsuitable.
`agent_mode: auto` resolves through this table (PLAN 4.3): tool calling unless the model is known not to support it.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agentbuilder.spec.models import ModelSpec, Tier

Mode = Literal["tool_calling", "react"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModeResult(_Strict):
    passed: int = Field(ge=0)
    runs: int = Field(gt=0)

    @property
    def rate(self) -> float:
        return self.passed / self.runs


class Capability(_Strict):
    provider: str
    model: str
    tool_calling: bool | None = None  # None = unknown
    recommended_agent_mode: Mode | None = None
    tier: Tier | None = None
    tier_source: Literal["measured", "manual"] | None = None
    modes: dict[Mode, ModeResult] = Field(default_factory=dict)
    evidence: str = ""
    notes: str = ""


def tier_for_rate(rate: float) -> Tier:
    if rate >= 0.99:
        return "strong"
    if rate >= 0.95:
        return "standard"
    if rate >= 0.85:
        return "limited"
    return "unsuitable"


@lru_cache(maxsize=1)
def table() -> tuple[Capability, ...]:
    text = resources.files("agentbuilder.models").joinpath("capabilities.yaml").read_text(encoding="utf-8")
    return tuple(Capability.model_validate(row) for row in yaml.safe_load(text)["models"])


def lookup(provider: str, model: str) -> Capability | None:
    """Exact match first, then the longest known id that prefixes `model` (so dated snapshots match their family)."""
    candidates = [c for c in table() if c.provider == provider]
    for c in candidates:
        if c.model == model:
            return c
    prefixed = [c for c in candidates if model.startswith(c.model)]
    return max(prefixed, key=lambda c: len(c.model)) if prefixed else None


def resolve_agent_mode(spec: ModelSpec) -> Mode:
    """An explicit mode always wins. `auto`: tool calling, unless the table says the model cannot do it."""
    if spec.agent_mode in ("tool_calling", "react"):
        return spec.agent_mode
    cap = lookup(spec.provider, spec.model)
    if cap is not None:
        if cap.tool_calling is False:
            return "react"
        if cap.recommended_agent_mode is not None:
            return cap.recommended_agent_mode
    return "tool_calling"
