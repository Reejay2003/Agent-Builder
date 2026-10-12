# COMPLETED: progress tracker and what not to redo

**Read this before starting any work.** It says what is done, what was decided, what broke before, and what is next. The long-term design is in [PLAN.md](PLAN.md); this file is the short, current truth.

## How to use this file (keeps us out of loops)
1. Before starting: find your task in **Next up**, put your GitHub handle in `Owner`, and set `Status` to `in progress` (do this in a small PR or an issue comment first).
2. While working: if you hit something that cost you more than 15 minutes, add it to **Gotchas**.
3. When done: in the **same PR** as the work, record it under **Done** (and, once a phase is finished, in that phase's **Phase N completed** section at the end of this file) with the date, the evidence (a file, a command, or a result), and one line on what was learned. A spike that passed but is not recorded here did not happen.
4. If you change a decision, add a new row to **Decisions** (do not edit the old one). Say why.
5. Never write secrets here or anywhere in the repo.

Status values: `not started` / `in progress` / `blocked` / `done` / `partial`. Tags: **[verified]** = run or read in the primary source; **[unverified]** = believed, not checked.

---

## Done

### Environment and repo
| What | Date | Evidence | Notes |
|---|---|---|---|
| Repo, Docker Compose stack (Postgres 17 + pgvector 0.8.0, Valkey 8) | 2026-10-10 | `deploy/compose/docker-compose.yml`, `make up`, `make check` | Ports bound to 127.0.0.1; data in named volumes |
| Reproducible setup: pinned `requirements.txt` + `requirements.lock`, `Makefile`, `scripts/check_env.sh`, dev container | 2026-10-10 | Tested from a clean copy of the repo: `make setup`, `make check`, `make fabric-doctor`, dev container import test | See Gotchas: Python 3.14 breaks the install |
| Planning: PLAN.md v1 to v8 | 2026-10-10 | [PLAN.md](PLAN.md) section 0 lists each version's changes | v8 added the LLM layer (4.3), weak-model handling (4.4), spike S14 |
| Claude Code helpers: Playwright MCP (`.mcp.json`), Ponytail skills (`.claude/skills/`) | 2026-10-10 | Playwright showed Connected in `/mcp` | Optional; only matters if you use Claude Code |

### Phase 0 spikes (details in each folder's README)
| ID | Question | Status | Date | Evidence | Key finding |
|---|---|---|---|---|---|
| S1 | Does NAT run with our own key and one tool, no NVIDIA key? | **done** | 2026-10-10 | `spikes/s1-nat-hello/` | Yes. NAT 1.9.0. Needs `nvidia-nat[langchain]`, not plain `nvidia-nat`. BYOK works via `_type: openai` + `base_url` |
| (agent) | A simple NAT agent on the full SDK | **done** | 2026-10-10 | `agents/simple-agent/`, `make agent` | ReAct agent, tools `current_datetime` + `wiki_search`. Calculator is NOT a built-in tool |
| S2 | Does Fabric run a NAT agent (`plan`, `doctor`, `run`)? | **done** | 2026-10-10 | `spikes/s2-fabric-nat/`, `run_calculator.py` | Yes. Fabric config is Python only (no YAML). NVIDIA's NAT adapter (tested on NAT 1.7/1.8) worked on 1.9.0 |
| S2b | Does OUR agent run through Fabric? | **partial** | 2026-10-10 | `spikes/s2-fabric-nat/run_simple_agent.py` | Works (several correct runs) but about half the runs failed on free models: ReAct parse errors. Plain NAT fails the same way, so it is the model, not Fabric. A clean pass-rate was not measured (free quota ran out). `--plan`/`--doctor` verified on stable Fabric 0.4.0; the LLM runs used 0.5.0b3 |
| S4 (partial) | Logs and scoring | **partial** | 2026-10-11 | `spikes/s4-relay-eval/README.md`, `make eval` | NAT-native ATIF v1.7 + `nat eval` (trajectory judge) work. Relay through Fabric now works after patching our adapter copy (4 causes found, see README; NOT a running-instance conflict): ATOF + ATIF written, but only graph-level events (no LLM/tool-typed steps or tokens). Larger run (nano, 15 runs/type): ReAct 14/15, tool calling 15/15 numerically; judge scores 0.83 / 0.85; reveals coincidental and wasteful runs. **Did not reproduce S14's 3/5 vs 5/5 gap** |
| S14 repair + S4 typed Relay | Tool-name repair; typed LLM/tool events in Relay ATIF | **done** | 2026-10-12 | `nat/repair.py`, `nat/relay_events.py`, `make test`, S4/S14 READMEs | Relay ATIF now has per-LLM-call steps (model, thought, tokens) and tool calls with args and results for both ReAct and tool calling. Tool-name repair: built and tested but triggered 0 times in a 60-run A/B (49/60 either way), benefit unproven, off by default |
| S14 big suite | 480-run comparison, 3 models x 4 setups x 20 tasks | **done** | 2026-10-12 | `spikes/s14-tool-calling/README.md`, `run_suite.py`, `tasks.py` | gpt-4.1-mini 100% everywhere; gpt-4o-mini 95-100%; gpt-4.1-nano tool calling 97.5% vs ReAct 85-92.5%. Fabric = plain NAT. Tool calling never worse; gap only on the weakest model; N=40/cell |
| S14 (partial) | Tool calling vs ReAct on our own MCP tools | **partial** | 2026-10-11 | `spikes/s14-tool-calling/README.md`, `packages/mcp-tools/`, `agents/mcp-agent/` | gpt-4.1-mini 15/15 in all modes (so Fabric is fine). On gpt-4.1-nano: tool calling 5/5, ReAct 3/5 (NAT) and 3/5 (Fabric). Failures = model drops the MCP tool-name prefix, loops or gives up, not format parsing. Not done: Fabric tool-calling target, probe, repair, gateway, Switchyard |
| S3 | Can the agent run in an OpenShell sandbox with controlled egress? | **done** | 2026-10-10 | `spikes/s3-openshell/` (both parts) | Yes. Allowed host works, other hosts blocked, key hidden inside (placeholder). About 0.6 s start, about 24 MiB per idle sandbox. Calculator agent ran inside on Fabric 0.4.0 + NAT 1.9.0 |

## Phase 1 kickoff (cleanup done 2026-10-12; claim before starting)
Phase 0 has enough evidence to start Phase 1 ([PLAN section 13](PLAN.md)). Suggested order, each small and independent:
| # | Task | Output | Owner | Status |
|---|---|---|---|---|
| P1.1 | **AgentSpec** JSON Schema + typed models | `packages/agent-spec/` (spec_version 1, validated examples: personal_automation, support) | (unclaimed) | not started |
| P1.2 | **Compiler A/B**: AgentSpec -> NAT workflow + `FabricConfig` (agent mode from `model.agent_mode`, tools from manifests, Relay on) | `services/runner/compiler/`, golden-file tests, `make test` | (unclaimed) | not started |
| P1.3 | **Runner service**: run a compiled spec through Fabric, return result + ATIF | `services/runner/` FastAPI endpoint `POST /runs` | (unclaimed) | not started |
| P1.4 | **Tool store v0**: manifests for demo + Gmail/Calendar tools, MCP gateway stub | `packages/tool-manifests/`, `services/mcp-gateway/` | (unclaimed) | not started |
| P1.5 | **Model check (probe)** + capability table | `packages/model-capabilities/`, `services/control` endpoint ([PLAN 4.4.1](PLAN.md)) | (unclaimed) | not started |
| P1.6 | **Control service** skeleton: FastAPI + Postgres (AgentSpec versions, runs) | `services/control/` | (unclaimed) | not started |
| P1.7 | **Wizard** shell (Next.js): BYOK, template, tool basket, test run with trace view | `apps/web/` | (unclaimed) | not started |
Cleanup already done: adapter moved to `services/runner/nat_adapter/` (own README, tests, licence file); `make test`; eval deps pinned; harnesses updated; all runs re-verified after the move.

## Next up (suggested order; claim before starting)
| ID | Task | Needs | Owner | Status |
|---|---|---|---|---|
| S14 (rest) | Remaining: larger N and more tasks; Fabric tool-calling target (custom adapter?); wizard probe + repair step 1 (tool-name suffix mapping) and 3; LiteLLM gateway; Switchyard trial ([PLAN 4.3, 4.4, S14](PLAN.md)) | An LLM key (OpenAI key works; free tier is 50 requests/day) | (unclaimed) | partial |
| S4 (rest) | Try NeMo Evaluator; read Relay ATIF in the eval harness; OTel export; formally decide telemetry source of truth (Relay ATIF is now rich enough to be a candidate) | S2 | (unclaimed) | partial |
| S7 | Licence table in `docs/` | reading only | (unclaimed) | partial: NAT, Fabric, OpenShell, NeMo Retriever, Switchyard are Apache-2.0 [verified]; Relay, NIM/Riva terms, embedding model licences not read |
| S6 | Whole stack on a laptop with Ollama, no cloud spend | Ollama | (unclaimed) | not started |
| S9 | RAG baseline: pgvector_lite vs NeMo Retriever on about 50 real documents | documents, optional GPU | (unclaimed) | not started |
| S10 | NAT retrievers and RAG evals | S9 | (unclaimed) | not started |
| S11, S12 | Database connector; OpenAPI to tools | Postgres (running) | (unclaimed) | not started |
| S13 | NeMo Retriever multi-tenancy | S9 | (unclaimed) | not started |
| S8 | Speech (optional, GPU) | GPU | (unclaimed) | not started |
| Phase 1 | Vertical slice: AgentSpec schema, wizard, compilers A to C ([PLAN section 13](PLAN.md)) | Phase 0 findings | (unclaimed) | not started |

## Decisions (append only; newest last)
| Date | Decision | Why | Where |
|---|---|---|---|
| 2026-10-10 | Everything free or open source; local-first via Docker Compose | Personal open-source project, no budget | PLAN 3 |
| 2026-10-10 | NAT builds the agent, Fabric runs it, OpenShell contains it | Fabric docs name NAT as the reference adapter; NemoClaw does the same | PLAN 4.1 |
| 2026-10-10 | Our AgentSpec is the stable contract; NVIDIA pieces sit behind adapters with pinned versions | They are all 0.x | PLAN 1.2, 5 |
| 2026-10-10 | Default retrieval engine is `pgvector_lite`; NeMo Retriever is optional | Dev machine has no NVIDIA GPU; hosted endpoints are dev/test only | PLAN v7, 8.12 |
| 2026-10-10 | Pin `nemo-fabric==0.4.0` (no pre-releases) | Verified in the sandbox image; `--prerelease` pulls 0.5.0b3 | `requirements.txt` |
| 2026-10-10 | Native tool calling is the default agent mode, ReAct the fallback; Switchyard is an optional router, not the gateway | S2b parse failures; Switchyard is pre-1.0 with a demo-only server | PLAN 4.3 |
| 2026-10-10 | **Stay on a light/free LLM for now** (default `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter) | Cost; accept weaker agents and expect flaky runs until S14 | `.env.example` |
| 2026-10-11 | Project licence is **Apache-2.0** (there is no "Apache 2.1"); `LICENSE` is the unmodified official text from apache.org | Matches the NVIDIA stack, includes a patent grant, friendly to contributors | `LICENSE` |
| 2026-10-11 | Development default model is **gpt-4.1-mini** via OpenAI (paid, cents per test run); free OpenRouter model is the zero-cost fallback. Supersedes "stay on a free LLM" for day-to-day work | Measured: gpt-4.1-mini is 15/15 across NAT and Fabric; free and nano models are flaky with ReAct | `.env.example`, S14 |
| 2026-10-12 | **We own our NAT adapter** (patched copy of NVIDIA's Apache-2.0 reference, now in `services/runner/nat_adapter/`): supports ReAct and tool calling, Relay activation with typed LLM/tool events, tool-name repair; later repair steps go here | Upstream has no maintained NAT adapter and the reference is ReAct-only | `spikes/s2-fabric-nat/`, PLAN 4.1 |
| 2026-10-11 | **Native tool calling is the default agent mode** (confirmed by S14 data); ReAct is the fallback | gpt-4.1-nano: tool calling 5/5 vs ReAct 3/5 | PLAN 4.3 |
| 2026-10-10 | Secrets only in git-ignored `.env`; the sandbox gets a placeholder key through an OpenShell provider | The key must never enter the agent's environment | `spikes/s3-openshell/` |

## Gotchas (do not rediscover these)
- **Python:** NAT supports 3.11 to 3.13 only. Plain `python3` may be 3.14 and the install fails with a confusing "no matching distribution `nvidia-nat-atif==1.9.0`". `make setup` picks 3.12 (or uses `uv`).
- **Never install with `--prerelease=allow`** for the core set: it silently upgrades Fabric to 0.5.0b3. (`requirements-full.txt` needs `--pre` for one Azure dependency; that is the only exception.)
- **`nvidia-nat` alone is not enough:** you need `nvidia-nat-langchain[all]` (LLM providers) and `nvidia-nat-mcp`.
- **Calculator tool does not exist in NAT's library;** it is only in the repo's examples. `wiki_search` and `current_datetime` do.
- **Fabric config is Python objects, not YAML.** Tools need `add_tool_definition(...)` AND `config.tools.enabled = [...]`, or the agent has zero tools.
- **The Fabric NAT adapter runs in a subprocess,** so it needs `PYTHONPATH=services/runner/nat_adapter/src` (the Makefile sets it). It hides error details; set `FABRIC_NAT_DEBUG=1` to write tracebacks to `/tmp/fabric-nat-debug.log` (our local patch).
- **Free-model flakiness:** ReAct parse errors (action and final answer in one reply, or empty output). OpenRouter free tier is 50 requests a day and returns HTTP 429 after that; repeated test runs burn it fast. Do not conclude "Fabric is broken" from a failing run; run plain `make agent` first.
- **OpenShell on macOS:** Docker Desktop must have *Settings > Resources > Network > Enable host networking* on, or sandboxes cannot reach the gateway. Docker 28+ required.
- **OpenShell policy:** `run_as_user` must exist in the image (use numeric `"1000"`); the app directory must be owned by that uid (`COPY --chown`); allow rules name specific binaries (`/usr/bin/python3.12`); the default image has no `curl` or Python.
- **OpenShell installer** is a `curl | sh` that installs a Homebrew service. Read the script first (`install.sh` in the OpenShell repo) and run it yourself.
- **Disk full breaks Docker silently:** Docker's VM goes read-only and builds can produce 0-byte files. Keep several GB free; after freeing space rebuild with `--no-cache`.
- **`docker` not found in a terminal** on macOS: add `/Applications/Docker.app/Contents/Resources/bin` to PATH, or turn on Docker Desktop's CLI tools.
- **`uv pip install "nemo-fabric[relay]"` can break the `nemo_fabric_adapters` namespace package** (the Fabric adapter host then fails with `No module named nemo_fabric_adapters.common`). Fix: `uv pip install --reinstall nemo-fabric-adapters-common==0.4.0`.
- **Fabric has NO bundled NAT adapter.** `external/nat` in the Fabric repo is a source-only third-party reference (no PyPI package). It accepts only `fabric.agent.react`; ReAct is its hardwired agent type, not a Fabric or NAT requirement. Our copy also accepts `fabric.agent.tool_calling`.
- **To get Relay output through Fabric you need all four:** the adapter descriptor declares `telemetry.providers.relay`; `cfg.telemetry = TelemetryConfig(providers={"relay": ...})`; `cfg.relay = RelayConfig(...)`; and `cfg.runtime.artifacts = <dir>` (else no `FABRIC_RELAY_CONFIG_PATH`). The adapter must also activate Relay (our patched copy does). A running Relay instance is not a factor (checked).
- **Fabric accepting a `relay=` config does not mean the adapter uses it.** Check that files appear / `RunResult.telemetry` is non-empty; `doctor` will not tell you.
- **Answer-matching hides bad trajectories:** use the trajectory judge (`make eval`). Also check the scorer first: ours once counted `42.5.` != `42.5` and `1000.0` != `1000` as failures.
- **MCP tool names are prefixed** by NAT (`demo__add_numbers`). Weak models in ReAct mode drop the prefix, NAT rejects the call, and the agent loops to LangGraph's recursion limit (32) or gives up. Tool calling avoids it.
- **Subprocesses need the venv on PATH:** the MCP stdio server (`command: python`) and the Fabric adapter host both resolve `python` from PATH. If PATH lacks `.venv/bin` you get "Connection closed" or `No module named nemo_fabric_adapters.common`. `make` targets and the S14 harness set it; sandbox images bake it in.
- **`.env` keys must be one unbroken line, no spaces.** A key pasted with wrapped spaces makes the shell run fragments as commands and the key arrives empty (HTTP 401). A mis-copied key also gives 401; re-copy with the provider's copy button.
- **System Python 3.13 here has no CA certificates** (`CERTIFICATE_VERIFY_FAILED` with urllib); use `.venv/bin/python` for HTTPS calls.
- **Do not judge an agent run by its final text:** one "success" contained a made-up date. S14's harness checks the real time and the MCP server's own call log.
- **`--no-keep` OpenShell sandboxes** can keep their name for a few seconds ("already exists"); use a new name.

## Open questions / blockers
- Real pass rate of tool calling vs ReAct per model: unknown until S14 has quota or a local model.
- Does the Fabric NAT adapter accept a tool-calling target, or do we write our own adapter target? (S14b)
- Is NeMo Retriever usable for free in production, and does it do hybrid search? (S7, S10)
- Relay licence and version compatibility with Switchyard's plugin (needs Relay 0.8 to under 1.0). (S4, S7)

## Changelog (newest first, one line each)
- 2026-10-12: Added per-phase completion sections at the end (Phase 0 completed, Phase 1 to 8 placeholders).
- 2026-10-12: Phase 1 cleanup: adapter moved to `services/runner/nat_adapter/`, README/paths updated, Phase 1 kickoff list added.
- 2026-10-12: Typed Relay events (LLM + tool steps with tokens) for both agent types; tool-name repair built (0 triggers in A/B); `make test` added.
- 2026-10-12: S14 big suite (480 runs): tool calling >= ReAct everywhere, clearest gap on gpt-4.1-nano; Fabric matches plain NAT.
- 2026-10-12: Our NAT adapter copy now supports `fabric.agent.tool_calling`; nano through Fabric: tool calling 5/5 vs ReAct 4/5.
- 2026-10-11: Relay now emits ATOF + ATIF through Fabric via a patched NAT adapter copy; running-instance hypothesis ruled out; Relay events are graph-level only.
- 2026-10-11: S4 partial: NAT eval + ATIF working (`make eval`), Relay silent through NAT adapter, S14 gap not reproduced; `nvidia-nat-eval[full]` added to requirements.
- 2026-10-11: S14 partial: demo MCP server + manifest, MCP agent configs, test harness; first results (gpt-4.1-mini, gpt-4.1-nano). Default dev model now gpt-4.1-mini.
- 2026-10-11: Added Apache-2.0 `LICENSE`; README and CONTRIBUTING updated.
- 2026-10-10: Added contributor setup (requirements, lock file, Makefile, check script, dev container, README, CONTRIBUTING, this file).


---

# Phase completion record
One section per phase of the [PLAN roadmap](PLAN.md#13-roadmap-after-phase-0). When a task finishes, add a row to its phase's table with the date and evidence. A phase is "completed" when its deliverable (first line of each section) works end to end and is recorded here; carry-overs are listed, not hidden.

## Phase 0 completed (closed 2026-10-12, with carry-overs)
**Goal:** answer the risky questions before building. **Result:** the stack works end to end and the key design decisions have evidence. Carry-overs do not block Phase 1.

| Spike | What it settled | Status | Evidence |
|---|---|---|---|
| S1 NAT hello world | NAT runs with our own key and an MCP tool, no NVIDIA key | **done** | `spikes/s1-nat-hello/` |
| S2 / S2b NAT via Fabric | Fabric runs NAT agents (`plan`, `doctor`, `run`); Fabric has no NAT adapter of its own, so we own one | **done** | `spikes/s2-fabric-nat/`, `services/runner/nat_adapter/` |
| S3 OpenShell | Per-run sandbox with an egress allow-list and a hidden key; about 0.6 s start, about 24 MiB idle | **done** | `spikes/s3-openshell/` |
| S4 Relay and evals | NAT-native ATIF and `nat eval` work; Relay works through our adapter with typed LLM/tool events (model, tokens, tool args and results) | **done, with carry-overs** | `spikes/s4-relay-eval/`, `nat_adapter/relay_events.py` |
| S14 tool calling vs ReAct | 480-run suite: tool calling never worse, clearly better only on the weakest model; Fabric matches plain NAT | **done, with carry-overs** | `spikes/s14-tool-calling/` |
| Docker / dev environment | Compose stack, pinned requirements, `make` targets, clean-install verified | **done** | `deploy/`, `requirements.lock`, `make check` |

**Carry-overs (tracked in Next up; none blocks Phase 1):**
- **Reading only:** the rest of S7 (Relay and NIM/Riva/embedding licences). (S5 was retired from the plan.)
- **Phase 0 leftovers:** S6 (full run on Ollama, no spend); S4 rest (NeMo Evaluator, Relay ATIF in the eval harness, OTel export); S14 rest (gateway, Switchyard trial, model probe, larger N); tool-name repair benefit unproven.
- **Needed before Phase 3 and 4, not before Phase 1:** S9 to S13 (RAG baseline, NAT retrievers and RAG evals, database connector, OpenAPI to tools, NeMo Retriever multi-tenancy). S8 (speech) is optional.

**Phase 0 decisions worth remembering:** tool calling is the default agent mode, ReAct the fallback; we own the NAT adapter; `pgvector_lite` is the default retrieval engine; Switchyard is optional; free-tier LLMs are not reliable enough for evals (dev default `gpt-4.1-mini`). Full list under **Decisions**.

## Phase 1 completed: Vertical slice (weeks 3 to 6)
**Deliverable:** wizard (BYOK, model check, personal-automation template, 5 to 8 tools), AgentSpec, compilers A to C, run in an OpenShell sandbox in test mode, trace view. Task list: **Phase 1 kickoff** above (P1.1 to P1.7).

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |

## Phase 2 completed: Safety (weeks 7 to 9)
**Deliverable:** guardrail profiles, OPA policies, risk tiers, approval UI, per-tool sandbox policy generation.

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |

## Phase 3 completed: Integrations v1 (weeks 10 to 12)
**Deliverable:** connector service (database read-only, CSV/Sheets), schema introspection and entity mapping, generated lookup tools, compiler F, demo datasets and snapshot test mode, record viewer, web-chat and webhook channels. Needs S11, S12 first.

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |

## Phase 4 completed: Knowledge layer v1 (weeks 13 to 16)
**Deliverable:** `RetrievalEngine` (pgvector_lite default, NeMo Retriever optional), ingestion worker, `knowledge.search` / `faq.lookup` / `profile.get` over MCP, gateway-injected tenant scope, "Add knowledge" wizard step. Needs S9, S10, S13 first.

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |

## Phase 5 completed: Evals (weeks 17 to 19)
**Deliverable:** per model-and-template eval gate, NAT eval suites, RAG golden sets and metrics, connector tests, garak red-teaming, publish gate.

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |

## Phase 6 completed: More templates (weeks 20 to 24)
**Deliverable:** support, recruiting, job-applying, research, ops, sales templates; OpenAPI and bring-your-own-MCP connectors; app packs; email and schedule channels.

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |

## Phase 7 completed: Caller agents (weeks 25 to 31)
**Deliverable:** WebRTC voice, pluggable ASR/TTS, FAQ-first low-latency retrieval, voice guardrails and evals.

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |

## Phase 8 completed: Distribution (later)
**Deliverable:** docs, one-command install, sample agents, optional hosted demo (a separate cost decision).

| Task | Date | Evidence | Notes |
|---|---|---|---|
| _nothing completed yet_ | | | |
