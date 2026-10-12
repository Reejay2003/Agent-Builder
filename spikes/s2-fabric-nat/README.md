# S2: NAT via Fabric (passed 2026-10-10)

NeMo Fabric (Apache-2.0) runs a NAT 1.9.0 workflow through the source-only NAT reference adapter
(copied from NeMo-Fabric v0.4.0 `external/nat`, Apache-2.0, see LICENSE-NVIDIA-Fabric).

**Version note:** the local S2 run used Fabric **0.5.0b3** (pre-release; `--prerelease=allow` pulled it). The adapter source is from the v0.4.0 tag and worked unchanged. Stable 0.4.0 is being verified inside the S3 sandbox image (pinned).

Setup (repo-root .venv): `uv pip install --prerelease=allow nemo-fabric nemo-fabric-adapter-contract nemo-fabric-adapters-common`
Run:
```
set -a; . .env; set +a
export PYTHONPATH="$PWD/services/runner/nat_adapter/src"   # the adapter moved here (2026-10-12)
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

## S2b: our own NAT agent (agents/simple-agent) through Fabric (2026-10-10)
`run_simple_agent.py` + `targets/simple-agent.fabric-target.json` describe the same agent (current_datetime + wiki_search, ReAct)
as a Fabric config instead of NAT YAML. Mapping: NAT `functions:` -> `config.add_tool_definition(...)` **plus**
`config.tools.enabled = [...]` (definitions alone leave the agent with zero tools); `llms:` -> `ModelConfig`; `react_agent` -> the
target entrypoint `fabric.agent.react`; extra workflow fields (e.g. `parse_agent_response_max_retries`) must be added to the target's `settings_schema`.

Result: it works. Several runs returned `succeeded` with "Python was created by Guido van Rossum. Today's date is 2026-10-10."
(the agent called both tools). Not a clean pass-rate measurement:
- Failures were `ReActAgentParsingFailedError` from free models (action and final answer in one reply, or empty output). Plain NAT
  (`agents/simple-agent/run.sh`) failed the same way on the same model, so this is model quality, not Fabric.
- One run answered with a hallucinated date (2025-08-14) without using the tool.
- OpenRouter free tier is 50 requests/day; repeated test runs exhausted it (HTTP 429, resets 2026-10-11 00:00 UTC), so later failures are quota.
- Takeaway for the plan: the adapter only supports the ReAct workflow, which is fragile with small/free models. Compare a native
  tool-calling agent, and budget real credits (OpenRouter: 10 credits unlocks 1000 free-model requests/day) before the Evals phase.
- Local patch: `FABRIC_NAT_DEBUG=1` makes our adapter copy write full tracebacks to /tmp/fabric-nat-debug.log (upstream hides them).
