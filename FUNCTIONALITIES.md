# What the platform can do, and how it works

Interview-prep notes for the owner. One entry per feature: what it is, why it exists, how it works step by
step, what was decided, what it cannot do. From now on it holds only what [PLAN.md](PLAN.md) does not already
describe (or how we differed from it); see the plan filter in the skill. Kept up to date by the `/log-functionality` skill
(`.claude/skills/log-functionality`). For the dated change history see [COMPLETED.md](COMPLETED.md).

**One-minute pitch.** Agent Builder lets a person describe an AI agent in a small file (the *AgentSpec*): which
model, which tools, what rules. The `agentbuilder` Python SDK checks that file, turns it into the configs
that NVIDIA's agent stack understands, runs the agent (on this machine or inside a locked-down virtual
machine), and records exactly what the agent did. A local web app is the friendly front end for the same SDK.

```
 AgentSpec (YAML/JSON)  ──validate──►  CompiledAgent ──┬─► NAT workflow YAML        (compiler A)
   one file, by reference only         one plain         ├─► NeMo Fabric config       (compiler B)
   (no keys inside)                    description       └─► OpenShell policy+profile (compiler C)
                                                                 │
        Runner ◄───────────────────────────────────────────────┘
   LocalRunner (this machine)  |  SandboxRunner (OpenShell microVM)
        │  uses: model (key by reference) + tools (MCP servers, risk tiers, mock mode)
        ▼
   RunResult: text, trajectory (every model call and tool call), warnings
```

## Recent additions (newest first)
- 2026-11-07 · F20 compiler D's single rule and OPA parity; F21 the eval gate; F15 approvals and audit log across the VM wall.
- 2026-11-07 · F19 The web app and the SDK: the key only goes to the URL it was saved with; the vault answers only an unlocked owner.
- 2026-11-07 · F18 rewritten: real human approvals (tool server waits, `ab run` asks in the terminal, the server queues for the web app). F4: the trajectory is redacted too. F14, F15: real-model results.
- 2026-11-07 · F5, F6 updated: the audit log rotates at 10 MB; `web.search` checks the result-list markup, not the words "No results".
- 2026-11-07 · F18 One approval rule for server, CLI and both runners.
- 2026-11-07 · F17 A key is never sent over plain http to a public host.
- 2026-11-07 · F5, F10, F15 updated: rate limits across runs; 429 and plain 500s; sandbox prompt on stdin and leftover-provider sweep.
- 2026-11-07 · F15 SandboxRunner: the agent runs inside an OpenShell microVM.
- 2026-11-07 · F14 Repair steps from the spec (`tool_names`, `reprompt`, `retry`).
- 2026-11-07 · F13 Model check (probe): one real call, then `agent_mode` auto or react.
- 2026-11-07 · F10 update: live runs of tier-2 tools are refused until approvals exist.
- 2026-11-06 · F6–F8 Personal tools, Google sign-in, tool gateway.
- 2026-11-05 · F9–F12 LocalRunner, local server, `ab` CLI, vault-backed keys.

## Index
| # | Area | Feature |
|---|---|---|
| F1 | Spec | AgentSpec: the one file that describes an agent |
| F2 | Compile | Compilers A, B, C and honest warnings |
| F3 | Models | `agent_mode: auto` and the capability table |
| F4 | Models | Credentials by reference, never by value |
| F5 | Tools | `@tool`, manifests, risk tiers, MCP server, mock mode |
| F6 | Tools | Personal tool library (Gmail, Calendar, Sheets, web search) |
| F7 | Tools | Google sign-in (`ab auth google`) |
| F8 | Tools | Tool gateway wrapper |
| F9 | Runtime | LocalRunner |
| F10 | Server | Local SDK server (HTTP API for the web app) |
| F11 | CLI | The `ab` command and `ab ui` |
| F12 | Observe | Trajectory reader (what the agent did) |
| F13 | Models | Model check (probe) |
| F14 | Reliability | Repair steps |
| F15 | Runtime | SandboxRunner (OpenShell microVM) |
| F16 | Process | Automatic daily work log |
| F17 | Models | No API key over plain http to a public host |
| F18 | Safety | Human approvals: the pause happens inside the tool server |
| F19 | Web | The web app and the SDK: who may send the key where |
| F20 | Safety | One allow/ask/deny rule, proven against a real OPA (compiler D) |
| F21 | Evals | The eval gate: scored from what the agent did, with honest ranges |

---

## Spec and compile

### F1. AgentSpec: the one file that describes an agent
- **Added:** SDK weeks 1–2 · **Status:** done
- **What it is:** A versioned file (`spec_version: 1`) with the agent's name, model, tools, instructions, approval rules and sandbox settings. Loaded and checked by `AgentSpec.from_dict` / `AgentSpec.load`.
- **Why we built it:** The web wizard, the CLI and tests all need one shared, checkable description of an agent, so nothing is configured by hand in three places.
- **How it works:** 1) The file is read as YAML or JSON. 2) Strict pydantic models check every field; unknown fields are errors, not ignored. 3) Problems come back one per line as `field.path: message`, so the web app can show them next to the right input. 4) A JSON schema file ships with the package, and a version module can migrate old specs. 5) Credentials may only be references (`env://NAME` or `secret://path`); a pasted key is refused.
- **Decisions and trade-offs:** Strict beats forgiving: a typo should fail loudly. Fields the spec accepts but nothing applies yet (for example guardrail profiles) are listed as warnings so they never look like protection.
- **Limits:** Several sections (knowledge, voice, channels, routing) are accepted but not applied yet.
- **Where:** `packages/sdk/src/agentbuilder/spec/` (`models.py`, `errors.py`, `migrate.py`, `agent-spec.schema.json`).
- **Proof:** spec and compile test suites in `packages/sdk/tests`.
- **Not verified:** none for this part.
- **Interview angle:** *Why a spec file instead of code?* One declarative source that a UI can edit, a CI job can validate, and a compiler can turn into several runtime formats. *Why refuse inline keys?* Specs get shared and committed; a key in one is a leak.

