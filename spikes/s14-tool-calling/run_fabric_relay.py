"""S4: same Fabric + NAT ReAct run, with NeMo Relay turned on (ATOF event log + ATIF trajectory written to --out)."""
import asyncio, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
src = (HERE / "run_fabric_mcp.py").read_text().replace("asyncio.run(main())", "")
ns = {"__file__": str(HERE / "run_fabric_mcp.py")}; exec(compile(src, "run_fabric_mcp", "exec"), ns)
from nemo_fabric import (Fabric, TelemetryConfig, TelemetryProviderConfig, RelayAtifConfig, RelayAtofConfig, RelayAtofFileSinkConfig, RelayConfig,
                         RelayObservabilityConfig)

out = Path(os.environ.get("RELAY_OUT", "/tmp/relay-test")); out.mkdir(parents=True, exist_ok=True)
cfg = ns["build_config"]()
cfg.runtime.artifacts = out / "fabric-artifacts"  # without an artifact root Fabric never writes the Relay config for the adapter
cfg.telemetry = TelemetryConfig(providers={"relay": TelemetryProviderConfig()})  # selects Relay; without this Fabric never enables it
cfg.relay = RelayConfig(project="agent-builder", output_dir=out, observability=RelayObservabilityConfig(
    atof=RelayAtofConfig(enabled=True, sinks=[RelayAtofFileSinkConfig(output_directory=out, filename="events.atof.jsonl")]),
    atif=RelayAtifConfig(enabled=True, agent_name="s14-mcp-agent", model_name=os.environ["LLM_MODEL"], output_directory=out),
    enable_full_payloads=True))

async def main():
    res = await Fabric().run(cfg, base_dir=ns["S2"] / ".tmp", input=sys.argv[1])
    m = res.to_mapping()
    print(json.dumps({"status": m["status"], "response": (m["output"] or {}).get("response"), "error": m["error"],
                      "telemetry": m["telemetry"], "artifacts": m["artifacts"]}, default=str, indent=1))

asyncio.run(main())
