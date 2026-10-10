# S2: NAT via Fabric (passed 2026-10-10)

NeMo Fabric (Apache-2.0) runs a NAT 1.9.0 workflow through the source-only NAT reference adapter
(copied from NeMo-Fabric v0.4.0 `external/nat`, Apache-2.0, see LICENSE-NVIDIA-Fabric).

**Version note:** the local S2 run used Fabric **0.5.0b3** (pre-release; `--prerelease=allow` pulled it). The adapter source is from the v0.4.0 tag and worked unchanged. Stable 0.4.0 is being verified inside the S3 sandbox image (pinned).

Setup (repo-root .venv): `uv pip install --prerelease=allow nemo-fabric nemo-fabric-adapter-contract nemo-fabric-adapters-common`
Run:
```
set -a; . .env; set +a
export PYTHONPATH="$PWD/spikes/s2-fabric-nat/src"
python spikes/s2-fabric-nat/run_calculator.py [--plan | --doctor]
```
Result: `RunResult.status = succeeded`, response "42.0" (calculator MCP tool, model via OpenRouter free tier).

Findings:
- Fabric config is Python-only (`FabricConfig`); there is no YAML. Our AgentSpec compiler (B) must emit these objects.
- BYOK works: `ModelConfig(provider="openai", base_url=OpenRouter, api_key_env=...)`.
- The adapter was tested by NVIDIA on NAT 1.7/1.8; it worked unchanged on 1.9.0.
- The adapter runs in a subprocess host, so it needs `PYTHONPATH` (dev bootstrap limitation per its README).
- `telemetry` is empty until Relay is wired (S4).
- `doctor` passes; warns that no resolution strategy or environment is set (S3 adds the environment).
- The `nemo-fabric` CLI binary was not installed by pip (Rust workspace); the Python SDK is enough.