### F2. Compilers A, B, C and honest warnings
- **Added:** SDK weeks 2–3 · **Status:** done for A, B, C (approval rules, compiler D, are not built)
- **What it is:** `compile_agent(spec, catalog)` makes a plain `CompiledAgent`; three small emitters turn it into: **A** a NeMo Agent Toolkit (NAT) workflow YAML, **B** a NeMo Fabric config, **C** an OpenShell sandbox policy and model provider profile.
- **Why we built it:** NVIDIA's tools each want their own format. One internal description means the user's spec never changes when a runtime does.
- **How it works:** 1) Tools in the spec are looked up in the catalog; unknown ones are an error. 2) The model is resolved (defaults, agent mode). 3) A tier-3 (destructive/financial) tool with the default policy "block" stops the compile. 4) Warnings are collected for things that are not enforced. 5) Emitters are pure functions of the `CompiledAgent`. Compiler C builds network rules only from each tool's declared hosts, so everything else is denied.
- **Decisions and trade-offs:** The core SDK imports no NVIDIA package; only the runner package does. Golden-file tests pin the generated YAML/JSON.
- **Limits:** Network rules are per sandbox, not per tool server (all tool servers share the same Python binary). Tool hosts are port 443 only.
- **Where:** `packages/sdk/src/agentbuilder/compile/`.
- **Proof:** golden-file tests (`tests/golden/`), `test_compile.py`, `test_sandbox_policy.py`; policy proven on a real OpenShell sandbox (`api.github.com` allowed, `example.com` refused) [verified].
- **Not verified:** none for this part.
- **Interview angle:** *Why generate configs instead of calling NAT directly?* Swappable runtimes and testable output. *How do you stop an agent reaching the internet?* The policy lists only hosts the tools declared; the sandbox denies the rest.

## Models

### F3. `agent_mode: auto` and the capability table
- **Added:** SDK week 1 · **Status:** done
- **What it is:** The agent can use the model's native *tool calling* or the older text format *ReAct*. In `auto`, the SDK picks for you.
- **Why we built it:** On free models our ReAct agent failed about half its runs because the model answered in the wrong text format; native tool calling avoids that parsing step.
- **How it works:** 1) An explicit mode in the spec always wins. 2) Otherwise `resolve_agent_mode` looks the model up in `capabilities.yaml` (exact name or a dated snapshot). 3) If the table says tool calling is unsupported it picks ReAct; if it has a recommended mode it uses that. 4) Unknown models default to tool calling. A model's tier (strong/standard/limited/unsuitable) comes from its measured success rate (>=99%, >=95%, >=85%).
- **Decisions and trade-offs:** The table only holds measured rows (from our spike runs), never guesses. Unknown stays unknown.
- **Limits:** The table has only a handful of models.
- **Where:** `packages/sdk/src/agentbuilder/models/capabilities.py`, `capabilities.yaml`.
- **Proof:** tests include a self-consistency check of the table.
- **Not verified:** none for this part.
- **Interview angle:** *Why not always ReAct?* It needs the model to follow a text format exactly. *Where do the numbers come from?* Our own runs, with the evidence noted per row.

### F4. Credentials by reference, never by value
- **Added:** SDK weeks 1–3 · **Status:** done
- **What it is:** Keys are named, not stored: `env://OPENAI_API_KEY` or `secret://modelcfg/<id>/api_key`.
- **Why we built it:** A key once arrived garbled (pasted over two lines), and specs get shared; keys must not live in them or in logs.
- **How it works:** 1) `resolve_credential` reads `env://` from the environment or `secret://` from a store, falling back to `AGENTBUILDER_SECRET_<PATH>`. 2) A value with spaces or line breaks inside is refused with a clear message. 3) The value is held in a `Secret` object that prints as `****`. 4) `redact()` scrubs any text before it is logged or returned, including the run's trajectory: a provider that rejects a key can echo it back in its error, and the trajectory records that error (found by CI on Linux, 2026-11-07). 5) The web app's vault is read by `LocalVaultStore` over loopback (`GET /api/internal/secrets/<name>`), never following redirects.
- **Decisions and trade-offs:** The local server resolves `env://` from an empty environment by default, so a shared spec cannot read the server's own variables.
- **Limits:** The vault side is the web app's work (a colleague's), not finished by the SDK.
- **Where:** `models/credentials.py`, `models/vault.py`, `runtime.credential_env`.
- **Proof:** credential tests; tests that force the key into error text and check it is removed (mutation-checked).
- **Not verified:** the vault against the real web app's endpoint.
- **Interview angle:** *How do you keep keys out of logs?* Secret type + redact on every outward path + tests that try to leak. *Why the empty environment on the server?* Otherwise a spec could name any variable and exfiltrate it.

## Tools

