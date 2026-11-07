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
| F18 | Safety | One "needs approval" rule for every way of running |

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
- **How it works:** 1) `resolve_credential` reads `env://` from the environment or `secret://` from a store, falling back to `AGENTBUILDER_SECRET_<PATH>`. 2) A value with spaces or line breaks inside is refused with a clear message. 3) The value is held in a `Secret` object that prints as `****`. 4) `redact()` scrubs any text before it is logged or returned. 5) The web app's vault is read by `LocalVaultStore` over loopback (`GET /api/internal/secrets/<name>`), never following redirects.
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
- **Not verified:** any real Google call; the response shapes follow the documented API.
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
- **Not verified:** that repair earns its cost on real models.
- **Interview angle:** *What must a repair never do?* Change meaning. *How do you know it helps?* We do not yet; it is off by default and every use is visible so the rate can be measured.

### F15. SandboxRunner (OpenShell microVM)
- **Added:** 2026-11-07 · **Status:** done for the SDK's own tools
- **What it is:** A second runner that runs the whole agent inside an OpenShell sandbox: a small virtual machine with a generated network allow-list and the model key kept outside.
- **Why we built it:** Local runs trust the agent and its tools with your machine. The sandbox limits the damage if a tool or the model misbehaves.
- **How it works:** 1) Compile, then refuse any tool server that is a program on this machine (only the SDK's own servers exist in the image). 2) Write the policy (compiler C) and the model's provider profile. 3) Create a per-run OpenShell provider holding the key, passing the key through the environment of that one command, never the command line. 4) Create the sandbox from the image with that provider, `--no-keep`, and run `python -m agentbuilder_nat.sandbox_main`. The compiled agent and the prompt (no key inside) go in as one JSON line on standard input, not as an argument, because arguments show in `ps` for every user of the machine. 5) Inside, `LocalRunner` runs as usual; the agent only sees a placeholder, and the sandbox proxy adds the real key to requests for the model host only. 6) The host reads one `AGENTBUILDER_RESULT` line, then always deletes the provider (and the sandbox after a failure or timeout). 7) Each run first deletes per-run providers older than the run timeout: names are `ab-<start time>-<4 hex>`, so a provider left by a killed run is found and removed, while one belonging to a run still going is left alone.
- **Decisions and trade-offs:** Reuse `LocalRunner` inside the VM so there is one agent code path. The SDK is installed into the image's site-packages because the VM driver ignores image environment settings and tool servers start with a cleaned environment. Things found only on the real gateway: profiles are global by id, so a non-default port is part of the id; sandbox names may be at most 19 characters; OpenShell forwards standard input but never closes it, so the reader takes exactly one line.
- **Limits:** Only the SDK's tool servers; the audit log is not collected; a provider left by a killed run holds the key until the next sandbox run sweeps it.
- **Where:** `packages/sdk-nat/src/agentbuilder_nat/sandbox.py`, `sandbox_main.py`, `packages/sdk-nat/sandbox/Dockerfile`, `make sandbox-image-sdk`.
- **Proof:** 9 tests, 8 without a real sandbox (key never in argv, prompt only on stdin, provider sweep, names within 19 characters); on a real microVM the agent succeeded with a mock Gmail tool and a fake model reached through `host.openshell.internal`, the key appeared nowhere in the result, and no per-run provider remained [verified].
- **Not verified:** the proxy injecting the real key in this runner (proven in the earlier spike with the owner's key, not re-run here); a real model.
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

### F18. One "needs approval" rule for every way of running
- **Added:** 2026-11-07 · **Status:** done until approvals exist (SDK 0.3)
- **What it is:** PLAN says tier-2 actions wait for a human (approval queue, SDK 0.3). Until that exists we went further than "warn": every way of running refuses a live tier-2 tool. The plan does not describe this interim guard.
- **Why we built it:** At first only the server refused; `ab run` and both runners accepted the same live run, so the rule depended on which door you used.
- **How it works:** 1) `unapproved_live_tools(compiled)` lists tools that are tier 2 with `tier2_external_comms: require_human` (or tier 3 with `tier3_destructive: require_human`) and whose server is not in mock mode. 2) The server (422), `ab run` (exit 1, before any runner starts), `LocalRunner` and `SandboxRunner` (failed result, nothing started, no provider created) all call it. 3) Mock runs and `tier2_external_comms: allow` pass.
- **Decisions and trade-offs:** Refuse rather than act unasked. The check reads only the compiled agent, so the runners stay safe even if a new caller forgets it.
- **Limits:** It is a blanket refusal; real per-action approvals are SDK 0.3.
- **Where:** `compile/compiler.py` (`unapproved_live_tools`, `approval_needed`), `server/app.py`, `cli.py`, `agentbuilder_nat/local.py`, `agentbuilder_nat/sandbox.py`.
- **Proof:** tests for the function, the server (mutation-checked), the CLI, and both runners [verified].
- **Not verified:** none for this part.
- **Interview angle:** *Why check in the runner too?* Defence in depth: the last line before anything acts. *What is prompt injection here?* A mail the agent reads could ask it to create an event with private data in the title; tier-2 tools are exactly the ones that contact other people.

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
