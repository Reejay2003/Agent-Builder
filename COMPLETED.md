# COMPLETED: progress tracker and what not to redo

**Read this before starting any work.** It says what is done, what was decided, what broke before, and what is next. The long-term design is in [PLAN.md](PLAN.md); this file is the short, current truth.

## How to use this file (keeps us out of loops)
1. Before starting: find your task in **Next up**, put your GitHub handle in `Owner`, and set `Status` to `in progress` (do this in a small PR or an issue comment first).
2. While working: if you hit something that cost you more than 15 minutes, add it to **Gotchas**.
3. When done: in the **same PR** as the work, move the item to **Done** with the date, the evidence (a file, a command, or a result), and one line on what was learned. A spike that passed but is not recorded here did not happen.
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
| P1.7 | **Wizard** shell (Next.js): BYOK, template, tool basket, test run with trace view | `apps/web/` | (unclaimed) | partial: login + dashboard UI only (mock data, mock auth) |
Cleanup already done: adapter moved to `services/runner/nat_adapter/` (own README, tests, licence file); `make test`; eval deps pinned; harnesses updated; all runs re-verified after the move.

## Next up (suggested order; claim before starting)
| ID | Task | Needs | Owner | Status |
|---|---|---|---|---|
| S14 (rest) | Remaining: larger N and more tasks; Fabric tool-calling target (custom adapter?); wizard probe + repair step 1 (tool-name suffix mapping) and 3; LiteLLM gateway; Switchyard trial ([PLAN 4.3, 4.4, S14](PLAN.md)) | An LLM key (OpenAI key works; free tier is 50 requests/day) | (unclaimed) | partial |
| S4 (rest) | Try NeMo Evaluator; read Relay ATIF in the eval harness; OTel export; formally decide telemetry source of truth (Relay ATIF is now rich enough to be a candidate) | S2 | (unclaimed) | partial |
| S7 | Licence table in `docs/` | reading only | (unclaimed) | partial: NAT, Fabric, OpenShell, NeMo Retriever, Switchyard are Apache-2.0 [verified]; Relay, NIM/Riva terms, embedding model licences not read |
| S5 | Helix check (build on, borrow from, or ignore) | reading only | (unclaimed) | not started |
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
| 2026-10-20 | **Model configs in SQLite (`node:sqlite`, `apps/web/data/app.db`); API keys in an AES-256-GCM column under a per-user data key, wrapped by scrypt(login password) or a user-chosen key.** Supersedes OpenBao as the default secrets store; OpenBao stays an option for shared installs | Local-first means one owner per install, so a secrets server is overhead. Derived from the password, never the stored hash (that sits in the same file) | `apps/web/src/lib/`, `apps/web/src/app/api/model-configs/` |
| 2026-10-20 | **Per-model "Test connection" (one chat completion) replaces the wizard's ~10-call model check** (PLAN 4.4.1 probe and `capability_tier` dropped from the model config) | User decision: check that endpoint, key and model work; rating models per template is not wanted in the wizard | `apps/web/src/lib/connection-test.ts`, `POST /api/model-configs/:id/test` |
| 2026-10-20 | **Self-hosted models are one provider, `local`** (Ollama, LM Studio, llama.cpp, vLLM): same OpenAI API, presets only set the base URL. `ollama` provider value migrated to `local` | They differ only in port; one code path for test, model listing and the runner | `apps/web/src/lib/db.ts`, wizard step 1 |
| 2026-10-20 | **All agents run as ReAct; no per-model agent mode** (UI field and `agent_mode` column removed; spec shows a fixed `agent_mode: react`). Supersedes "native tool calling is the default" | User decision. Known trade-off from our own data: S14 tool calling >= ReAct (gpt-4.1-nano 97.5% vs 85-92.5%), S2b ReAct parse errors on free models | `apps/web/src/lib/db.ts`, wizard step 1 |