### F5. `@tool`, manifests, risk tiers, MCP server, mock mode
- **Added:** SDK weeks 2–3, rate limit and log rotation updated 2026-11-07 · **Status:** done
- **What it is:** A Python function becomes an agent tool with `@tool(...)`. The SDK derives a manifest (name, input schema from type hints, plain description, network hosts, risk tier) and can serve it as an MCP (Model Context Protocol) server.
- **Why we built it:** The agent, the sandbox policy and the approval rules all need to know what a tool touches. One declaration feeds all of them.
- **How it works:** 1) `@tool` builds a manifest and refuses a risk tier that understates the side effects. 2) Tiers: 0 read-only, 1 writes, 2 contacts other people, 3 destructive or financial. 3) `build_server` wraps each tool: inputs validated, every call appended to an audit log, `--mock` returns the manifest's `mock_response` without running the function, and a per-minute rate limit is enforced (sliding one-minute window; the call over the limit gets a plain "slow down" error and never runs). 4) When the gateway gives an audit log, the count lives in a locked file next to it (`rate-limits/<tool id>`), so it holds across runs and tool processes. Mock calls are not counted. 5) The audit log rotates at 10 MB (`MAX_LOG_BYTES`): the full file becomes `<name>.1`, replacing the older one, so it never takes more than about 20 MB. The writer holds a file lock and rotates only if the path is still the file it opened, so two tool servers never rotate twice and no line is lost.
- **Decisions and trade-offs:** Test mode must never touch a live system, so mock is a server flag, not a promise by the tool author. The count was first kept in memory, but tool servers start fresh for every run, so "10 a minute" really meant "10 per run"; a file shared by all runs fixes that without a database.
- **Limits:** Without an audit log (for example inside the sandbox) the count is per process. The file lock is POSIX only (macOS, Linux).
- **Where:** `packages/sdk/src/agentbuilder/tools/` (`decorator.py`, `manifest.py`, `catalog.py`, `mcp_server.py`).
- **Proof:** `test_tools*.py` (real MCP client over stdio); rate-limit tests with a fake clock and across two separate servers sharing one log [verified].
- **Not verified:** none for this part.
- **Interview angle:** *What stops a looping agent spamming an API?* The enforced rate limit. *Why mock at the server?* The model cannot talk its way past it.

### F6. Personal tool library (Gmail, Calendar, Sheets, web search)
- **Added:** 2026-11-06 · **Status:** done offline; no live Google call yet
- **What it is:** Six ready tools: `gmail.read` (tier 0), `gmail.send_draft` (tier 1, makes a draft only), `calendar.list_events` (0), `calendar.create_event` (tier 2), `sheets.read` (0), `web.search` (0, DuckDuckGo, free, unofficial).
- **Why we built it:** The personal-automation template needs real tools, and each one shows a different safety rule.
- **How it works:** 1) One MCP server per namespace (`python -m agentbuilder.library.server gmail`) so network access is per namespace. 2) Every input is validated before any network call (one plain email address, ISO times with a timezone, sheet id and range patterns, caps on rows and results). 3) Text from outside is cleaned of control characters and truncated, because mail and web pages can contain instructions aimed at the model. 4) Calendar events are created with `sendUpdates=none`, so no invitation emails go out. 5) No sending scope is ever requested, so a draft cannot become a sent mail. 6) `web.search` raises a clear error on a page it cannot read, instead of looking like "no results". It decides by markup, not text: only a page with DuckDuckGo's result-list container (`class="results"`) or its empty-search box (`class="no-results"`) counts as a real search page. A captcha page that happens to say "No results" is an error.
- **Decisions and trade-offs:** Draft-only email and silent events trade convenience for safety until human approvals exist.
- **Limits:** DuckDuckGo's HTML page is unofficial and can rate-limit or change.
- **Where:** `packages/sdk/src/agentbuilder/library/`, manifest `packages/tool-manifests/personal_tools.manifest.json`.
- **Proof:** about 60 offline tests against a fake Google server; mutation-checked (turning off email validation or `sendUpdates=none` fails tests); the personal template ran on real NAT with mocked Gmail [verified].
- **Not verified:** live drafts, event creation and Sheets reads. Live `gmail.read` and `calendar.list_events` against the owner's account worked on 2026-11-07 [verified].
- **Interview angle:** *What is prompt injection and what did you do?* Mail text can say "do X"; tools return it cleaned and labelled as data, risky tools are tiered, and tier 2 live runs are blocked until approvals exist. *Why one server per namespace?* Least privilege per namespace.

### F7. Google sign-in (`ab auth google`)
- **Added:** 2026-11-06 · **Status:** done offline
- **What it is:** A command that signs the user in to Google once so the Gmail/Calendar/Sheets tools can work.
- **Why we built it:** Using Google needs OAuth; asking users for a password or key would be unsafe.
- **How it works:** 1) The user creates a Desktop OAuth client in Google Cloud and gives the JSON file. 2) The command opens a browser using the OAuth installed-app flow with PKCE and a state check. 3) Google redirects to a loopback port on this machine. 4) The refresh token is saved to `~/.config/agentbuilder/google-token.json` (file mode 0600, folder 0700). 5) Tool servers read that file, because their environment is cleaned. 6) `status` never prints secrets; `revoke` calls Google and deletes the file.
- **Decisions and trade-offs:** Google's URLs are constants in code, never read from the client file, so a crafted file cannot redirect the secret. Free option chosen; Google "Testing" status expires sign-ins after 7 days (from our knowledge, to confirm).
- **Limits:** Weekly re-sign-in while the app is in Testing.
- **Where:** `library/google.py`, `ab auth`.
- **Proof:** `test_library_google.py` against a fake Google [verified].
- **Not verified:** the real sign-in.
- **Interview angle:** *Why PKCE?* A desktop app cannot keep a client secret secret; PKCE binds the code to this login attempt. *Why a token file?* The tool subprocess has a sanitized environment.

