"""Tool manifests (PLAN section 6): what a tool can read or change, in plain language, plus the facts the sandbox and
approval policy are generated from (risk tier, network hosts, file paths). One manifest per tool."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SideEffect = Literal["none", "read", "write", "external_comms", "destructive", "financial"]
RiskTier = Literal[0, 1, 2, 3]

# Lowest risk tier each declared side effect may have: 0 read-only, 1 reversible write,
# 2 external communication (human approval by default), 3 destructive or financial (blocked by default).
MIN_TIER: dict[str, int] = {"none": 0, "read": 0, "write": 1, "external_comms": 2, "destructive": 3, "financial": 3}

_TOOL_ID = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
_HOST = re.compile(r"^(\*\.)?([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RateLimits(_Strict):
    per_minute: int | None = Field(None, gt=0)


class ToolManifest(_Strict):
    id: str
    mcp_name: str
    description_plain: str = Field(min_length=1)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=list)
    side_effects: SideEffect = "none"
    risk_tier: RiskTier = 0
    creds_required: list[str] = Field(default_factory=list)
    egress_hosts: list[str] = Field(default_factory=list)
    fs_paths: list[str] = Field(default_factory=list)
    rate_limits: RateLimits = Field(default_factory=RateLimits)
    mock_response: Any = None

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not _TOOL_ID.match(v):
            raise ValueError("tool id must be dotted lowercase words, e.g. 'gmail.read'")
        return v

    @field_validator("egress_hosts")
    @classmethod
    def _valid_hosts(cls, v: list[str]) -> list[str]:
        for h in v:
            if not _HOST.match(h):
                raise ValueError(
                    f"egress host '{h}' must be a bare host name such as 'api.example.com' or '*.example.com'"
                )
        return v

    @field_validator("fs_paths")
    @classmethod
    def _absolute_paths(cls, v: list[str]) -> list[str]:
        for p in v:
            if not p.startswith("/") or ".." in p.split("/"):
                raise ValueError(f"fs path '{p}' must be absolute and contain no '..'")
        return v

    @model_validator(mode="after")
    def _risk_matches_side_effects(self) -> ToolManifest:
        floor = MIN_TIER[self.side_effects]
        if self.risk_tier < floor:
            raise ValueError(
                f"risk_tier {self.risk_tier} is too low for side_effects '{self.side_effects}' (minimum {floor})"
            )
        return self


def manifests_document(server: str, source: str, manifests: list[ToolManifest]) -> dict[str, Any]:
    """The committed JSON shape (packages/tool-manifests/*.manifest.json)."""
    return {
        "server": server,
        "source": source,
        "transport": "stdio",
        "tools": [m.model_dump(mode="json") for m in manifests],
    }
