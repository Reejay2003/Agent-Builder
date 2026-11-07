"""Eval suites are data (YAML or JSON), never code: a suite file can be shared without running anything."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Expect(_Strict):
    """What a correct answer looks like. Every listed check must hold."""

    contains: list[str] = Field(default_factory=list)  # each, case-insensitive
    numbers: list[float] = Field(default_factory=list)  # each appears in the answer (within 0.011)
    abstain: bool = False  # the right answer is "I can't / I don't know / that doesn't exist"
    not_contains: list[str] = Field(default_factory=list)


class Case(_Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,40}$")
    prompt: str = Field(min_length=1)
    expect: Expect = Field(default_factory=Expect)
    required_tools: list[str] = Field(default_factory=list)  # tool ids or names, matched by suffix
    forbid_tools: bool = False  # the question needs no tool; calling one is a failure
    never_tools: list[str] = Field(default_factory=list)  # tools that must NOT be called (for example after injection)
    category: str = "general"

    @model_validator(mode="after")
    def _consistent(self) -> Case:
        if self.forbid_tools and self.required_tools:
            raise ValueError(f"case {self.id}: forbid_tools and required_tools contradict each other")
        return self


class Thresholds(_Strict):
    """Starting points from PLAN 4.4.3 (tuned in S14): success >= 0.85 and no-tool answers < 0.05 to publish."""

    success: float = Field(0.85, ge=0, le=1)
    limited_success: float = Field(0.70, ge=0, le=1)  # at or above: publish with limited mode
    max_no_tool_answer: float = Field(0.05, ge=0, le=1)


class Suite(_Strict):
    name: str
    description: str = ""
    cases: list[Case] = Field(min_length=1)
    thresholds: Thresholds = Field(default_factory=Thresholds)

    @model_validator(mode="after")
    def _unique(self) -> Suite:
        ids = [c.id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique")
        return self


def load_suite(name_or_path: str) -> Suite:
    """A built-in suite by name (`calculator_v1`, `personal_automation_v1`) or a YAML/JSON file path."""
    path = Path(name_or_path)
    if path.suffix in (".yaml", ".yml", ".json") and path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        builtin = resources.files("agentbuilder.evals") / "suites" / f"{name_or_path}.yaml"
        if not builtin.is_file():
            raise FileNotFoundError(f"no eval suite '{name_or_path}': give a built-in name or a .yaml/.json path")
        text = builtin.read_text(encoding="utf-8")
    return Suite.model_validate(yaml.safe_load(text))
