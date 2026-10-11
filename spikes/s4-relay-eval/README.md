# S4 (partial): logs and evaluation, 2026-10-11

**Goal:** get trustworthy per-run logs (trajectories) and scores, so agent failures can be diagnosed from evidence instead of final text.

## What works today: NAT-native ATIF + `nat eval` (no Relay needed)
`make eval KIND=react|tool_calling REPS=3 MODEL=gpt-4.1-nano` runs `spikes/s4-relay-eval/dataset.json` (5 questions that need our MCP tools) through the agent and writes to `out/<kind>/`:
- `workflow_output_atif.json`: one **ATIF v1.7** trajectory per run (user step, model steps, tool calls with observations, token metrics).
- `trajectory_output.json`: **LLM-judge trajectory score** (0 to 1) per run with the judge's reasoning (judge = `JUDGE_MODEL`, defaults to the main model).
- `avg_workflow_runtime`, `avg_num_llm_calls`, `avg_tokens_per_llm_end`: deterministic metrics.
- `summarize.py`: our own scorer over the ATIF (numeric answer check + which real tools ran + tool errors).
`nat eval` needs `nvidia-nat-eval[full]` (now in `requirements.txt`; verified from a clean install).

### Results (gpt-4.1-nano as the agent, gpt-4.1-mini as judge, 15 runs per agent type, temperature 0)
| Agent type | Numerically correct | Trajectory judge avg | Notes |
|---|---|---|---|
| ReAct | 14/15 | 0.83 | 2 "correct" runs were coincidence: it called `get_current_time` unprompted and counted the words of the timestamp (4 words) instead of the sentence; the judge scored them 0.0 and 0.25. 1 run failed after 3 tool errors and answered with filler |
| Tool calling | 15/15 | 0.85 | 6 runs made unrequested extra tool calls (called `count_words` on math questions); the judge scored these 0.5 to 0.75 |

**What the data says:** answer correctness alone hides the problem. The trajectory evaluator separates "right for the right reason" from "right by coincidence" and from "right but wasteful". Both agent types are imperfect on a weak model, in different ways.

## Correction to the S14 table
S14's matrix showed nano ReAct 3/5 vs tool calling 5/5. **This larger run did not reproduce that gap** (ReAct 14/15 here). The tool-name-prefix failure (`add_numbers` instead of `demo_tools__add_numbers`) appeared in the earlier task; here the only tool errors were in 1 of 15 runs. Treat "tool calling beats ReAct" as **unproven**: it depends on the task, N is small, and the two scorers differ. Next step is a single shared dataset and scorer for both harnesses.

## Relay through Fabric: patched and working, but only structural (2026-10-11, later)
**Hypothesis checked: "a running Relay/telemetry instance shuts Relay down" is NOT the cause.** The Relay docs pages read (overview, plugin configuration files, observability) say nothing of the kind [verified]; on this machine there is no Relay/OTel process, no listener on 4317/4318/6006/16686, no `~/.config/nemo-relay`, no `.nemo-relay`, no `nemo-relay` CLI, and Fabric's own ambient-config check returns `[]`. (Fabric does refuse to start when an ambient `plugins.toml` exists, with a clear error, so a stray config would fail loudly, not silently.)

**The real causes, all fixed:**
1. The NAT adapter descriptor declared no telemetry support (`adapter.telemetry == {}` in the plan) -> added `"telemetry": {"providers": {"relay": ...}}` to `spikes/s2-fabric-nat/nat.fabric-adapter.json`.
2. The config must SELECT the provider: `cfg.telemetry = TelemetryConfig(providers={"relay": TelemetryProviderConfig()})`; `cfg.relay=` alone only holds settings.
3. Fabric only writes the adapter's Relay config (`FABRIC_RELAY_CONFIG_PATH`) when an artifact root exists: `cfg.runtime.artifacts = <dir>`.
4. The adapter had no Relay code -> patched our copy (`adapter.py`, marked "local patch"): reads `runtime_context.telemetry`, loads Fabric's plugin config, activates the Relay plugin per invocation, opens an Agent scope, attaches `NemoRelayCallbackHandler` through a LangChain configure-hook, writes `telemetry` + `relay_artifacts` into the result, and still closes the scope (so artifacts exist) when the run fails.

**Result** (`spikes/s14-tool-calling/run_fabric_relay.py`): `RunResult` succeeded, ATOF (`events.atof.jsonl`, 32 scope events) and ATIF v1.7 written, both listed in the result's artifacts.
**Limit:** the Relay LangChain callback handler only maps chain/graph runs here. Events are all category `agent` (LangGraph nodes, `tool` nodes with the ReAct scratchpad in `data`); there are no LLM-typed or tool-typed scopes, so the ATIF has 1 step and no token metrics. NAT-native ATIF (above) is far richer today. Getting typed LLM/tool events needs Relay's LangGraph `ToolNode`/middleware integration or NAT-level hooks (not done).
**Recommendation:** use NAT-native ATIF + `nat eval` as the evaluation source of truth now; keep the patched Relay path for Fabric-level run artifacts and revisit when typed events are needed.

## Relay (earlier finding, kept for history)
- `nemo-relay` is Apache-2.0 on PyPI (0.10.0 latest; `pip install "nemo-fabric[relay]==0.4.0"` pulled 0.9.4).
- Fabric 0.4.0 has first-class Relay config (`FabricConfig.relay = RelayConfig(observability=RelayObservabilityConfig(atof=..., atif=..., opentelemetry=...))`) and `doctor` accepts it.
- **But the NAT reference adapter ignores it:** `spikes/s14-tool-calling/run_fabric_relay.py` ran successfully, `RunResult.telemetry == []`, and no ATOF/ATIF files were written. The adapter has no Relay or telemetry code; Fabric's shared adapter library (`nemo_fabric_adapters.common`: `relay_enabled`, `relay_request_context`, `relay_artifacts`, `relay_hooks`) is what an adapter must opt into.
- Relay ships LangChain/LangGraph integrations (`nemo_relay.integrations.langchain.NemoRelayCallbackHandler`), and NAT's agents run on LangGraph. Two ways forward: (a) patch our adapter copy to activate the Relay plugin per run and attach the handler; (b) skip Relay for NAT agents and rely on NAT-native ATIF. Not done.
- Relay's own ATIF is v1.7 too (written per top-level Agent scope), the same schema family as NAT's, so evaluators can read either.

## Not done
NeMo Evaluator (separate package `nemo-evaluator` 0.3.0, Python 3.12+; not tried; NAT eval covered the need); Relay via the adapter; Phoenix/OTel UI; comparing Fabric-run trajectories (the NAT eval path does not go through Fabric).
