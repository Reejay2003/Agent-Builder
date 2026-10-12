"""Load and save AgentSpecs (YAML or JSON). `yaml.safe_load` only: spec files are data, never code."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from agentbuilder.spec.errors import SpecError
from agentbuilder.spec.migrate import upgrade
from agentbuilder.spec.models import AgentSpec

Format = Literal["yaml", "json"]


def _format_errors(exc: ValidationError) -> list[str]:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        msg = str(err["msg"]).removeprefix("Value error, ")
        lines.append(f"{loc}: {msg}")
    return lines


def load_dict(data: Mapping[str, Any]) -> AgentSpec:
    try:
        return AgentSpec.model_validate(upgrade(data))
    except ValidationError as exc:
        problems = _format_errors(exc)
        raise SpecError("invalid AgentSpec:\n  " + "\n  ".join(problems), problems) from exc


def loads(text: str, fmt: Format = "yaml") -> AgentSpec:
    try:
        data = json.loads(text) if fmt == "json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SpecError(f"cannot parse {fmt}: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError("an AgentSpec file must contain a mapping at the top level")
    return load_dict(data)


def load(path: str | Path) -> AgentSpec:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in {".yaml", ".yml", ".json"}:
        raise SpecError(f"unsupported spec file type '{p.suffix}' (use .yaml, .yml or .json)")
    return loads(p.read_text(encoding="utf-8"), "json" if suffix == ".json" else "yaml")


def to_dict(spec: AgentSpec) -> dict[str, Any]:
    """Explicit, JSON-compatible dict: defaults are kept (readable specs), None values are dropped."""
    return spec.model_dump(mode="json", exclude_none=True)


def dumps(spec: AgentSpec, fmt: Format = "yaml") -> str:
    data = to_dict(spec)
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def save(spec: AgentSpec, path: str | Path) -> None:
    p = Path(path)
    p.write_text(dumps(spec, "json" if p.suffix.lower() == ".json" else "yaml"), encoding="utf-8")