### F8. Tool gateway wrapper
- **Added:** 2026-11-06 · **Status:** done (thin local version)
- **What it is:** The single place that decides how tool servers are started for a run: in mock mode or live, and with one shared audit log.
- **Why we built it:** Later a dedicated gateway (for example one based on LiteLLM) should replace it without changing callers.
- **How it works:** 1) `Gateway.apply(catalog, mock, audit_log)` returns a catalog. 2) `LocalGateway` adds `--mock` and `--log <file>` to servers the SDK built (`gateway_flags`). 3) A mock request for a server it did not build is refused, because mock could not be guaranteed. 4) `ab ui` and `ab run --mock` write to `~/.local/state/agentbuilder/tool-calls.jsonl`, so you can prove after a test which tools ran.
- **Decisions and trade-offs:** A tiny interface now, a swap later.
- **Limits:** LiteLLM's MCP-gateway feature was not checked.
- **Where:** `packages/sdk/src/agentbuilder/gateway.py`.
- **Proof:** `test_gateway_and_library_servers.py` [verified].
- **Not verified:** a LiteLLM-backed gateway.
- **Interview angle:** *Why not build a full gateway now?* No second implementation exists yet; an interface keeps the door open without guessing its shape.

## Running agents

### F9. LocalRunner
- **Added:** 2026-11-05 · **Status:** done
- **What it is:** Runs a compiled agent on this machine through NeMo Fabric and NAT, with our own adapter, and returns a `RunResult`.
- **Why we built it:** Everything above needs something that actually runs the agent and reports honestly what happened.
- **How it works:** 1) Check the model key is present (a missing key is reported before anything starts). 2) Build the Fabric config. 3) Set the environment Fabric's separate adapter process inherits: the key under the variable the spec names, `ADAPTER_PYTHON`, and an absolute `PYTHONPATH`. 4) Run Fabric with Relay telemetry on. 5) Read the trajectory file back. 6) Restore the environment. Runs are serialised by a lock (taken in a worker thread so the event loop never blocks).
- **Decisions and trade-offs:** The environment is process-wide, so two runs with different keys must not overlap; a lock is simpler than per-run processes for one user.
- **Limits:** One run at a time per process.
- **Where:** `packages/sdk-nat/src/agentbuilder_nat/local.py`, our adapter in `nemo_fabric_adapters/nat/`.
- **Proof:** `test_local_runner.py` against a fake OpenAI server on real NAT and Fabric [verified]; redaction tests.
- **Not verified:** a run against a real paid model with the owner's key.
- **Interview angle:** *Why own the adapter?* NVIDIA's reference supports only ReAct and ignores telemetry; ours adds tool calling, typed events and repair hooks.

### F10. Local SDK server (HTTP API for the web app)
- **Added:** 2026-11-05 · **Status:** done
- **What it is:** A small server on 127.0.0.1 with endpoints to validate a spec, start a run, read its result, list tools, and check a model.
- **Why we built it:** The browser app should use the SDK, not duplicate it.
- **How it works:** 1) Only the web app's server holds a token and sends it in `X-AgentBuilder-Token`. 2) Requests must have a loopback `Host` (blocks DNS rebinding) and no `Origin` header (a browser page calling directly is refused). 3) `POST /runs` takes a spec, a prompt and `mock` (default true), compiles, and runs in the background; the last 50 runs are kept in memory. 4) Errors are per field. 5) A live run of a tier-2 tool without approval is refused (see F18). 6) When 50 runs are unfinished, new ones get 429; only finished runs are ever forgotten. 7) Any error a handler did not expect becomes a plain 500, and only its type is logged, never its text.
- **Decisions and trade-offs:** Standard library only, no web framework: built for one user on one machine.
- **Limits:** In-memory runs; no runner choice field yet (always `local`).
- **Where:** `packages/sdk/src/agentbuilder/server/app.py`; contract in PLAN §16.13.
- **Proof:** server tests (auth, host, origin, per-field errors, mock default, tier-2 refusal with a mutation check) [verified].
- **Not verified:** end to end with the web app.
- **Interview angle:** *Why a token if it is localhost?* Other local programs and web pages can reach localhost. *Why default to mock?* A test click should never send a real email.

### F11. The `ab` command and `ab ui`
- **Added:** 2026-11-05 · **Status:** done
- **What it is:** `ab ui | validate | compile | run [--mock] | doctor | tools | auth | probe-model`.
- **Why we built it:** A terminal path for developers, and the launcher for the web app.
- **How it works:** `ab ui` starts the SDK server on a free port, starts the web app, passes both the API URL, an API token and a vault token as environment variables, and stops both on Ctrl-C or SIGTERM.
- **Decisions and trade-offs:** The local web app is the SDK's front end, not a separate product.
- **Limits:** Needs Node for the web app.
- **Where:** `cli.py`, `ui.py`.
- **Proof:** `test_cli_and_ui.py`.
- **Not verified:** the full wizard flow in a browser.
- **Interview angle:** *How do the two servers trust each other?* Two random tokens per session, one in each direction.

