"""Fabric run of the ReAct NAT agent whose tools come from our MCP server (packages/mcp-tools/demo_server.py)."""
import asyncio, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S2 = ROOT / "spikes" / "s2-fabric-nat"
sys.path.insert(0, str(S2 / "src"))
from nemo_fabric import (DiscoveryConfig, Fabric, FabricConfig, MetadataConfig, ModelConfig,
                         RuntimeConfig, WorkflowConfig)


def _workflow() -> dict:
    """FABRIC_AGENT_KIND=react (default) or tool_calling selects which NAT agent type the adapter builds."""
    if os.environ.get("FABRIC_AGENT_KIND", "react") == "tool_calling":
        return dict(target_id="agent-builder.simple-agent-toolcalling", settings={"llm_name": "default"})
    return dict(target_id="agent-builder.simple-agent", settings={"llm_name": "default", "parse_agent_response_max_retries": 3})


def build_config() -> FabricConfig:
    cfg = FabricConfig(
        metadata=MetadataConfig(name="s14-mcp-agent"),
        discovery=DiscoveryConfig(local_paths=[S2]),
        workflow=WorkflowConfig(**_workflow()),
        models={"default": ModelConfig(provider="openai", model=os.environ["LLM_MODEL"],
                                       base_url=os.environ["LLM_BASE_URL"], api_key_env="LLM_API_KEY",
                                       temperature=0.0)},
        runtime=RuntimeConfig(input_schema="text", output_schema="message"),
    )
    cfg.add_mcp_server("demo", transport="stdio", url=sys.executable,
                       args=[str(ROOT / "packages/mcp-tools/demo_server.py")]
                       + (["--log", os.environ["AB_TOOL_LOG_PATH"]] if os.environ.get("AB_TOOL_LOG_PATH") else []),
                       exposure="harness_native")
    return cfg


async def main():
    base = S2 / ".tmp"; base.mkdir(exist_ok=True)
    out = await Fabric().run(build_config(), base_dir=base, input=sys.argv[1])
    print(json.dumps(out.to_mapping(), default=str))

asyncio.run(main())
