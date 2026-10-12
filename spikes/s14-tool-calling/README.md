# S14 (partial): tool calling vs ReAct, on our own MCP tools (2026-10-11)

**Question:** is the NAT/Fabric "parsing issue" a Fabric problem, a model problem, or an agent-type problem, and does native tool calling fix it?

**Setup:** NAT 1.9.0, Fabric 0.4.0, our demo MCP server (`packages/mcp-tools/demo_server.py`, tools `get_current_time`, `add_numbers`, `count_words`).
Task: "What is 17.5 plus 25, and what is the current time in Asia/Kolkata? Use the tools." Temperature 0, N=5 runs per cell, one task.
**Scoring is strict:** success needs 42.5 in the answer, the real current Asia/Kolkata time (date or clock within 15 min), AND server-side proof (the MCP server's own call log) that both tools actually ran.
Run: `make` is not wired; use `.venv/bin/python spikes/s14-tool-calling/run_matrix.py --n 5 [--model X] [--modes nat-react,nat-toolcalling,fabric-react]`.

| Model | NAT + ReAct | NAT + tool calling | Fabric + ReAct |
|---|---|---|---|
| nvidia/nemotron-3-super-120b-a12b:free (OpenRouter) | 1/1 (smoke only) | 1/1 (smoke only) | 1/1 (smoke only) |
| gpt-4.1-mini (OpenAI) | **5/5** | **5/5** | **5/5** |
| gpt-4.1-nano (OpenAI) | 3/5 | **5/5** | 3/5 |

> **Correction (2026-10-11, see `spikes/s4-relay-eval/README.md`):** a larger NAT-eval run on the same nano model did NOT reproduce the 3/5 vs 5/5 gap (ReAct 14/15, tool calling 15/15 numerically correct, with the LLM judge penalising different behaviours). Read points 2 to 4 below as hypotheses, not findings.

## What this tells us
1. **Not a Fabric problem.** With a decent model Fabric + NAT is 5/5, identical to plain NAT. Fabric and plain NAT fail at the same rate on the weak model.
2. **It is a model-strength x agent-type problem.** ReAct degrades with the weak model; native tool calling did not (5/5 on both).
3. **The nano failures were not format-parsing errors.** In all 4 failed ReAct runs the weak model dropped the MCP tool-name prefix (the tool is exposed as `demo__add_numbers`, the model called `add_numbers`). NAT rejects the unknown tool, then the model either loops until LangGraph's recursion limit of 32 (3 runs: `GRAPH_RECURSION_LIMIT`, about 23 s wasted) or stops and answers "I made a mistake in the tool name ... I will try again" (1 run, no tool ran). Tool calling avoids this because the exact names travel in the function schema.
4. **Concrete repair step for PLAN 4.4.2 step 1 (deterministic repair):** map a called name that is a unique suffix of exactly one real tool name (`add_numbers` -> `demo__add_numbers`) before rejecting it. Not built yet.
5. **The earlier free-model failures** (empty output, mixed action and final answer) did not appear in this task with the free model in a 3-run smoke; they are probably model- or quota-related, as suspected. Not re-measured at N>1.

## Update (2026-10-12): tool calling through Fabric via our own adapter patch
The upstream NAT reference adapter only accepts the `fabric.agent.react` description and hardwires NAT's `react_agent` (it is a source-only example, not a bundled Fabric adapter). Our copy (`spikes/s2-fabric-nat/src/nemo_fabric_adapters/nat/adapter.py`) now also accepts `fabric.agent.tool_calling` -> NAT `tool_calling_agent` (a 3-line change; new target `agent-builder.simple-agent-toolcalling`; harness mode `fabric-toolcalling`).

| gpt-4.1-nano, same task, N=5 | Success | Failure |
|---|---|---|
| Fabric + ReAct | 4/5 | 1 answered without using any tool ("It seems I have been using the tools correctly...") |
| Fabric + tool calling | **5/5** | none (also about 15% faster: 6.0 s vs 7.2 s per run) |

Across all S14/S4 runs on this task, tool calling made no outright failures (it did make extra, unrequested tool calls in the S4 eval); ReAct failed in 1 to 2 of 5 on nano in the matrix runs but 1 of 15 in the S4 eval. Still small N. Direction is consistent, not proven.

## Caveats (do not over-read)
- N=5 per cell, one task, one MCP server, temperature 0. 3/5 vs 5/5 is suggestive, not statistically solid. Needs larger N and more tasks.
- Only OpenAI models (the project key sees 11 models). `gpt-5*` are reasoning models and may reject a `temperature` setting [unverified]; not tested.
- Tool calling through Fabric: untested at first because the upstream reference adapter only supports `react_agent`; now done with our patched adapter copy (see Update above).
- The probe, repair ladder, gateway and Switchyard parts of S14 (PLAN 4.3, 4.4) are not done.
- Cost was a few cents (not measured; check the OpenAI usage page).

## Files
`run_matrix.py` (harness, classifies every outcome), `run_fabric_mcp.py` (Fabric run with our MCP server), `results/` (raw per-run JSONL, git-ignored), agents in `agents/mcp-agent/`.