### F12. Trajectory reader (what the agent did)
- **Added:** SDK week 3 · **Status:** done
- **What it is:** Reads the run record NeMo Relay writes (ATIF format) into typed objects: each model call, each tool call with arguments and result, tokens.
- **Why we built it:** To test and debug agents we need facts about a run, not only the final text.
- **How it works:** Parses the file strictly (malformed input is a clear `TrajectoryError`), exposes `tools_used`, `real_tool_calls`, token totals. The server turns it into a trace for the UI, clipping long text.
- **Decisions and trade-offs:** Eval-style checks (was this tool used?) can run on the same object.
- **Limits:** Reads the format version we pinned.
- **Where:** `packages/sdk/src/agentbuilder/observe/trajectory.py`.
- **Proof:** reader tests including malformed input after a review round.
- **Not verified:** newer ATIF versions.
- **Interview angle:** *Why trust the trajectory over the model's answer?* The model can say it used a tool without doing so; the record cannot.

## Reliability

### F13. Model check (probe)
- **Added:** 2026-11-07 · **Status:** done offline; not run against a real provider
- **What it is:** One real chat request that checks the endpoint, the key, the model name and whether the model can use tools, then tells the wizard whether to write `agent_mode: auto` or `react`. Available as `probe_tool_calling`, `POST /model/check` and `ab probe-model`.
- **Why we built it:** Weak models fail by answering in the wrong format. Better to find out when the user connects the model than in the middle of a run. It doubles as the wizard's "Test connection".
- **How it works:** 1) Resolve the model and key. 2) Send one request offering a tool `add_numbers` with `tool_choice: required`. 3) A valid call with numeric arguments means `auto`. 4) A reply without a call, or an error about tools, means "try again with `tool_choice: auto`" (some providers reject or ignore `required`), then `react` if that fails too. 5) 401/403, 404, 429 or other errors leave the spec alone with a plain message. 6) A 429 or 5xx is retried twice, honouring `Retry-After` up to 10 seconds; a longer wait (a spent daily quota) is not retried. 7) The key travels only in the Authorization header, redirects are never followed, and the key is scrubbed from provider text.
- **Decisions and trade-offs:** The earlier plan was a 10-call test per template; we chose one call, because the free tier allows only 50 requests a day and the real measuring belongs to the eval gate.
- **Limits:** One sample proves little; it screens out clearly unsuitable models only. The endpoint can send a stored key to the URL the request names (same trust as `POST /runs`; noted for later).
- **Where:** `models/probe.py`, `repair.py`, `server/app.py` (`check_model`), `cli.py`.
- **Proof:** `test_model_probe.py` (every answer shape, key never in output, retry and quota behaviour, a real HTTP redirect test) [verified offline].
- **Not verified:** a real provider.
- **Interview angle:** *Why not test the model with many tasks?* Cost and quota; a probe screens, an eval measures. *What did you get wrong at first?* Requiring a tool call would have downgraded tool-capable models whose provider ignores `required`; we added the `auto` retry.

### F14. Repair steps
- **Added:** 2026-11-07 · **Status:** partial (see Limits)
- **What it is:** Three optional helpers a spec can switch on under `model.reliability.repair.steps`: `tool_names`, `reprompt`, `retry`.
- **Why we built it:** Weak models make small, fixable mistakes, such as calling `add_numbers` when the tool is named `demo__add_numbers`.
- **How it works:** 1) `tool_names`: the compiler records it; `LocalRunner` sets `FABRIC_NAT_REPAIR=tool_names`; the adapter wraps NAT's tool lookup and, only if exactly one tool matches after trivial cleanup, uses it. Every repair is reported as a run warning. 2) `reprompt`: sets NAT's parse re-prompt count (`parse_agent_response_max_retries`) to `max_attempts`, so a format error is sent back to the model. 3) `retry`: NAT already retries failed model calls itself; the compiler says so in a warning.
- **Decisions and trade-offs:** A repair may only reshape what the model produced; it never invents a tool call or arguments. Repairs are never silent. Nothing is on unless the spec lists it.
- **Limits:** ReAct mode only (the compiler warns for tool calling). In our earlier 60-run test the name repair never triggered, so its benefit is unproven. Repair cannot fix wrong answers or answers given without calling a tool.
- **Where:** `compile/compiler.py`, `agentbuilder_nat/local.py`, `nemo_fabric_adapters/nat/repair.py`, `repair.py` (retry helper).
- **Proof:** compile tests, adapter tests, a runner test that the switch reaches the adapter and repairs appear in warnings [verified].
- **Not verified:** that repair earns its cost on real models. One real ReAct run (`gpt-4.1-mini`, 2026-11-07) used 5470 tokens against 1252 in tool-calling mode, never called a tool, and no name repair fired.
- **Interview angle:** *What must a repair never do?* Change meaning. *How do you know it helps?* We do not yet; it is off by default and every use is visible so the rate can be measured.