## Gotchas (do not rediscover these)
- **`npm run build` and `next dev` both run the SQLite migrations on `apps/web/data/app.db`** (route modules import `db.ts` while collecting page data). Back up the DB before changing the schema.
- **Turbopack dev can keep a stale server module after an edit** (seen: `httpUrl is not a function` while the compiled chunk had the export). Restart `npm run dev` before debugging further.
- **`apps/web/src/lib/db.ts` opens `data/app.db` relative to the current directory and migrates on import.** Importing it from a script run in `apps/web` touches the real DB; test migrations from another directory with a copy.
- **NAT's `_type: openai` client needs a non-empty `api_key` even for keyless local servers** [memory: OpenAI client behaviour, not re-checked]; the runner should pass a placeholder when a `local` config has no key.
- **Next 16 prerenders pages that use no request-time API.** A page that reads SQLite but no cookies (e.g. `/register`) becomes static at build time unless it calls `await connection()`. Check the `○`/`ƒ` column in `npm run build`.
- **Next 16 keeps visited pages mounted but hidden (React Activity).** Two `/login` and `/register` forms can be in the DOM at once; Playwright selectors need `:visible`.
- **`apps/web` needs Node 22.13+** for the built-in `node:sqlite` (repo runs on Node 26 with `@types/node` 26). Older `@types/node` does not know the module.
- **Unwrapped data keys live only in server memory.** After a server restart every session is locked: saving a new API key returns HTTP 423 until the user unlocks in Settings. Scheduled runs while the owner is signed out cannot decrypt keys yet.
- **`shadcn init` rewrites `globals.css`** to class-based dark mode (`.dark`), which breaks our `prefers-color-scheme` `dark:` classes; we switched the variant back to the media query.
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
- 2026-10-20: Removed agent mode from model configs (always ReAct). Wizard robustness: one `api()` helper so network failures, empty 500s and non-JSON bodies show a message instead of throwing; discover reuses a saved key only for the base URL it was saved with. [verified]: migration on copies of the current and a pre-`local` DB, then real DB rows identical to backup; `npm test` 10 pass; `npm run build`.
- 2026-10-20: Self-hosted models. Provider `local` with server presets (Ollama :11434, LM Studio :1234, llama.cpp :8080, vLLM :8000), Docker hint (`host.docker.internal`), key optional, 120 s default test timeout for cold model loads. `POST /api/model-configs/discover` lists model ids via `GET {base_url}/models` (free; works before saving, falls back to the saved key); wizard "Load models" fills a datalist. Table rebuilt to change the provider CHECK (`ollama` -> `local`). [verified]: migration on a DB copy (rows, encrypted key, FK, integrity) and then on the real DB (rows byte-identical to backup); `npm test` 10 pass (fake server: model listing, dedupe, empty server, timeouts); `npm run build`; discover returns 401 without a session. Not verified: a real local server (none running here) and the wizard UI in a browser.
- 2026-10-20: Test connection per model config. `POST /api/model-configs/:id/test` decrypts the key in memory, sends one `chat/completions` request (no sampling params) and stores `tested_at`, `test_ok`, `test_message`, `test_latency_ms`; results clear when provider, base URL, model or key change. Wizard button saves first, then tests. Plain-language errors for 401/403/404/429, timeout, unreachable host, non-chat replies. [verified]: `npm test` 8 pass (fake local OpenAI server: success, trailing slash, wrong/missing key, unknown model, bad reply shape, timeout, refused port), `npm run build`, endpoint returns 401 without a session. Not verified: the button in the browser (the only account is the owner's) and any real provider call. `verify_ssl=false` is not applied by the test.
- 2026-10-20: Single-user auth flow. `/register` is open only until the first account exists (then redirects to `/login`; `/login` redirects to `/register` while there is none). Registration shows a one-time recovery phrase (6x4 base32, 120 bits) that wraps a second copy of the data key; `/forgot` (email + phrase + new password) re-wraps the data key with the new password, resets the key source to password and signs out all sessions, so saved API keys survive. Accounts made before this have no phrase. [verified]: `npm test` (3 pass incl. phrase format), `npm run build` (`/register` dynamic via `connection()`), browser on an empty DB: `/login` sends to `/register`; register shows the phrase (Continue disabled until confirmed); `/register` then redirects to `/login`; reset with the phrase typed lowercase with spaces works; old password rejected; the API key saved before the reset still decrypts with the new password.
- 2026-10-20: Model config storage and API. SQLite tables `users`, `sessions`, `model_configs`; real login (scrypt password hash, hashed session tokens) replaces the mock; CRUD at `/api/model-configs` (GET list, POST, GET/PATCH/DELETE `:id`), JSON-only, scoped per user; Settings page to switch between password-derived and own encryption key, and to unlock. Wizard step 1 edits saved configs with all NAT-tunable fields (temperature, top_p, max_tokens, seed, request_timeout, max_retries, verify_ssl, agent_mode). [verified]: `npm test` (crypto round trip, wrong password and cross-user blobs rejected), `npm run build`, browser checks: CRUD statuses 201/409/400/415/200/204/404, a second user gets 404 on the first user's config, a locked session returns 423, own-key unlock rejects a wrong key, DB and WAL contain no plaintext key.
- 2026-10-20: `apps/web/` UI shell: Next.js 16.4.2 + Tailwind 4.3.3 (versions pinned). Email/password login (mock: any credentials accepted, email stored in an httpOnly `session` cookie via a server action), dashboard with mock agents table, sign out. No API or agent wiring. Verified [verified]: `npm run build` passes; in a browser `/` -> `/login` -> `/dashboard` -> sign out -> `/login`. Gotcha: Next 16 has Cache Components on, so a page that reads `cookies()` fails the build unless it is wrapped in `<Suspense>` or sets `export const instant = false`. Read `apps/web/node_modules/next/dist/docs/` before writing Next code; APIs differ from older versions.
- 2026-10-13: NeMo Evaluator integrated: `make eval-nel` (`agents/simple-agent/eval/run_nel.py`, `nel.yaml`, `nel_benchmark.py`; cases shared with `make eval-simple` via `cases.py`). `nemo-evaluator==0.3.0` + `greenlet==3.5.6` pinned (`nat serve` needs greenlet). nel starts `nat serve` and sends each case through its NatSolver. Same result as `nat eval` [verified]: answer 20/22, tools 13/22, both 12/22. `run_nel.py` patches three nemo-evaluator 0.3.0 / NAT 1.9 mismatches in-process: (1) the adapter proxy adds `model` to the body and NAT `/generate/full` returns 422 on any extra field, so the proxy is skipped for NAT services; (2) NAT streams tokens as many `data:` events and NatSolver kept only the last; (3) NAT reports tools as FUNCTION_START/END, NatSolver only maps TOOL_START/END. `type: custom` solvers are declared in its config but not wired in 0.3.0. `nemo-evaluator-launcher` 0.2.6 needs `nemo-evaluator<0.3.0`, so it is not used. Note: nel binds `nat serve` to 0.0.0.0 during the run.
- 2026-10-13: `make eval-simple` (`agents/simple-agent/eval/run_eval.py`): `nat eval` runs the unchanged simple agent on 22 cases (date, Wikipedia, both, no-tool, format, unknown topic) against local Nemotron-3-Nano-4B; it auto-starts llama-server and keeps macOS awake. Result [verified]: answer correct 20/22, required tools used 13/22, both 12/22. The model skips `wiki_search` for well-known facts. Gotchas: `avg_*` evaluators are not registered in nat 1.9.0 here; the trajectory judge gets an empty trajectory unless `enable_atif_evaluator: true`; a 4B judge is unreliable (6/22 parse failures, one score of 5.0, wrong weekday claims), so treat its score as advisory; `current_datetime` reports UTC, so expected dates use UTC.
- 2026-10-12: `agents/simple-agent/test_suite.sh` (11 cases, answer regex + required-tool check) run via `run.sh` against local llama-server 0.6.0 with Nemotron-3-Nano-4B Q4_K_M (`ENV_FILE=local-llama.env`). 7/11 [verified]. All 4 failures: the model answered famous facts from memory and skipped `wiki_search`; it calls the tool only for obscure topics or when told to "search Wikipedia". ReAct format held in every run; no parse failures. Same 7/11 after pulling db8c734 (`run.sh` keeps `ENV_FILE` plus the new `LLM_API_KEY` fallback).
- 2026-10-12: Phase 1 cleanup: adapter moved to `services/runner/nat_adapter/`, README/paths updated, Phase 1 kickoff list added.
- 2026-10-12: Typed Relay events (LLM + tool steps with tokens) for both agent types; tool-name repair built (0 triggers in A/B); `make test` added.
- 2026-10-12: S14 big suite (480 runs): tool calling >= ReAct everywhere, clearest gap on gpt-4.1-nano; Fabric matches plain NAT.
- 2026-10-12: Our NAT adapter copy now supports `fabric.agent.tool_calling`; nano through Fabric: tool calling 5/5 vs ReAct 4/5.
- 2026-10-11: Relay now emits ATOF + ATIF through Fabric via a patched NAT adapter copy; running-instance hypothesis ruled out; Relay events are graph-level only.
- 2026-10-11: S4 partial: NAT eval + ATIF working (`make eval`), Relay silent through NAT adapter, S14 gap not reproduced; `nvidia-nat-eval[full]` added to requirements.
- 2026-10-11: S14 partial: demo MCP server + manifest, MCP agent configs, test harness; first results (gpt-4.1-mini, gpt-4.1-nano). Default dev model now gpt-4.1-mini.
- 2026-10-11: Added Apache-2.0 `LICENSE`; README and CONTRIBUTING updated.
- 2026-10-10: Added contributor setup (requirements, lock file, Makefile, check script, dev container, README, CONTRIBUTING, this file).
