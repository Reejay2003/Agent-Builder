"""AgentSpec: the one stable contract (PLAN section 5). Pure data, no behaviour, no network.

Design rules enforced here:
- unknown fields are errors (typos fail loudly);
- credentials are references (`secret://...`, `env://NAME`), never keys, and no key-like value may appear anywhere;
- sections that belong to later phases (knowledge, integrations, channels, voice) are accepted but opaque until
  the phase that implements them defines their shape.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SPEC_VERSION = 1

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_TOOL_ID = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_AGENT_ID = re.compile(r"^agt_[A-Za-z0-9]{4,64}$")
_SECRET_REF = re.compile(r"^(secret|env)://[A-Za-z0-9_./-]+$")
# Obvious API-key shapes: OpenAI/OpenRouter sk-..., AWS, GitHub, Slack, Google. A guard, not a guarantee.
_KEY_LIKE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})"
)

Provider = Literal["openai", "openrouter", "ollama", "nvidia_hosted", "openai_compatible"]
AgentMode = Literal["auto", "tool_calling", "react"]
Tier = Literal["strong", "standard", "limited", "unsuitable"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RepairSpec(_Strict):
    max_attempts: int = Field(3, ge=0, le=10)
    steps: list[Literal["tool_names", "retry", "reprompt"]] = Field(default_factory=list)
    escalate_to: str | None = None


class ReliabilitySpec(_Strict):
    tier: Tier | None = None
    mode: Literal["normal", "limited"] = "normal"
    repair: RepairSpec = Field(default_factory=RepairSpec)


class RoutingSpec(_Strict):
    provider: str
    algorithm: str
    models: list[str] = Field(default_factory=list)


class ModelSpec(_Strict):
    provider: Provider
    model: str = Field(min_length=1)
    base_url: str | None = None
    credential_ref: str | None = None
    temperature: float | None = Field(None, ge=0, le=2)
    max_tokens: int | None = Field(None, gt=0)
    agent_mode: AgentMode = "auto"
    capability_tier: Tier | None = None
    reliability: ReliabilitySpec = Field(default_factory=ReliabilitySpec)
    routing: RoutingSpec | None = None

    @field_validator("base_url")
    @classmethod
    def _http_url(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^https?://[^\s]+$", v):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @field_validator("credential_ref")
    @classmethod
    def _by_reference(cls, v: str | None) -> str | None:
        if v is not None and not _SECRET_REF.match(v):
            raise ValueError(
                "credentials are by reference only: use secret://<name> or env://<VAR_NAME>, never the key itself"
            )
        return v

    @model_validator(mode="after")
    def _needs_base_url(self) -> ModelSpec:
        if self.provider == "openai_compatible" and not self.base_url:
            raise ValueError("provider 'openai_compatible' requires base_url")
        if self.credential_ref and self.base_url and _sends_key_in_clear(self.base_url):
            raise ValueError(
                "base_url uses plain http:// to a public host, which would send the API key unencrypted: "
                "use https://, or http:// only for this machine or your local network"
            )
        return self


def _sends_key_in_clear(url: str) -> bool:
    """http:// to anything but this machine, a private network address or a *.local / *.internal name."""
    parts = urlsplit(url)
    if parts.scheme != "http":
        return False
    host = (parts.hostname or "").lower()
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True  # a public name
    return not (address.is_private or address.is_loopback or address.is_link_local)


class InstructionsSpec(_Strict):
    persona: str = ""
    rules: list[str] = Field(default_factory=list)


class ToolRef(_Strict):
    id: str
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, data: Any) -> Any:
        return {"id": data} if isinstance(data, str) else data  # `tools: [demo.add_numbers]`

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not _TOOL_ID.match(v):
            raise ValueError("tool id must be dotted lowercase words, e.g. 'gmail.read' or 'demo.add_numbers'")
        return v


class GuardrailsSpec(_Strict):
    profile: Literal["strict", "standard", "relaxed"] = "standard"


class ApprovalsSpec(_Strict):
    tier2_external_comms: Literal["require_human", "allow"] = "require_human"
    tier3_destructive: Literal["block", "require_human"] = "block"


class SandboxSpec(_Strict):
    policy_preset: str | None = None


class EvalsSpec(_Strict):
    suite: str | None = None
    publish_threshold: float = Field(0.85, ge=0, le=1)


def _find_secret(value: Any, path: str = "") -> str | None:
    """Return the path of the first key-like string inside `value`, or None."""
    if isinstance(value, str):
        return path or "<root>" if _KEY_LIKE.search(value) else None
    if isinstance(value, dict):
        for k, v in value.items():
            if (hit := _find_secret(v, f"{path}.{k}" if path else str(k))) is not None:
                return hit
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            if (hit := _find_secret(v, f"{path}[{i}]")) is not None:
                return hit
    return None


class AgentSpec(_Strict):
    spec_version: Literal[1] = 1
    id: str | None = None
    name: str
    type: str | None = None
    description: str = ""
    model: ModelSpec
    instructions: InstructionsSpec = Field(default_factory=InstructionsSpec)
    tools: list[ToolRef] = Field(default_factory=list)
    guardrails: GuardrailsSpec = Field(default_factory=GuardrailsSpec)
    approvals: ApprovalsSpec = Field(default_factory=ApprovalsSpec)
    sandbox: SandboxSpec = Field(default_factory=SandboxSpec)
    evals: EvalsSpec = Field(default_factory=EvalsSpec)
    # Reserved: accepted but opaque until the phase that implements them
    # (knowledge: Phase 4, integrations and channels: Phase 3, voice: Phase 7).
    knowledge: dict[str, Any] | None = None
    integrations: list[dict[str, Any]] = Field(default_factory=list)
    channels: list[dict[str, Any]] = Field(default_factory=list)
    voice: dict[str, Any] | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    # --- convenience API (implemented in agentbuilder.spec.io) ---
    @classmethod
    def load(cls, path: str | Path) -> AgentSpec:
        from agentbuilder.spec import io

        return io.load(path)

    @classmethod
    def loads(cls, text: str, fmt: Literal["yaml", "json"] = "yaml") -> AgentSpec:
        from agentbuilder.spec import io

        return io.loads(text, fmt)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AgentSpec:
        from agentbuilder.spec import io

        return io.load_dict(data)

    def to_dict(self) -> dict[str, Any]:
        from agentbuilder.spec import io

        return io.to_dict(self)

    def to_yaml(self) -> str:
        from agentbuilder.spec import io

        return io.dumps(self, "yaml")

    def to_json(self) -> str:
        from agentbuilder.spec import io

        return io.dumps(self, "json")

    def save(self, path: str | Path) -> None:
        from agentbuilder.spec import io

        io.save(self, path)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not _NAME.match(v):
            raise ValueError(
                "name must be lowercase letters, digits, '-' or '_' (1 to 63 characters), "
                "starting with a letter or digit"
            )
        return v

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str | None) -> str | None:
        if v is not None and not _AGENT_ID.match(v):
            raise ValueError("id must look like 'agt_' followed by letters and digits")
        return v

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str | None) -> str | None:
        if v is not None and not _TYPE.match(v):
            raise ValueError("type must be a lowercase identifier such as 'personal_automation'")
        return v

    @model_validator(mode="after")
    def _checks(self) -> AgentSpec:
        ids = [t.id for t in self.tools]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate tool ids: {', '.join(dupes)}")
        hit = _find_secret(self.model_dump(mode="python"))
        if hit is not None:
            raise ValueError(
                f"a value that looks like an API key was found at '{hit}'; "
                "specs hold references (secret://, env://), never keys"
            )
        return self