### F15. SandboxRunner (OpenShell microVM)
- **Added:** 2026-11-07 · **Status:** done for the SDK's own tools
- **What it is:** A second runner that runs the whole agent inside an OpenShell sandbox: a small virtual machine with a generated network allow-list and the model key kept outside.
- **Why we built it:** Local runs trust the agent and its tools with your machine. The sandbox limits the damage if a tool or the model misbehaves.
- **How it works:** 1) Compile, then refuse any tool server that is a program on this machine (only the SDK's own servers exist in the image). 2) Write the policy (compiler C) and the model's provider profile. 3) Create a per-run OpenShell provider holding the key, passing the key through the environment of that one command, never the command line. 4) Create the sandbox from the image with that provider, `--no-keep`, and run `python -m agentbuilder_nat.sandbox_main`. The compiled agent and the prompt (no key inside) go in as one JSON line on standard input, not as an argument, because arguments show in `ps` for every user of the machine. 5) Inside, `LocalRunner` runs as usual; the agent only sees a placeholder, and the sandbox proxy adds the real key to requests for the model host only. 6) The host reads one `AGENTBUILDER_RESULT` line, then always deletes the provider (and the sandbox after a failure or timeout). 7) Each run first deletes per-run providers older than the run timeout: names are `ab-<start time>-<4 hex>`, so a provider left by a killed run is found and removed, while one belonging to a run still going is left alone.
- **Decisions and trade-offs:** Reuse `LocalRunner` inside the VM so there is one agent code path. The SDK is installed into the image's site-packages because the VM driver ignores image environment settings and tool servers start with a cleaned environment. Things found only on the real gateway: profiles are global by id, so a non-default port is part of the id; sandbox names may be at most 19 characters; OpenShell forwards standard input but never closes it, so the reader takes exactly one line.
- **Approvals and the audit log across the VM wall (2026-11-07):** OpenShell streams the VM's stdout and forwards each stdin line live (tested on the real gateway). Inside, `sandbox_main` runs `LocalRunner` with an approver that prints `AGENTBUILDER_APPROVAL <request>` and waits for a stdin line with that request's id; the host reads the output live (`_popen_stream`), asks the real approver and writes the answer back. A line for another id is ignored, so nothing else printed in the VM can answer for a real request, and the host answers each id once. Time a person spends deciding is added to the run's deadline. After the run, the VM prints its tool-call log (`AGENTBUILDER_AUDIT`) and the host appends each valid line to its own audit log with `sandbox: true`.
- **Limits:** Only the SDK's tool servers; rate limits inside the VM count per run; a provider left by a killed run holds the key until the next sandbox run sweeps it; no Google token reaches the VM yet, so live Google tools cannot work there.
- **Where:** `packages/sdk-nat/src/agentbuilder_nat/sandbox.py`, `sandbox_main.py`, `packages/sdk-nat/sandbox/Dockerfile`, `make sandbox-image-sdk`.
- **Proof:** real microVM: a live tier-2 call waited for the host's approver with its exact payload, the decline reached the VM and its audit line came back [verified 2026-11-07]; 12 tests, 10 without a real sandbox (key never in argv, prompt only on stdin, provider sweep, names within 19 characters); on a real microVM the agent succeeded with a mock Gmail tool and a fake model reached through `host.openshell.internal`, the key appeared nowhere in the result, and no per-run provider remained [verified].
- **Not verified:** none for the key path: a real run with OpenAI `gpt-4.1-mini` succeeded in the microVM with the key injected by the proxy, and the key appeared nowhere in the output [verified 2026-11-07].
- **Interview angle:** *How does the agent call the model without holding the key?* The proxy outside the agent adds it. *Why a microVM and not a container?* Its own kernel and no network device, so the policy cannot be bypassed by a shared kernel or a raw socket.

### F17. No API key over plain http to a public host
- **Added:** 2026-11-07 · **Status:** done
- **What it is:** A spec that has a key (`credential_ref`) and a `base_url` starting with `http://` to an internet host is refused when it is loaded. Not described in the plan.
- **Why we built it:** The model check and runs send the key in a header to whatever `base_url` says; over plain http anyone on the path can read it. Found in the code audit.
- **How it works:** 1) The `ModelSpec` check runs on every spec load (server, CLI, model check, runners all load specs the same way). 2) http is allowed for `localhost`, loopback, private network addresses (for example a GPU box at `192.168.x.x`), and names ending `.local` or `.internal` (for example `host.openshell.internal`, which a sandbox uses to reach this machine). 3) Without a key, plain http is fine anywhere.
- **Decisions and trade-offs:** One check in the spec instead of one in each caller, so no caller can forget it. Local models over http keep working.
- **Limits:** It does not yet pin the key to the URL saved with the model in the vault, so a token holder could still send a stored key to another https host.
- **Where:** `packages/sdk/src/agentbuilder/spec/models.py` (`_sends_key_in_clear`).
- **Proof:** `test_models.py` (8 URLs: public http refused; https, loopback, private, `.local`, `.internal` allowed) [verified].
- **Not verified:** none for this part.
- **Interview angle:** *Why not just require https?* Local models (Ollama, a box on your network) usually speak plain http, and there the key does not cross the internet. *Why in the spec and not in the HTTP client?* Every path loads a spec; not every path uses the same client.

