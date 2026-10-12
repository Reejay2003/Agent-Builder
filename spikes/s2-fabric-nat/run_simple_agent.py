"""S2b: our own NAT agent (agents/simple-agent: current_datetime + wiki_search) run through Fabric.

Same agent as agents/simple-agent/workflow.yml, but described as a Fabric config instead of NAT YAML:
  NAT YAML `functions:`  ->  config.add_tool_definition(...)
  NAT YAML `llms:`       ->  ModelConfig
  NAT YAML `react_agent` ->  the target's entrypoint (fabric.agent.react)
Usage: PYTHONPATH=src python run_simple_agent.py [--plan|--doctor] [--input "..."]
"""
import argparse, asyncio, json, os, sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
ADAPTER = ROOT / "services" / "runner" / "nat_adapter"  # our NAT adapter (moved out of spikes/)
sys.path.insert(0, str(ADAPTER / "src"))

from nemo_fabric import (DiscoveryConfig, Fabric, FabricConfig, MetadataConfig, ModelConfig,
                         RuntimeConfig, WorkflowConfig)


def build_config() -> FabricConfig:
    config = FabricConfig(
        metadata=MetadataConfig(name="simple-agent"),
        discovery=DiscoveryConfig(local_paths=[ADAPTER]),
        workflow=WorkflowConfig(target_id="agent-builder.simple-agent",
                                settings={"llm_name": "default", "parse_agent_response_max_retries": 3}),
        models={"default": ModelConfig(
            provider="openai",
            model=os.environ.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
            base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key_env="LLM_API_KEY",
            temperature=0.0)},
        runtime=RuntimeConfig(input_schema="text", output_schema="message"),
    )
    config.add_tool_definition("current_datetime", kind="function", ref="current_datetime")
    config.add_tool_definition("wiki_search", kind="function", ref="wiki_search",
                               settings={"max_results": 2})
    # Definitions only register functions; `enabled` is what puts them in the agent's tool list.
    config.tools.enabled = ["current_datetime", "wiki_search"]
    return config


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", action="store_true")
    p.add_argument("--doctor", action="store_true")
    p.add_argument("--input", default="Who created Python, and what is the date today?")
    a = p.parse_args()
    base = ADAPTER / ".tmp"; base.mkdir(exist_ok=True)
    fabric, cfg = Fabric(), build_config()
    if a.doctor:
        out = await fabric.doctor(cfg, base_dir=base)
    elif a.plan:
        out = fabric.plan(cfg, base_dir=base)
    else:
        out = await fabric.run(cfg, base_dir=base, input=a.input)
    print(json.dumps(out.to_mapping(), indent=2, default=str))

asyncio.run(main())
