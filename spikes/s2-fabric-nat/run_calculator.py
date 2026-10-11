"""S2: NAT workflow run through NeMo Fabric, model via OpenRouter (BYOK, OpenAI-compatible).

Adapted from NeMo-Fabric v0.4.0 external/nat/examples/calculator.py (Apache-2.0).
Usage: PYTHONPATH=src python run_calculator.py [--plan|--doctor] [--input "..."]
"""
import argparse, asyncio, json, os, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "src"))  # source-only NAT adapter

from nemo_fabric import (DiscoveryConfig, Fabric, FabricConfig, InstructionConfig,
                         InstructionsConfig, MetadataConfig, ModelConfig, RuntimeConfig,
                         WorkflowConfig)


def build_config() -> FabricConfig:
    config = FabricConfig(
        metadata=MetadataConfig(name="s2-nat-calculator"),
        discovery=DiscoveryConfig(local_paths=[HERE]),
        workflow=WorkflowConfig(target_id="nvidia.examples.nat.calculator",
                                settings={"llm_name": "default"}),
        models={"default": ModelConfig(
            provider=os.environ.get("LLM_PROVIDER", "openai"),
            model=os.environ.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
            base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key_env="LLM_API_KEY",
            temperature=0.0)},
        instructions=InstructionsConfig(system=InstructionConfig(
            content="Use the calculator tools for arithmetic. Return a concise answer.",
            mode="append")),
        runtime=RuntimeConfig(input_schema="text", output_schema="message"),
    )
    config.add_mcp_server("calculator", transport="stdio", url=sys.executable,
                          args=[str(HERE / "calculator_mcp.py")],
                          exposure="harness_native", blocked_tools=["divide"])
    return config


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", action="store_true")
    p.add_argument("--doctor", action="store_true")
    p.add_argument("--input", default="What is 21 multiplied by 2?")
    a = p.parse_args()
    base = HERE / ".tmp"; base.mkdir(exist_ok=True)
    fabric, cfg = Fabric(), build_config()
    if a.doctor:
        out = await fabric.doctor(cfg, base_dir=base)
    elif a.plan:
        out = fabric.plan(cfg, base_dir=base)
    else:
        out = await fabric.run(cfg, base_dir=base, input=a.input)
    print(json.dumps(out.to_mapping(), indent=2, default=str))

asyncio.run(main())