### F18. Human approvals: the pause happens inside the tool server
- **Added:** 2026-11-07 (replaces the interim "refuse every live tier-2 run" guard of the same day) · **Status:** done for `LocalRunner`, `ab run` and the local server; not in the sandbox runner
- **What it is:** PLAN §16.4 and §7.5 say tier-2 actions call an `approve` callback with the exact payload and show in an approval queue. This entry covers HOW we built it, which the plan does not say: the wait happens in the tool server, and the two sides talk through a private folder.
- **Why we built it:** Tier-2 tools (for example `calendar.create_event`) contact other people. A mail the agent reads can carry instructions (prompt injection), so a person must see the exact call before it happens.
- **How it works:** 1) `needs_approval(compiled)` lists tools a person must approve: tier 2 under `tier2_external_comms: require_human`, tier 3 under `tier3_destructive: require_human`. 2) `runner.run(..., approve=callback)`: `LocalRunner` makes a private folder for the run (0700) and `with_approvals` adds `--approvals <folder> --approve <tool ids>` to each live SDK-built tool server holding such a tool. 3) Compiler A raises NAT's tool-call timeout for those servers (60 s by default) to 10 minutes plus a margin. 4) Before such a tool runs live, the tool server first applies the rate limit, then writes `<id>.request.json` with the tool, tier and the exact arguments, and waits for `<id>.decision.json`. 5) `ApprovalWatcher` (a thread on the host) reads the request, calls the callback, writes the decision. 6) Yes: the tool runs. No, no answer in 10 minutes, or an approver that crashes: the tool does not run and the model is told "a person declined this call; do not try it again". The audit log records approved, declined or expired. 7) Who answers: `ab run` shows the payload in the terminal and needs an explicit `y`; without a terminal the run is refused before it starts. The local server parks the request on the run (`GET /runs/{id}` shows `waiting_for_approval` and the arguments) and the web app answers with `POST /runs/{id}/approvals/{approval_id}`. 8) `unapproved_live_tools` stays as the last line of defence in every caller: a tool that still cannot ask (on a server the SDK did not build, which would ignore the flags) is refused.
- **Decisions and trade-offs:** The pause is in the tool server, like mock mode, because that is the one place the model cannot get around. A folder instead of a socket: NAT starts the tool server, not us, and a folder needs no port, token or protocol. Rate limit before approval, so a looping model cannot flood a person with requests. The server expires a request 10 seconds before the tool gives up, so the web app never shows "approved" for a call that timed out. Mock runs never ask.
- **Limits:** Requests are answered one at a time. A run waiting for an answer holds one of the server's two run workers. Inside the sandbox the same folder mechanism runs in the VM and the question crosses to the host over the sandbox's stdin/stdout (F15). Limited mode (`model.reliability.mode: limited`) makes tier-1 tools ask too (F20).
- **Where:** `packages/sdk/src/agentbuilder/approvals.py`, `tools/mcp_server.py` (`_wrap`), `compile/compiler.py` (`needs_approval`, `unapproved_live_tools`), `compile/nat_workflow.py` (`tool_call_timeout`), `server/app.py` (`_Run.ask`, `decide_approval`), `cli.py`, `agentbuilder_nat/local.py`.
- **Proof:** `test_approvals.py` (real MCP client: yes runs the tool, no does not, exact payload seen, files cleaned up, folder 0700, mock never asks, expiry, crashing approver means no, terminal needs an explicit yes, flags only on live SDK servers); server tests (queue, 404/409, expiry, a server the SDK did not build refused); `test_approvals_on_nat.py` on real NAT + Fabric: refused without an approver, runs only after yes [verified].
- **Not verified:** a live tier-2 call against real Google Calendar; the web app's approval screen.
- **Interview angle:** *Why not ask the model to confirm?* The model is the thing that may have been tricked; the check must sit where it cannot reach. *What happens if nobody answers?* After 10 minutes it is a no, and the model is told so.

### F19. The web app and the SDK: who may send the key where
- **Added:** 2026-11-07 · **Status:** done for the wizard's model, tools and test steps (saving agents waits for the control service)
- **What it is:** PLAN §16.13 defines the API between the web app and the SDK server. This entry covers what the plan does not say: how the web app keeps a stored key pointed at the right place, and how the SDK gets the key without a browser session.
- **Why we built it:** The SDK reads `secret://modelcfg/<id>/api_key` from the web vault. If the browser could send any spec, it could pair a stored key with any `base_url` and send that key to a host it was never meant for.
- **How it works:** 1) The browser only calls the web app's own routes (`/api/sdk/...`, `/api/model-configs/{id}/check`). Each one needs a signed-in session and a JSON body, so a cross-site form cannot call it. 2) The web app's server rebuilds the spec's `model` section from the saved model config (`modelFromConfig`): provider, URL, model and the `secret://` reference all come from the database row. 3) It adds the SDK token and forwards the call (`lib/sdk.ts`). 4) When a run or the model check needs the key, the SDK calls `GET /api/internal/secrets/modelcfg/<id>/api_key` with the vault token. The web app checks the token in constant time, accepts only loopback hosts and no browser `Origin`, and then decrypts with the data key of any live, unlocked session of the config's owner (`unlockedKeyFor`). No such session: 423 "the vault is locked". 5) The wizard shows the YAML and warnings the SDK wrote, never its own YAML.
- **Decisions and trade-offs:** The SDK validates and writes YAML; the UI never does, so the two cannot disagree. The spec name is a slug of the typed name (found when the SDK rejected "Inbox helper"), and the typed name stays in `metadata.display_name`. The vault uses any unlocked session of the owner, because the SDK's request carries no cookie.
- **Limits:** Anyone holding the SDK server's token could still call it directly with their own spec (the same limit as F17); the token lives only in `ab ui`'s two processes. Runs are not per user (one-user install). Created agents are not saved yet (control service, P1.6).
- **Where:** `apps/web/src/lib/agent-spec.ts`, `lib/vault.ts`, `lib/sdk.ts`, `lib/sdk-routes.ts`, `app/api/internal/secrets/[...name]/route.ts`, `app/api/sdk/`, `app/api/model-configs/[id]/check/route.ts`, `app/dashboard/new/setup/wizard.tsx`.
- **Proof:** `agent-spec.test.mjs` (model from the saved config, slug, vault names, token check, loopback) [verified]; driven in a browser with a fake model and a fake key: model check through the vault, mock run with trace, live run stopped for approval, Decline kept the tool from running [verified].
- **Not verified:** a real provider through the web app; the vault with two users signed in at once.
- **Interview angle:** *Why rebuild the model on the server?* The browser is the least trusted part; the key must follow the URL it was saved with. *How does a background process get a key that is encrypted with the user's password?* Only while that user has an unlocked session; otherwise it is refused, not guessed.

