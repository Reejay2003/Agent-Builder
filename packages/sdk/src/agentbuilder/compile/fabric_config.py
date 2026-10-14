"""Compiler B: CompiledAgent -> a NeMo Fabric `FabricConfig`-shaped mapping (JSON-compatible).

The core SDK does not import Fabric (an NVIDIA 0.x package); the runner package validates the mapping with
`nemo_fabric.FabricConfig.model_validate(mapping)`. Targets name the workflow our adapter builds
(services/runner/nat_adapter/targets): ReAct and tool calling."""

from __future__ import annotations

from typing import Any

from agentbuilder.compile.compiled import CompiledAgent

SCHEMA_VERSION = "fabric.agent/v1alpha1"
TARGET_ID = {
    "tool_calling": "agent-builder.simple-agent-toolcalling",
    "react": "agent-builder.simple-agent",
}
_PROVIDER = {"nvidia_hosted": "nvidia"}  # everything else speaks the OpenAI wire format


def to_fabric_config(
    c: CompiledAgent,
    *,
    adapter_dir: str | None = None,
    artifacts_dir: str | None = None,
    relay_output_dir: str | None = None,
) -> dict[str, Any]:
    """`adapter_dir`: where Fabric finds our adapter descriptor and targets. `relay_output_dir`: turn on Relay telemetry
    (ATOF + ATIF); Fabric then also needs an artifact root, defaulted to `<relay_output_dir>/fabric-artifacts`."""
    model: dict[str, Any] = {"provider": _PROVIDER.get(c.model.provider, "openai"), "model": c.model.model}
    if c.model.api_key_env:
        model["api_key_env"] = c.model.api_key_env
    model["base_url"] = c.model.base_url
    if c.model.temperature is not None:
        model["temperature"] = c.model.temperature
    if c.model.max_tokens is not None:
        model["max_tokens"] = c.model.max_tokens

    settings: dict[str, Any] = {"llm_name": "default"}
    if c.model.agent_mode == "react":
        settings["parse_agent_response_max_retries"] = c.parse_retries

    runtime: dict[str, Any] = {"input_schema": "text", "output_schema": "message"}
    if relay_output_dir and not artifacts_dir:
        artifacts_dir = f"{relay_output_dir.rstrip('/')}/fabric-artifacts"
    if artifacts_dir:
        runtime["artifacts"] = artifacts_dir

    cfg: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "metadata": {"name": c.name}}
    if c.description:
        cfg["metadata"]["description"] = c.description
    cfg["workflow"] = {"target_id": TARGET_ID[c.model.agent_mode], "settings": settings}
    if adapter_dir:
        cfg["discovery"] = {"local_paths": [adapter_dir]}
    cfg["runtime"] = runtime
    cfg["models"] = {"default": model}
    if c.instructions:
        cfg["instructions"] = {"system": {"content": c.instructions, "mode": "append"}}
    if c.servers:
        cfg["mcp"] = {
            "servers": {
                s.name: {
                    "transport": "stdio",
                    "url": s.command,
                    "args": list(s.args),
                    "exposure": "harness_native",
                    "allowed_tools": [t.mcp_name for t in c.tools_for(s.name)],
                }
                for s in c.servers
            }
        }
    if relay_output_dir:
        cfg["telemetry"] = {"providers": {"relay": {}}}
        cfg["relay"] = {
            "project": c.name,
            "output_dir": relay_output_dir,
            "observability": {
                "version": 3,
                "atof": {
                    "enabled": True,
                    "sinks": [{"type": "file", "output_directory": relay_output_dir, "filename": "events.atof.jsonl"}],
                },
                "atif": {
                    "enabled": True,
                    "agent_name": c.name,
                    "model_name": c.model.model,
                    "output_directory": relay_output_dir,
                },
                "enable_full_payloads": True,
            },
        }
    return cfg
