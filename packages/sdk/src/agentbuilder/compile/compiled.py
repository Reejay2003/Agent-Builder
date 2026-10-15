"""CompiledAgent: an AgentSpec with everything resolved (model endpoint, agent mode, tools, servers, instructions).

It is the single input to every emitter (NAT workflow, Fabric config, later sandbox policy and OPA bundle), so they
cannot disagree. It never contains a secret value: only the NAME of the environment variable a runtime should read
the key from.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentbuilder.tools.catalog import McpServerBinding
from agentbuilder.tools.manifest import RiskTier, SideEffect


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompiledModel(_Strict):
    provider: str
    model: str
    base_url: str
    api_key_env: str | None = None
    temperature: float | None = None
    agent_mode: Literal["tool_calling", "react"]


class CompiledTool(_Strict):
    id: str
    server: str
    mcp_name: str
    risk_tier: RiskTier
    side_effects: SideEffect
    egress_hosts: list[str] = Field(default_factory=list)
    fs_paths: list[str] = Field(default_factory=list)


class CompiledAgent(_Strict):
    name: str
    description: str = ""
    spec_version: int
    model: CompiledModel
    instructions: str = ""
    tools: list[CompiledTool] = Field(default_factory=list)
    servers: list[McpServerBinding] = Field(default_factory=list)
    guardrails_profile: str = "standard"
    tier2_policy: str = "require_human"
    tier3_policy: str = "block"
    sandbox_preset: str | None = None
    parse_retries: int = 3
    warnings: list[str] = Field(default_factory=list)

    def tools_for(self, server: str) -> list[CompiledTool]:
        return [t for t in self.tools if t.server == server]