### F20. One allow/ask/deny rule, proven against a real OPA (compiler D)
- **Added:** 2026-11-07 · **Status:** partial (the Guardrails config is written but not applied at run time)
- **What it is:** PLAN §4.2 says compiler D writes an OPA bundle and a Guardrails config. What the plan does not say: there is ONE Python rule, `tool_decision`, and everything else is derived from it.
- **Why we built it:** Approval rules lived in three places (tool server flags, runner checks, a future OPA). Three copies drift; a policy that says "deny" while the tool server says "allow" is worse than none.
- **How it works:** 1) `tool_decision(compiled, tool)`: tier 3 is deny (or ask under `require_human`), tier 2 is ask (or allow), tier 1 asks only in limited mode, the rest is allow. Mock calls are always allowed; an unlisted tool is always denied. 2) `needs_approval` (and so the tool servers' `--approve` list and every runner) uses it. 3) `to_opa_bundle` writes the decisions as `data.json` plus a fixed `policy.rego` (ask becomes allow only with `approved: true`). 4) A test generates one OPA test per case from the Python rule and runs `opa test` in the official OPA 1.0.0 image: every answer must match. 5) `to_guardrails_config` writes a NeMo Guardrails config per profile (the input check is the floor; standard and strict add the output check).
- **Decisions and trade-offs:** No OPA process in the run path today: the SDK's tool servers enforce the same rule, and OPA is ready for a shared MCP gateway. Guardrails are not applied because the library is not pinned in the lock file (owner's decision), and the compiler keeps warning "NOT applied".
- **Limits:** Guardrails are generated only. OPA is not called at run time.
- **Where:** `compile/compiler.py` (`tool_decision`), `compile/policy_bundle.py`, `compile/guardrails_config.py`, `ab compile --format opa|guardrails`.
- **Proof:** `test_compiler_d.py`: decision table, limited mode reaching the tool server, the bundle matching the rule, OPA parity on three agents (14 cases each) [verified], each profile's config loading in `RailsConfig` [verified].
- **Not verified:** Guardrails rails running against a model.
- **Interview angle:** *Why not write the policy in Rego only?* The tool server must decide without an OPA process; one rule in code, exported to Rego, and a test that makes OPA agree. *What does limited mode change?* A weak model may still draft, but a person checks every change.

### F21. The eval gate: scored from what the agent did, with honest ranges
- **Added:** 2026-11-07 · **Status:** done offline (no real-model suite run yet)
- **What it is:** PLAN §4.4.3 defines the metrics and outcomes. What it does not say: how a case is judged, how small samples are reported, and how the gate is wired to a command.
- **Why we built it:** A model can claim "I used the calculator" and guess. Judging the answer text alone would reward that.
- **How it works:** 1) A suite is YAML data: prompt, expected text or numbers, required tools, tools it must never call (injection cases), or "must abstain". 2) `score_case` checks in a fixed order and gives one plain reason: the run failed, a required tool is missing from the TRAJECTORY, a tool was used for a no-tool question, a forbidden tool was called, it did not abstain, or the answer lacks an expected word or number. 3) Tool names match by namespace (`gmail.read` is `gmail__read`, never `sheets__read`). 4) Rates are reported as k/n with a 95% Wilson range. 5) `decide`: block if any required-tool case was answered without the tool beyond the limit; pass at the publish bar (the spec's `evals.publish_threshold`); pass with limited mode down to 0.70; else block. 6) `ab eval` runs mock tools by default and exits 0, 3 or 1.
- **Decisions and trade-offs:** Cases run one at a time to keep a free tier usable. A guessed answer blocks even when the success rate is high.
- **Limits:** Results are not yet written back to the capability table; no runtime drift watch; built-in suites are small.
- **Where:** `packages/sdk/src/agentbuilder/evals/`, `ab eval`.
- **Proof:** `test_evals.py` (18 tests); `tests/integration/test_eval_on_nat.py`: the calculator suite on real NAT + Fabric with the fake model, 6/7, the guessed case caught, the gate blocked [verified].
- **Not verified:** a suite against a real model (spends money).
- **Interview angle:** *How do you know a tool was really used?* From the run's trajectory, not the answer. *Why ranges?* 6/7 is anywhere from about 49% to 97% at 95% confidence; a percentage alone would mislead.

## Process

### F16. Automatic daily work log
- **Added:** 2026-11-05 · **Status:** done
- **What it is:** A Claude Code `Stop` hook that appends every turn (what was asked, files changed, commits and pushes, the start of the answer) to `work log/<date>/<user>.md`.
- **Why we built it:** Two people work on this repo with AI help; a record of each day's work is automatic instead of remembered.
- **How it works:** The hook reads the transcript from the end, redacts key-shaped text, finds changed files by comparing git state saved in `.git/worklog-state.json`, and never fails the turn.
- **Decisions and trade-offs:** Files are committed, not edited by hand.
- **Limits:** Redaction misses emails and some long hex strings; only the last prompt of a turn is logged.
- **Where:** `.claude/hooks/log_work.py`, `.claude/settings.json`.
- **Proof:** `python -m pytest .claude/hooks`.
- **Not verified:** use by the second contributor.
- **Interview angle:** *How do you keep secrets out of it?* Redaction before writing, plus the rule that keys live only in the git-ignored `.env`.
