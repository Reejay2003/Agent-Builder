# Agent Builder Platform: Master Plan (v8)

Last updated: 2026-10-08. Personal open-source project on GitHub. No revenue, no funding, so **everything must be free or open source** (section 3).

Tags used for facts:
- **[verified]**: read in NVIDIA docs or repos during this planning session
- **[secondary]**: from third-party articles, re-check against NVIDIA docs
- **[memory]**: from my background knowledge, not checked this session; confirm before adopting

## 0. Changes

### v8
1. **New section 4.3: the LLM layer** (gateway, model routing, agent mode). Evidence from S2b: our NAT ReAct agent failed about half its runs on free models with `ReActAgentParsingFailedError` (model replied in the wrong text format, or returned nothing). Plain NAT failed the same way, so it is a model/agent-type problem, not a NAT-Fabric incompatibility. A gateway cannot repair that.
2. **Native tool calling becomes the default agent mode; ReAct is the fallback** for models without function calling (small local models). The AgentSpec gains `model.agent_mode: auto | tool_calling | react` and a capability tier; compiler A picks the NAT workflow type from it. NAT ships `tool_calling_agent` **[verified: used in its `examples/agents/tool_calling` config]**; the Fabric NAT adapter only supports `react_agent` today **[verified in its README]**, so S14 checks whether a tool-calling target is feasible or we write our own adapter target.
3. **NeMo Switchyard (NVIDIA, Apache-2.0, pre-1.0, v0.3.0 on PyPI as `nemo-switchyard`)** evaluated as an **optional model-routing layer**, not the default gateway and not a format fixer **[verified: README and NVIDIA blog]**. See 4.3 for what it is, its limits and why.
4. **Default gateway:** keep the OpenAI-compatible BYOK interface; OpenRouter or LiteLLM (MIT **[verified on PyPI]**) behind it. OpenShell already holds the key and routes inference, so the gateway sits on the host side of that boundary.
5. **New spike S14** (tool calling across models through Fabric, plus a Switchyard trial); BOM, risks, ADR list and links updated. Also: the OpenRouter free tier is 50 requests a day **[verified: HTTP 429 response]**, so Evals-phase work needs paid credits or local models.

### v7
1. **`pgvector_lite` is now the default retrieval engine; NeMo Retriever is optional.** The dev machine is a Mac with no NVIDIA GPU, and NeMo Retriever's local inference needs one (hosted endpoints are dev/test only, section 3.4). The zero-spend path must work out of the box. NeMo Retriever stays a selectable engine (`--profile gpu`, or hosted endpoint for prototyping). Wherever v6 text below says NeMo Retriever is the default, read it as optional.
2. **Docker is the packaging model** (section 3.5): one image per service, pinned versions, Compose profiles. Starter stack (Postgres+pgvector, Valkey) is in `deploy/compose/` and verified running.

### v6
1. **NeMo Retriever library replaces our hand-built ingestion, embedding and retrieval pipeline** as the default engine of the Knowledge layer (section 8.12). It is Apache-2.0 and open source, does extraction (text, tables, charts, OCR), embedding and retrieval, and has a RAG example plus LangChain and LlamaIndex integrations **[verified: GitHub README, 26.08 release]**.
2. **What it does NOT replace:** tenant scope, the confirmed-facts store, FAQ cards, memory, citations policy, confidence/abstention, and the MCP tools. Those stay ours, wrapped around it.
3. **Caveats found, which shape the design:** its documented vector store is LanceDB (Milvus via an extra profile), **not pgvector**; local inference needs an NVIDIA GPU (no CPU-only path is documented), and the no-GPU route is NVIDIA's hosted endpoints, which are dev/test only (section 3.4); the default embedding model has its own licence (OpenMDW); no reranker is mentioned. So the Knowledge service gets a **`RetrievalEngine` interface** with two backends: NeMo Retriever (default when a GPU or hosted key is available) and a lite pgvector backend (the zero-GPU fallback). S9 and S10 decide the default.
4. Spikes S9 and S10 rewritten; new spike S13 (multi-tenancy on NeMo Retriever's store); BOM, architecture, repo layout, risks and links updated.

### v5
1. **New section 7: the Integration layer.** A support agent needs the company's customer and order database and its ticketing tool; a recruiting agent needs the applicant pool and must show the HR person a candidate's profile. Knowledge (section 8) only covered documents. Connectors now turn a user's own **database, spreadsheets, REST/OpenAPI, existing MCP servers, business apps and folders** into typed, risk-tiered tools, with no code.
2. **Entity mapping in the wizard** ("which table holds customers? which column is the email?") produces a confirmed *semantic model*, and tools are generated from it. Free-form SQL is off by default and guarded when on. Writes exist only as user-defined, tiered **actions**.
3. **Record viewer and human review queues**: one UI component renders any mapped record (candidate, customer, order, ticket) with its sources, used in the test step, the approval queue, and the recruiting shortlist review. This is how "no automatic rejection" (section 8.11) is actually enforced.
4. **Channels and triggers** (section 7.9): web chat, email inbox, webhook, folder watch, schedule, voice. Without these an agent can only be used from the test console.
5. **Test mode never touches live systems:** synthetic demo datasets per template, snapshot copies of connected tables, recorded mocks.
6. Wizard step 4 becomes "Connect systems and accounts"; AgentSpec gains `integrations:` and `channels:`; compiler F; new Phase 3 (Integrations v1) and spikes S11, S12; BOM lists free connector libraries and the non-open-source tools to avoid as dependencies (n8n, Airbyte).

### v4
1. **New section 8: the Knowledge layer.** Customer-support, recruiting, job-applying and caller agents all need correct, citable information, so RAG is now a first-class part of the design rather than a tool you bolt on later.
2. **Key design decision: RAG alone is not enough.** Exact facts about a person or record (an email address, employment dates, an order status) come from a **confirmed structured store**, not from similarity search. RAG covers narrative content; a memory store covers preferences and history (section 8.1).
3. The wizard gains an **Add knowledge** step, the AgentSpec gains a `knowledge:` block, the roadmap gains a Knowledge phase, and two new spikes (S9, S10) test it.
4. Knowledge access is a normal MCP tool call, so it inherits the existing risk tiers, OPA checks, sandbox policy and traces. Tenant scope is injected by the gateway, never supplied by the agent.

### v3
1. **NeMo Agent Toolkit (NAT) is now the agent-building layer.** Fabric's adapter docs name NAT as the reference "shared framework adapter" **[verified]**, so the intended path is NAT builds the agent, Fabric runs it.
2. **OpenShell is now part of the runtime plane**, not a separate plane. This matches how NemoClaw is built (OpenShell owns provisioning, policy and containment; Fabric runs inside the sandbox) **[verified]**.
3. **Free-only constraint** drives a local-first design, pluggable providers, and a bill of materials with licences (section 3).
4. Corrected claims: NeMo Evaluator's fit for agent *trajectories* is unconfirmed (section 11), and Riva is not free for production without conditions (section 9).

## 1. Reality check before building

### 1.1 NeMo Helix overlaps with this product
NVIDIA's Fabric ecosystem page lists **NeMo Helix** as a platform for building, deploying, evaluating and improving agents; it translates agent definitions into Fabric configuration and Fabric runs the harness **[verified]**. Not checked: whether Helix is self-hostable, free, no-code, or supports BYOK.

**Implication:** the defensible part of this project is the **guided, non-technical experience** (BYOK, templates, risk-tiered tool basket, no-code connection of your own data and systems, safe defaults), not the plumbing. Spike S5 decides whether to build on Helix, borrow ideas, or ignore it.

### 1.2 Maturity of the stack
| Component | Version seen | Status |
|---|---|---|
| NeMo Agent Toolkit | README mentions 1.5.0; docs index lists versions up to 1.8 | Apache-2.0, `pip install nvidia-nat`, Python 3.11 to 3.13 **[verified]**. Pin an exact version in S1 |
| NeMo Fabric | v0.4.0 | Rust core, Python SDK, CLI, adapter contract **[verified]** |
| NeMo Relay | v0.9.4 (v0.10.0 on dev docs) | Scopes, middleware, plugins, ATOF/ATIF/OTel **[verified]** |
| OpenShell | 0.1, launched 2026-09-28 | Apache-2.0 sandbox runtime **[secondary]** |
| NemoClaw | "being hardened for release" | Open-source reference stack: Fabric inside OpenShell **[verified]** |

Everything is early (0.x). **Rule: your own AgentSpec is the stable layer. NVIDIA pieces sit behind adapters you own, with pinned versions.**

## 2. Product definition

A guided builder where a non-technical person builds, tests and (later) deploys an agent.

Wizard steps:
1. **Connect LLM** (BYOK): any OpenAI-compatible endpoint (OpenAI, Anthropic via compatible gateway, NVIDIA hosted, local Ollama). Validate with a test call, store encrypted, never return it to the browser.
2. **Choose agent type** (template gallery, 2.1).
3. **Tool basket**: catalog filtered by agent type, recommended tools pre-ticked, plain-language description of what each can read or change, risk tier.
4. **Connect systems and accounts** (section 7): OAuth for Gmail, Calendar and so on; the company's own database, spreadsheets, ticketing, CRM or ATS through connectors. The wizard introspects the source, proposes an entity mapping ("which table holds customers? which column is the email?"), the user confirms it, and typed lookup tools are generated. The user also picks how the agent is reached: web chat, email inbox, webhook, folder watch, schedule (section 7.9).
5. **Add knowledge** (section 8): upload files, paste URLs, or connect the user's own Drive; see a parse preview; **confirm the facts extracted about a person or business** (for example the fields parsed from a resume); try sample questions and see which sources were used.
6. **Configure**: persona, instructions, guardrail strictness. Platform floor cannot be turned off.
7. **Test in sandbox**: mock or dry-run tools, full trace visible, including retrieved sources. Connectors run against a synthetic demo dataset or a snapshot copy, never the live system; a **record viewer** shows exactly which customer, order or candidate the agent looked at.
8. **Evaluate**: auto-generated suite (tools, retrieval, grounding), pass or fail.
9. **Publish**: gated on step 8. Deployment targets come later.

### 2.1 Agent-type templates
Each template = default instructions + recommended tools + guardrail profile + eval suite + sandbox policy preset + risk rules.

| Template | Typical tools | Systems of record (section 7) | Channels (section 7.9) | Order |
|---|---|---|---|---|
| Personal automation (email triage, calendar, reminders, daily brief) | Gmail, Calendar, Sheets, Drive, web search | User's own Google account only | Schedule, email, chat | **1st (MVP)** |
| Customer support | KB search, ticketing, order lookup, draft reply | Customer and order database (read-only), ticketing tool, product KB | Web chat widget, email inbox, ticketing webhook | 2nd |
| Research / analyst | web search, fetch, doc writer | Uploaded documents, optional database export | Chat, schedule | 2nd |
| Ops / workflow | Sheets, forms, helpdesk | Spreadsheets, internal databases, helpdesk | Webhook, schedule, chat | 3rd |
| Sales / SDR | CRM, enrichment, email drafts | CRM (self-hosted or user's own) | Chat, schedule, CRM webhook | 3rd |
| Recruiting | resume parsing, candidate profile, scheduling, shortlist review | ATS or watched resume folder or inbox, requisition sheet, calendar | Folder watch, inbox, ATS webhook; human review queue | 3rd |
| **Caller agent (voice)** | speech, telephony, calendar, CRM, human transfer | Business info, bookings, CRM | Voice (WebRTC, optional SIP) | **Last, own sub-platform (section 9)** |

The "Systems of record" column is what the Integration layer connects; the "Channels" column is how a run starts. Both are configured in wizard step 4.

## 3. Free and open-source constraint

### 3.1 Principles
- **Local-first.** The product ships as a GitHub repo you run with `docker compose up` on your own machine. No hosted SaaS, no managed cloud, no GPU rental. Users bring their own LLM key (BYOK) or run a local model.
- **Every paid or gated thing is an optional provider behind an interface**, never a hard dependency. The default path must work with zero spend.
- **No "free data center" exists for a real service.** I have not verified any free hosting offer worth committing to. If you want a public demo later, treat it as a separate decision with its own cost; the plan does not depend on one.

### 3.2 Bill of materials
| Need | Default (free) | Licence / terms | Notes |
|---|---|---|---|
| Agent building | NeMo Agent Toolkit | Apache-2.0 **[verified]** | No GPU needed. Hello World uses a NVIDIA hosted model key, but it is framework-agnostic; confirm BYOK with OpenAI-compatible endpoints in S2 |
| Execution contract | NeMo Fabric | Repo is public; **licence not read** | Docs have OSS and licence pages; read before adopting |
| Telemetry | NeMo Relay | **Licence not read** | Same: read licence page |
| Sandbox | NVIDIA OpenShell | Apache-2.0 **[secondary]** | Needs Docker (runs K3s inside one container); OS and hardware requirements are on its Support Matrix page, not read yet |
| Guardrails | NeMo Guardrails | Apache-2.0 **[memory]** | Self-hosted Python library |
| Evals | NAT built-in eval + NeMo Evaluator + garak | Evaluator Apache-2.0 **[verified]**; garak Apache-2.0 **[memory]** | Evaluator needs Docker for code sandboxes; no GPU or Kubernetes mentioned |
| LLM | User's own key, or **Ollama** local models | Ollama MIT **[memory]** | OpenShell's community catalog lists an `ollama` sandbox **[secondary]**. Small local models make weak agents; expect that |
| LLM gateway (optional, behind the BYOK interface) | OpenRouter (hosted) or **LiteLLM** (self-hosted) | LiteLLM MIT **[verified on PyPI]**; OpenRouter is a service with a free tier of 50 requests/day **[verified]** | One OpenAI-style API over many providers, retries, fallbacks, usage tracking. Does not fix wrong output formats |
| Model routing (optional, later) | **NeMo Switchyard** (`nemo-switchyard` 0.3.0) | Apache-2.0 **[verified]**; pre-1.0, APIs may change | Cost/quality routing across models. Its standalone server is labelled demo, not for production; LiteLLM integration is experimental. See 4.3 |
| Hosted LLM for dev | build.nvidia.com free endpoints | Prototyping only: rate-limited, credit amounts not stated, "trial experience", production serving needs AI Enterprise **[verified]** | Fine for development, not a foundation |
| Authorization | OPA | Apache-2.0 **[memory]** | OpenShell also compiles its YAML policies to OPA/Rego **[secondary]** |
| Login | Keycloak (or simple local auth for MVP) | Apache-2.0 **[memory]** | MVP can start with a single local user |
| Secrets | **OpenBao** or SOPS+age | MPL-2.0 / open **[memory]** | HashiCorp Vault moved to BUSL, so it is not open source |
| DB / cache | Postgres + pgvector; **Valkey** instead of Redis | PostgreSQL licence; BSD **[memory]** | Redis changed licences, so use Valkey |
| Backend / UI | FastAPI, Next.js, shadcn/ui | MIT **[memory]** | |
| Traces UI | Jaeger or Grafana Tempo via OTel | Apache-2.0 / AGPL **[memory]** | Phoenix is Elastic License, not OSI open source **[memory]**, so avoid |
| Ingestion + embedding + retrieval engine | **NeMo Retriever library** (extraction, embed, retrieve) | Apache-2.0 **[verified]**; default embedding model under OpenMDW **[verified]**; Adobe pdfservices-sdk optional with its own terms | Default store LanceDB (in-process); Milvus via extra profile **[verified]**. Needs an NVIDIA GPU for local inference, or NVIDIA hosted endpoints (dev/test licence only). Pin version (26.8.1 seen) |
| Fallback (no GPU) vector + keyword search | pgvector + Postgres full-text search | PostgreSQL licence **[memory]** | The "lite" `RetrievalEngine` backend; one database, no GPU. Qdrant or Milvus (Apache-2.0 **[memory]**) only if scale demands it |
| Embeddings | NeMo Retriever's embedding step (Nemotron models) on a GPU or hosted endpoint; **lite fallback:** open-weights model on CPU (Ollama or sentence-transformers) | Varies per model **[memory]**; check each model's licence | Nemotron models are open weights; licence terms to be read in S7 **[verified: exist, terms unread]** |
| Reranking | Optional open cross-encoder | Varies per model **[memory]** | Optional: Nemotron reranking models (same caveats) **[verified]** |
| Document parsing | **NeMo Retriever library** (pages, tables, charts, infographics, OCR) | Apache-2.0 **[verified]** | Lite fallback: Docling or pypdf, Tesseract for OCR (MIT / Apache-2.0 **[memory]**) |
| PII scanning at ingestion | Presidio | MIT **[memory]** | Relay's PII-redaction plugin works on event streams, not on stored documents |
| RAG evals | Ragas or own LLM-judge | Apache-2.0 **[memory]** | Whether NAT eval or NeMo Evaluator offers RAG metrics is unconfirmed (S10) |
| Voice (optional) | Pipecat or LiveKit + open ASR/TTS | BSD / Apache-2.0 **[memory]** | NVIDIA speech is an optional provider (section 9) |
| Database connectors | SQLAlchemy + drivers (psycopg, PyMySQL, sqlite3; pymssql or pyodbc for SQL Server) | MIT / LGPL / BSD / MIT **[memory]** | Read-only database user enforced by a privilege check at connect time (section 7.3) |
| Spreadsheet / CSV import | openpyxl, pandas or DuckDB for one-off imports into Postgres | MIT **[memory]** | Google Sheets via the user's own OAuth |
| OpenAPI to tools | FastMCP `from_openapi` or an openapi-to-MCP generator | Apache-2.0 / MIT **[memory]**; confirm in S12 | Always wrapped in our platform manifest so tiers and egress are ours |
| Bring-your-own MCP server | MCP spec (open), proxied by the gateway | Open spec | Each tool gets a manifest with a user-assigned risk tier |
| Demo business apps (optional, heavy) | Zammad or FreeScout (helpdesk), Twenty or EspoCRM (CRM), OpenCATS (ATS), Nextcloud (files) | AGPL-3.0 / GPL **[memory]** | Separate processes reached over their HTTP APIs, so their licences do not touch our code; `docker compose --profile demo-apps`. Default demo path is a seeded Postgres with synthetic data instead |
| Web chat widget | Own embeddable widget (vanilla JS or Preact) + FastAPI websocket | MIT | Small; avoids pulling in a whole helpdesk product as a dependency |
| Email channel | Gmail API via user's OAuth, or IMAP/SMTP (imaplib, aiosmtplib) | Stdlib / MIT **[memory]** | Polling, no paid email API |
| Scheduler | APScheduler or Postgres-backed cron table | MIT **[memory]** | No external queue service |
| **Do not build on** | n8n (Sustainable Use licence), Airbyte (ELv2), Chatwoot (MIT core but heavy Rails stack) | Not OSI open source (first two) **[memory]** | Fine as systems a *user* connects to via OpenAPI/webhooks, not as platform dependencies |

### 3.3 Compute ladder (cheapest first)
1. **Your laptop or desktop with Docker.** Runs NAT, Fabric, Relay, OpenShell, Postgres, UI. No GPU.
2. **LLM:** your own key, or Ollama locally, or NVIDIA's free hosted endpoints for prototyping.
3. **GPU work (self-hosted speech, big local models):** only if you own an NVIDIA GPU. NVIDIA's free Developer Program allows self-hosting NIMs for research, development and testing on up to 16 GPUs **[verified]**, but that licence is not for production use. Free notebook GPUs (Colab, Kaggle) are fine for experiments only; quotas change **[memory]**.
4. **Anything beyond that costs money.** Mark it out of scope.

### 3.5 Docker and versioning
- One `Dockerfile` per service (control, runner, mcp-gateway, knowledge, connectors, channels, web), so services can use different Python or library versions without conflict.
- Pin exact base images (never `latest`) and lock dependencies (`uv.lock` or hashed requirements). Keep NVIDIA component versions (NAT, Fabric, Relay, Retriever) in one place.
- Compose lives in `deploy/compose/`. Core stack: Postgres+pgvector, Valkey, services. Profiles: `gpu` (NeMo Retriever), `demo-apps`, `voice`. Config in `.env` (git-ignored), template in `.env.example`.
- Healthchecks on every container (feeds `doctor`), named volumes for data, non-root users, ports bound to 127.0.0.1.
- Run: `docker compose -f deploy/compose/docker-compose.yml --env-file .env up -d`.
- Later: GitHub Actions to build and test images, publish to ghcr.io (free).

### 3.4 Licence trap to avoid
NVIDIA's free tiers are **research, development and test** licences; production serving needs NVIDIA AI Enterprise **[verified]**. Because this is an open-source repo others will clone, keep NVIDIA-gated services (NIMs, Riva) as optional providers and document that whoever deploys them for real use owns the licence question.

## 4. Architecture: planes and owners

| Plane | Responsibility | Built with |
|---|---|---|
| Experience | Wizard UI | Next.js, shadcn/ui |
| Control | Tenants, auth, AgentSpecs, tool catalog, **policy compiler**, secrets refs | FastAPI, Postgres, Keycloak/local auth, OPA |
| Context | **Knowledge service** (RAG via NeMo Retriever, confirmed-facts store, FAQ cards, memory), secrets, per-agent state; details in section 8 | NeMo Retriever (LanceDB or Milvus), Postgres for facts/FAQ/memory (+ pgvector in lite mode), Valkey, OpenBao/SOPS |
| Integration | **Connector service** (databases, sheets, OpenAPI, bring-your-own MCP, app packs, folders), semantic models, generated tools, **channels and triggers**; details in section 7 | FastAPI, SQLAlchemy, OpenAPI-to-MCP generator, webhook receiver, email poller, scheduler |
| **Runtime** | Agent definition, execution, containment (three layers, below) | **NAT + Fabric + OpenShell** |
| Guardrails | Content and behaviour rails | NeMo Guardrails (+ NemoGuard models if available free) |
| Authorization | Per-tool-call allow or deny | OPA, plus OpenShell's compiled policies |
| Telemetry and eval | Lifecycle events, traces, trajectories, scoring, red-team | Relay, NAT eval, Evaluator, garak |
| Voice (Phase 7) | Realtime speech and telephony | Pipecat/LiveKit + open ASR/TTS, optional NVIDIA speech |

### 4.1 Runtime plane in detail
```
Layer 1  NAT           defines the agent: workflow YAML, LLM, tools (MCP client), memory
Layer 2  Fabric        execution contract: FabricConfig, plan + doctor, run, RunResult
                        (NAT is wired in as the "shared framework adapter")
Layer 3  OpenShell     containment: one sandbox per run/session, YAML policy, credentials
                        held outside the sandbox, egress through the policy engine
```
Fabric and NAT run **inside** the OpenShell sandbox. The control plane **writes** the sandbox policy; OpenShell **enforces** it. This split keeps the policy compiler in your code (testable, versioned) and enforcement in a component that the agent cannot override.

### 4.2 End-to-end pipeline
```
Wizard answers -> AgentSpec (versioned YAML/JSON in Postgres)
   -> compiler A: NAT workflow YAML   (agent, LLM ref, tools via MCP, workflow type from model.agent_mode)
   -> compiler B: FabricConfig        (NAT adapter target, MCP, telemetry via Relay)
   -> compiler C: OpenShell policy    (egress hosts, paths, process rules per tool)
   -> compiler D: OPA bundle + Guardrails config
   -> compiler E: knowledge config    (collections, retrieval settings, profile schema, gateway scope rules)
   -> compiler F: integration config  (connector routes, semantic model, generated tool manifests, action tiers, channel bindings)
   -> Fabric plan + doctor (pre-flight) -> run inside OpenShell sandbox
   -> Relay events (ATOF) -> ATIF trajectories -> eval + trace UI
```

### 4.3 The LLM layer: gateway, routing and agent mode
The platform must run with many kinds of models, so model differences are handled in three separate places. Mixing them up is what made the parsing error look like a gateway problem.

| Problem | Where it is fixed | Tool |
|---|---|---|
| Different provider APIs, keys, retries, fallbacks, rate limits, usage | **Gateway** | OpenRouter or LiteLLM behind our OpenAI-compatible BYOK interface; the key stays outside the sandbox (OpenShell provider, S3) |
| Which model should serve which step (cost vs quality) | **Model routing**, optional | NeMo Switchyard (below) |
| The model answers in the wrong shape (ReAct text that will not parse) | **Agent mode** | Native tool calling by default; ReAct only as fallback; output repair; eval gate |

**Agent mode (the real fix for the S2b failures).** `model.agent_mode: auto` resolves from a capability table kept in `packages/model-capabilities/` (does the model support function calling, streaming, JSON mode, context size, a reliability tier from our evals). `tool_calling` is used when supported, `react` otherwise. Compiler A emits the matching NAT workflow type. If a model is too weak for a template, the wizard says so before the user builds on it. On a parse failure the runner resends the format error once; repeated failures are reported, not hidden.

**NeMo Switchyard: what it is and how we would use it** **[verified: github.com/NVIDIA-NeMo/Switchyard and the NVIDIA blog]**
- An open-source layer that routes each step of an agent to a model. It keeps routing logic separate from provider endpoints (semantic model names map to provider endpoints and model IDs), exposes OpenAI, Anthropic and Responses-compatible endpoints, and logs the chosen model, rationale, tokens, latency and outcome.
- Routers: LLM classifier (a judge picks the model, with session affinity), stage router (reads recent tool activity), escalation router (start cheap, move to a stronger model when the session struggles), and a tunable prefill router. `nvidia/switchyard` is the model name clients send for automatic routing.
- Integrations: gateway use, local proxy, embedding in your own harness, a **NeMo Relay plugin** (needs Relay `>=0.8.0, <1.0.0`; Relay 0.8.x and 0.9.0 can lose upstream error status when the plugin is enabled) and a LiteLLM plugin.
- **Limits that decide our use of it:** pre-1.0 (APIs and routing behaviour can change); `switchyard-server` is marked demo, not for production; the LiteLLM route is experimental and cannot serve classifier or escalation algorithms; tool-call and streaming translation between the OpenAI and Anthropic dialects is not described, so it is not a proven format translator; it needs Python plus a Rust toolchain for some paths; the savings figures in the blog are vendor or partner reported (for example LangChain's 74% cost reduction on 145 tasks) and not independently verified; its README itself says a cheaper call does not guarantee a cheaper completed task. NAT, Fabric and OpenShell integration is not mentioned.
- **Decision:** not in the MVP path. We add it behind our gateway interface as an optional **routing provider** for users with several models or paid keys, after S14 shows what it does for our agents. A user with one free model gains nothing from it. It is a good fit later for the escalation pattern (small model first, strong model when stuck), which also helps the free-model quality problem.
- Fit with the stack: Relay is already our telemetry layer, so its plugin is the natural attachment point, but the version range and the error-status caveat must be tested against our pinned Relay (S4, S14).

**Free-tier reality:** OpenRouter's free tier is 50 requests a day **[verified]**; 10 credits unlock 1000 free-model requests a day. Local Ollama models have no quota but are weak tool callers. Eval runs (Phase 5) need either credits or a local model with a stated quality floor.

## 5. The AgentSpec (the one stable contract)
```yaml
spec_version: 1
id: agt_01...
type: personal_automation
model:
  provider: openai_compatible          # openai | nvidia_hosted | ollama | any compatible URL
  base_url: https://api.openai.com/v1
  model: gpt-...
  credential_ref: secret://llm/primary # never the key itself
  agent_mode: auto                     # auto | tool_calling | react; auto reads packages/model-capabilities
  capability_tier: standard            # filled from the capability table / evals; the wizard warns on weak tiers
  routing: null                        # optional: { provider: switchyard, algorithm: escalation, models: [...] }
instructions: { persona: "...", rules: ["..."] }
tools: [ {id: gmail.read}, {id: gmail.send_draft}, {id: calendar.create_event} ]
knowledge:                             # section 8; omit for agents that need none
  collections: [kb_support_docs]       # the only collections this agent may search
  retrieval: { mode: hybrid, top_k: 5, rerank: false, min_score: 0.35, require_citations: true }
  faq_first: true                      # exact pinned answers before semantic search
  profile_schema: candidate_v1         # structured, user-confirmed facts (null if unused)
  memory: { enabled: false }
  freshness: { max_age_days: 90 }
integrations:                          # section 7; systems of record, credentials by reference only
  - id: shop_db
    type: database                     # database | sheet | openapi | mcp_server | app_pack | folder
    credential_ref: secret://int/shop_db   # read-only DB user, privilege-checked at connect time
    semantic_model: support_v1         # user-confirmed entity mapping: customer, order, ticket
    expose: [customer.find, order.get, order.list_recent]   # generated Tier 0 lookup tools
    actions:                           # the ONLY write path; each is explicit and tiered
      - { id: ticket.create, tier: 1 }
      - { id: order.refund, tier: 3, enabled: false }
    free_query: { enabled: false }     # guarded read-only NL->SQL, off by default
    sync_to_knowledge: [ {entity: kb_article, collection: kb_support_docs} ]
    test_data: snapshot                # synthetic | snapshot | mock; never live in test mode
channels:                              # section 7.9; how runs start
  - { type: web_chat, auth: anonymous, rate_limit: 30/min }
  - { type: webhook, source: shop_db.ticket.created }
  - { type: schedule, cron: "0 8 * * *", enabled: false }
guardrails: { profile: standard }      # strict | standard | relaxed, floor enforced
approvals: { tier2_external_comms: require_human }
sandbox: { policy_preset: personal_automation_v1 }
voice: null                            # caller agents only
evals: { suite: personal_automation_v1, publish_threshold: 0.85 }
```
Rules: versioned, JSON-Schema validated, credentials by reference only, and the UI, compilers, evals and deployment all read this and nothing else.

## 6. Tool library and MCP gateway
- Wrap existing open-source or vendor MCP servers; add a **platform manifest** per tool: `id, description_plain, scopes, side_effects, risk_tier, creds_required, egress_hosts, fs_paths, rate_limits, mock_response`.
- **Two sources of tools:** hand-written manifests for prebuilt tools (Gmail, Calendar, web search), and **generated** manifests from connectors (section 7), which turn a user's own database, spreadsheet or API into tools without code. Both go through the same gateway, tiers and policy compilers.
- NAT acts as the MCP client (it can integrate MCP tools and also serve agents as an MCP server) **[verified]**. One gateway exposes only the basket's tools per agent.
- **Risk tiers:** 0 read-only, 1 reversible write, 2 external communication (human approval by default), 3 destructive or financial (blocked by default).
- Each tool's `egress_hosts` and `fs_paths` feed the generated OpenShell policy, so adding a tool to the basket automatically widens the sandbox just enough, and nothing else.
- Free tool backends only: prefer self-hostable or free-tier APIs (Gmail, Calendar, Sheets via the user's own Google account; open web search such as SearXNG **[memory]**).

## 7. Integration layer: connecting the user's own systems

### 7.1 Why this is its own layer
Section 8 covers documents. Most real agents also need the **system of record**: a support agent needs the company's customer and order database and its ticketing tool; a recruiting agent needs the applicant pool (an ATS, a shared folder, an inbox) and must show the human a candidate's full profile; a sales agent needs the CRM. Tools (section 6) are the agent-facing end of this. **Connectors are the system-facing end:** one connector turns one external system into a set of typed, risk-tiered MCP tools, plus an optional sync into a knowledge collection.

The non-technical user never writes SQL, API calls or tool code. They connect a source, confirm a mapping, and tools appear in the basket.

### 7.2 Connector types
| Connector | What the user supplies | What it produces | Free default |
|---|---|---|---|
| **Database** (Postgres, MySQL/MariaDB, SQLite, SQL Server) | Connection string for a **read-only** DB user; the wizard checks the privileges and refuses or warns otherwise | Schema introspection, entity mapping, generated typed lookup tools (`customer.find`, `order.get`); writes only via user-defined actions | SQLAlchemy **[memory, MIT]** |
| **Spreadsheet / CSV** | Google Sheets via OAuth, or CSV/XLSX upload | Imported into a managed table in platform Postgres, then treated like a database connector; re-sync on schedule | Own code |
| **REST API (OpenAPI)** | OpenAPI/Swagger URL or file, plus auth (API key, bearer, OAuth2) | One tool per operation; GET defaults to Tier 0, POST/PUT/PATCH to Tier 1 or 2, DELETE to Tier 3; the user hides operations they do not want | FastMCP `from_openapi` or similar **[memory]**, behind our manifest |
| **Existing MCP server** | URL or command of a server the user already runs | Proxied through the gateway; each tool wrapped in a platform manifest with a user-assigned tier | MCP is an open spec |
| **SaaS accounts (OAuth)** | Google (Gmail, Calendar, Drive, Sheets), GitHub, Slack or Discord free tiers | Prebuilt manifests; this is the old "Connect accounts" step | User's own accounts |
| **App packs** | A self-hosted open-source app: helpdesk (Zammad, FreeScout), CRM (Twenty, EspoCRM), ATS (OpenCATS), files (Nextcloud), wiki (BookStack, Wiki.js) **[memory; all AGPL/GPL/MIT]** | A curated pack: manifests, semantic model, webhook subscriptions, knowledge sync. Built on top of the OpenAPI connector | Separate processes over HTTP, so AGPL does not touch our code |
| **Files and folders** | A folder on the host, Nextcloud, or Drive | Watched for new files (resumes arriving), ingested into knowledge (section 8) and exposed as `files.list` / `files.get` | Own worker |
| **Webhooks / events (inbound)** | A URL the external system calls (new ticket, new application, new row) | Starts a run (section 7.9) with the event as input | Own code |

### 7.3 From connection to tools: the mapping step in the wizard
1. **Connect.** Credential stored by reference (OpenBao or SOPS), test the connection, **privilege check**: a database connector wants a read-only user. If the credentials can write, the wizard says so and either asks for a read-only user or tiers every generated tool accordingly.
2. **Introspect.** Tables and columns (sample rows shown only to the user, never stored), endpoints, folders.
3. **Map to entities.** The template proposes a mapping from the schema to its entities: *"Which table holds customers? Which column is the customer email? Which table holds orders and how does it link to customers?"* The user confirms or fixes it. The result is a **semantic model**: entity, key fields, display fields, PII-labelled fields, allowed filters, joins. Schemas per template live in `packages/semantic-models/` (customer, order, ticket, candidate, requisition, booking).
4. **Generate tools.** From the semantic model, typed lookup tools with fixed, parameterised, row-limited queries and timeouts. Each gets a platform manifest (section 6) with a plain-language description, Tier 0, and the fields it returns.
5. **Optional free-form read (`db.query_readonly`).** NL-to-SQL, but only against allowlisted tables and columns, inside a read-only transaction, with a row cap and statement timeout, and rejected if the parsed query touches anything outside the allowlist. **Off by default**, labelled "advanced", Tier 0.
6. **Writes are never generic.** The user defines an **action** ("create a ticket", "move candidate to interview stage") as one specific parameterised operation with a preview of what will change. Tier 1 if reversible, Tier 2 if it communicates externally, Tier 3 (blocked by default) if destructive or financial.
7. **Test data.** For the sandbox the wizard offers (a) a **synthetic demo dataset** per template (customers, orders, tickets, candidates) so a user can try the agent before connecting anything real, (b) a **snapshot copy** of the mapped tables, (c) **recorded mocks**. Test mode never writes to a live system.

### 7.4 Architecture
```
Agent (inside OpenShell sandbox)
   |  MCP via gateway (the sandbox's only allowed egress)
   v
MCP gateway: injects tenant_id, agent_id, user_id; OPA check; Relay trace
   |
   v
Connector service (OUTSIDE the sandbox, beside the knowledge service)
   semantic model -> fixed queries / API calls -> allowlist + row cap + timeout -> PII masking -> result
   connection pools per tenant; credentials from the secrets store; query log with generated SQL
   |
   v
User's systems: their database, API, app, folder     (egress from the connector host only)
```
Rules, the same ones the knowledge layer follows (section 8.3) plus three more:
1. Connectors run **outside** the sandbox; the agent reaches them only through the gateway.
2. Tenant and scope are injected by the gateway, never supplied by the agent.
3. An agent sees only the connectors and tools listed in its AgentSpec.
4. **Data minimisation:** tools return only the mapped display fields; PII-labelled fields are masked unless the tool's scope includes them, and reading them is access-logged like `profile.get`.
5. **Every query is logged** with the generated SQL or request, the tenant, and the run id, and shows up in the trace view.
6. **Schema drift:** nightly re-introspection; a changed or missing column marks the mapping unhealthy, `doctor` fails pre-flight, and the generated tool returns "I can't look that up right now" instead of wrong data.

### 7.5 Record viewer and human review queues
One UI component, the **record viewer**, renders any entity from a semantic model (candidate, customer, order, ticket) as a card with its sources (table and row, document, or confirmed fact), PII masking by role, and links to the underlying documents. It is used in three places:
- **Test step:** next to the trace, "what the agent looked at".
- **Approval queue:** every Tier 2 action shows the record plus the exact payload before a human approves.
- **Review queues** for templates that produce recommendations rather than actions:
  - **Recruiting shortlist:** candidate card (confirmed profile from section 8.6, resume preview), the requisition, the agent's rationale with citations, and approve / reject / notes by the HR user. The decision and rationale are logged. The agent never changes a candidate's status itself; this is how section 8.11's "no automatic rejection, human review" is enforced in practice.
  - **Customer support:** ticket, customer and order cards, the agent's draft reply with cited sources; "send" is a Tier 2 approval until the owner relaxes it.

### 7.6 Compiler F
`integrations:` and `channels:` in the AgentSpec compile to: gateway routes for the agent (which connector tools it may call), generated tool manifests (fed into compilers C and D so OPA and the sandbox policy stay in sync), the semantic model and allowlists loaded by the connector service, action definitions with tiers, knowledge sync jobs, and channel bindings (webhook endpoints, poll jobs, schedules). Connectors add **no sandbox egress**, since the agent still only talks to the gateway.

### 7.7 Structured data vs knowledge: where things go
- **Rows and fields → tools** (exact facts, section 8.1). An order status or a candidate's email is read from the system of record, not from a document.
- **Long text that lives in a connected system → knowledge sync.** Ticket bodies and resolutions, KB articles stored in the helpdesk, resume files attached to applications, job descriptions in the ATS are synced incrementally (by `updated_at` or webhook) into a knowledge collection with the connector as source, keeping the row's ACL and tenant.
- **Resumes from a connector** (ATS, folder, inbox) go through the same parse → extract → **confirm** flow as uploads (section 8.6). Unconfirmed profiles are flagged until an HR user confirms them in the review queue.
- Rule of thumb for the wizard: structured → tool, prose → RAG, and both stay scoped to the agent's tenant and collections.

### 7.8 Free-stack notes
Everything here is the user's own systems or self-hosted open source. The default demo path is a seeded Postgres with synthetic data (`packages/demo-data/`); the optional `demo-apps` compose profile starts Zammad, Twenty or OpenCATS for people who want realistic app connectors, and it is heavy, so it is off by default. **Do not make n8n or Airbyte dependencies**: their licences are not OSI open source **[memory]**. Users may still connect them as external systems through OpenAPI or webhooks.

### 7.9 Channels and triggers: how a run starts
An agent that can only be used from the test console is not a product. Each channel binding creates runs with a known identity and passes the event as input; outputs still go through the tool tiers.

| Channel | How | Typical template | Notes |
|---|---|---|---|
| Test console | Wizard step 7 | All | Always mock or snapshot data |
| **Web chat widget** | Embeddable script tag + FastAPI websocket; anonymous or logged-in | Support, research | Rate-limited; anonymous users get Tier 0 only |
| **Email inbox** | Gmail API via OAuth, or IMAP polling; replies as Tier 2 drafts | Support, recruiting (applications), personal | No paid email API |
| **Webhook** | Signed inbound URL per binding (new ticket, new application, new row) | Support, ops, recruiting | Verify signature, replay-protect, idempotent run ids |
| **Folder watch** | Local folder, Nextcloud or Drive change feed | Recruiting (new resumes), ops | Triggers ingestion first, then the agent |
| **Schedule** | Cron table in Postgres, APScheduler | Personal (daily brief), ops, sales | Runs with the owner's identity |
| **Voice** | Section 9 | Caller | Separate realtime loop |
| **Human review queue** | Section 7.5 | Recruiting, support | Humans trigger the final action, not the agent |

Channel bindings live in the `channels:` block of the AgentSpec and are published together with the agent in wizard step 9.

## 8. Knowledge layer: RAG and exact personal data

### 8.1 Three kinds of knowledge, three access paths
One RAG pipeline cannot serve every need. A support bot must quote the refund policy, a recruiting agent must state a candidate's exact employment dates, and a personal agent must remember that you prefer morning meetings. These are different problems.

| Kind | Examples | Mechanism | Why |
|---|---|---|---|
| **Exact facts** about a person, business or record | Candidate email, degree and dates, business hours, price, order status | **Confirmed structured store + lookup tools** (`profile.get`, `faq.lookup`, SQL-backed tools) | Similarity search returns the nearest passage, which can be a near-miss. An exact fact must come from a field, not a guess |
| **Narrative content** | KB articles, policies, resume text, job descriptions, manuals | **Hybrid RAG** (`knowledge.search`) | Semantic plus keyword retrieval, with citations |
| **Preferences and history** | "Prefers morning meetings", earlier conversations | **Memory store** | Small, per-user, written by the agent; not a document corpus |

This is how the platform delivers the exact information about a person without extra hassle: **parse once, show the parsed fields to the user in the wizard, let them confirm or fix them, and store them as confirmed facts.** The agent answers exact questions from those fields and uses RAG for the long tail.

### 8.2 What each agent type needs
| Agent | Knowledge sources | Exact-data store | Retrieval notes |
|---|---|---|---|
| Customer support | Product docs, FAQs, policies, optionally resolved tickets (synced from the helpdesk, section 7.7) | Order or customer lookup via database-connector tools (section 7); pinned FAQ answers | Citations required; abstain and escalate when evidence is weak; freshness matters for policies |
| Recruiting (company side) | Job descriptions, hiring policy, company info, candidate resumes (uploaded, or from an ATS, folder or inbox via section 7) | Parsed candidate profile confirmed in the review queue (section 7.5), job requisition fields | Personal data; strict access control; no automatic rejection, human review |
| Job-applying personal agent (user side) | The user's resume, cover letters, past applications, job postings | User's confirmed profile (contact, dates, links) | Exact fields prefill forms; every submission is Tier 2 and needs approval (section 6) |
| Personal automation | User's notes and documents (email and calendar via tools, not indexed by default) | Preferences | Memory matters more than RAG |
| Caller (voice) | FAQ, business info, price list, policies | Pinned FAQ cards, hours, services | Tight latency: exact FAQ match first, small top_k, no reranker on the hot path, cached |
| Research / ops / sales | User-uploaded documents, exports | Record lookups via tools | Standard hybrid RAG |

### 8.3 Architecture
```
Sources: file upload, URL or sitemap crawl, user's own Drive, pasted text, connected systems via connector sync (section 7.7)
   |
   v
Ingestion worker (async, resumable job) = thin wrapper around NeMo Retriever
   NeMo Retriever: extract (text, tables, charts, OCR) -> embed -> store   [lite mode: our parser + CPU embedder + pgvector]
   ours, around it: metadata/ACL tagging -> PII scan -> tenant-scoped collection
   profile extractor: LLM -> JSON schema -> validation -> user confirms in wizard
   |
   v
Vector store (LanceDB / Milvus, or pgvector in lite mode): chunks + embeddings
Postgres: documents, profile_facts, faq_cards, memory, ingestion_jobs
   |
   v
Knowledge service (runs OUTSIDE the sandbox)
   RetrievalEngine (NeMo Retriever, or lite pgvector) -> mandatory filters -> optional rerank -> parent expansion -> citations
   exposed as MCP tools through the existing gateway:
      knowledge.search   Tier 0
      faq.lookup         Tier 0
      profile.get        Tier 0, sensitive, access-logged
      memory.read/write  Tier 0 / Tier 1
   ^
   |  MCP via gateway
Agent (inside OpenShell sandbox)
```
Rules that follow from the rest of the architecture:
1. **Retrieval runs outside the sandbox.** The sandbox policy allows egress only to the MCP gateway, so a compromised agent cannot reach the database.
2. **Tenant and scope are never supplied by the agent.** The gateway derives `tenant_id`, `agent_id` and `user_id` from the run identity and injects them; the knowledge service enforces the filter, with Postgres row-level security as a backstop. A prompt-injected agent cannot ask for another tenant's data.
3. **An agent sees only the collections listed in its AgentSpec.**
4. **Retrieval is an ordinary tool call:** risk tier 0, OPA check, Relay trace, and a real read-only knowledge base available in test mode.

Core tables (sketch): `collections`, `documents` (version, hash, source, ACL, sensitivity), `chunks` (text, embedding, tsvector, metadata, parent_id, embedding_model, valid_from, valid_until), `ingestion_jobs`, `profile_facts` (subject, schema, key, value, source_chunk, extracted_at, confirmed_by, confirmed_at), `faq_cards` (question variants, answer, owner_approved), `memory_items`.

### 8.4 Ingestion
- **Parsing and extraction: NeMo Retriever library.** It splits documents into pages, classifies elements (text, tables, charts, infographics), OCRs them and emits structured JSON **[verified]**. File-type coverage (DOCX, HTML, CSV, Markdown) is unconfirmed; S9 checks it, with the lite parser as fallback.
- **Chunking:** structure-aware, so headings, lists and tables stay intact. Roughly 300 to 800 tokens with small overlap. **Parent-child:** retrieve the small chunk, return its parent section. Resumes chunk by section (experience, education, skills); tables become their own chunks with their captions.
- **Metadata on every chunk:** tenant, collection, document id and version, source and page or section, language, ACL, sensitivity label, `valid_from` and `valid_until`, embedding model id.
- **PII scan** at ingestion; sensitive documents get a label that restricts which agents and tools may read them.
- **Idempotent and resumable:** content hashes skip unchanged files; edits trigger re-ingestion; **deleting a document removes its chunks, embeddings and caches** (right to erasure).
- **Embeddings:** NeMo Retriever's `.embed()` step by default; the lite backend uses an open-weights CPU model behind our `Embedder` interface. The model id is stored per chunk, and changing models means re-embedding the whole collection into a new versioned index. Choose a multilingual model if Hindi and English both matter, and test it in S9.

### 8.5 Retrieval
1. Optional query rewrite using chat context (resolve "it", "that policy").
2. **Retrieval:** NeMo Retriever's `Retriever` class runs the query against the collection **[verified]**. Whether it does hybrid (dense + keyword) search is unconfirmed (S10); if not, we add keyword search and reciprocal rank fusion ourselves. The lite backend is pgvector plus Postgres full-text search with RRF.
3. **Mandatory metadata filters:** tenant, collection, ACL, validity dates.
4. Optional reranker (open cross-encoder, or a Nemotron reranker) when the latency budget allows. NeMo Retriever's README does not mention reranking **[verified]**, so this stays our optional step.
5. Parent expansion and de-duplication.
6. **Confidence threshold:** below it the service returns "insufficient evidence" instead of weak context, so the agent can say "I don't have that" or escalate.
7. Return passages with source, page and document version for citations.

Defaults per template live in the AgentSpec `knowledge.retrieval` block. Voice agents use no reranker, `top_k` of about 3, and FAQ-first. Time-sensitive material (prices, postings, policies) uses `valid_until` filters and stale warnings.

### 8.6 The exact-data store
- **Schemas per template:** candidate or user profile, business info, FAQ cards, order lookup fields. Each is a JSON Schema in `packages/knowledge-schemas/`.
- **Resume flow:** upload, parse, LLM extraction into the schema with validation, wizard shows a review form, user confirms or edits, facts become `confirmed`.
- **Agents answer exact questions only from confirmed facts.** Unconfirmed fields come back flagged as unverified. The template instructions and an eval check both enforce "never recall contact details or dates from retrieved prose when a confirmed fact exists".
- **FAQ cards** are owner-approved question and answer pairs, matched exactly first. They are the fastest and safest path for caller agents.

### 8.7 Grounded generation and guardrails
- Instructions: answer only from supplied context, cite sources, say "I don't have that" rather than guess, escalate per template.
- Chat UI renders citations; voice agents speak short answers and log the sources instead.
- Structured output (JSON schema) for forms and applications, validated before any tool call.
- NeMo Guardrails retrieval and output rails for grounding and relevance checks **[memory]**.
- **Retrieved text is untrusted data.** Indirect prompt injection through documents and web pages is a primary RAG risk. Mitigations: delimit and label retrieved content, strip instruction-like patterns where practical, never derive tool-call authority from retrieved text, and rely on OPA, OpenShell and Tier 2 human approval as the backstop.

### 8.8 Evaluating RAG
- **Golden set generated from the user's own documents:** an LLM writes question and answer pairs with the source passage, and the user approves them in the wizard. Add **negative questions** (answer not in the KB) and **adversarial ones** (injection text planted in a document).
- **Retrieval metrics:** hit rate or recall at k, MRR. **Generation metrics:** faithfulness to context, answer relevance, citation correctness, correct abstention. **Exact-field accuracy** for profile facts. **Latency** p50 and p95.
- Libraries: Ragas or your own LLM-judge **[memory]**. Whether NAT's eval or NeMo Evaluator ships RAG metrics is **unverified** (S10).
- The publish gate (section 11) includes minimum retrieval and faithfulness scores.
- **Knowledge-gap report** from production traces: questions that had no good evidence, shown to the owner as "add this to your knowledge base".

### 8.9 Fit with NAT, Fabric and OpenShell
- NAT's docs navigation shows **retriever and embedder concepts**: embedder modules for OpenAI, Hugging Face, NVIDIA NIM and Azure OpenAI, a LangChain retriever plugin, and an "Adding a Retriever" custom-component guide **[verified: present in the docs navigation; the page bodies were not readable this session, so config syntax and supported vector stores are unconfirmed]**.
- NAT's memory interface appears as an unfinished roadmap item, with Redis and Mem0 only credited or linked as external plugins **[verified]**, so **memory is ours**, built on Postgres.
- **Decision:** build the knowledge service as **our own service behind MCP**, with NeMo Retriever as the engine inside it (section 8.12). It is portable, works with the sandbox, and goes through the same policy path as every other tool. Optionally add a thin NAT custom retriever that calls it for NAT-native workflows. S10 confirms.
- Fabric needs nothing special: its MCP config points the agent at the gateway.

### 8.10 Free-stack choices
**Default (v7): the lite backend** (Postgres with pgvector and full-text, CPU embedders, Docling for parsing), so the zero-spend path works on a GPU-less Mac. **Optional:** NeMo Retriever with LanceDB (in-process) for GPU owners or hosted-endpoint prototyping; Milvus only if scale demands it. Uploaded files on a local volume. NVIDIA's hosted endpoints are prototyping only (section 3.4).

### 8.12 NeMo Retriever integration (v6)
**What we take from it:** extraction, embedding, vector storage and the `Retriever` query API. **What we keep:** everything that makes retrieval safe and exact.

| Concern | Owner |
|---|---|
| Parse, OCR, tables and charts, embed, index, query | **NeMo Retriever** |
| Tenant/collection isolation, ACL, validity dates, sensitivity labels | Ours (one collection or table per tenant and collection, plus metadata filters; S13 tests it) |
| Confirmed facts, FAQ cards, memory | Ours (Postgres) |
| Confidence threshold, abstention, citations with document version | Ours |
| MCP tools (`knowledge.search` etc.), OPA, Relay traces | Ours |
| Erasure of a deleted document's chunks and embeddings | Ours, calling the engine's delete; S13 verifies it really removes vectors |

**Interface:** `RetrievalEngine { ingest(doc, meta), search(query, filters, k), delete(doc_id), reindex(embedding_model) }`. Backends: `pgvector_lite` (default) and `nemo_retriever` (optional). The AgentSpec picks nothing here; the deployment config does (`retrieval_engine: nemo_retriever | pgvector_lite`), so agents do not change when the engine does.

**Is "RAG" included?** Its README shows a RAG example that sends retrieved text to an LLM, plus LangChain and LlamaIndex integrations **[verified]**. We still do generation through NAT with our grounding rules (section 8.7), not through its example, so the model stays BYOK.

**Open risks:** GPU requirement for local use (production guidance in its docs is heavy: 24 GB+ VRAM class GPU, Linux, NVIDIA Container Toolkit) **[verified via search]**; hosted endpoints are dev/test only; embedding model licence (OpenMDW); a third-party source claims production use needs NVIDIA AI Enterprise **[secondary, unverified]**. Read the actual terms in S7 before making it the default. If they block free production use, `pgvector_lite` becomes the default and NeMo Retriever stays an optional provider, consistent with section 3.4.

### 8.11 Privacy and compliance
Resumes and customer records are personal data. Plan for consent, retention limits, deletion on request, encryption at rest, and an access log on `profile.get`. India's DPDP Act and GDPR may apply, and automated hiring decisions are treated as high-risk in some regimes such as the EU AI Act **[memory, not legal advice; check before any real deployment]**. So: **no automatic rejection, human review of every recommendation, and a logged rationale.** Applying to jobs on a user's behalf sends personal data to third parties, so it is **Tier 2: show the exact payload and require approval before sending.**

## 9. Caller agents and speech

### 9.1 What NVIDIA offers, and the catch
- **Riva (classic):** forum statements say Riva is free up to **1,000 hours of ASR per day and 25 million TTS characters per day**, with paid Riva Enterprise above that. But a 2023 reply says the free version is for POC and testing, and a user flagged that the EULA seemed to allow only non-production use with no clear answer **[verified, but the thread is not the licence]**. Read the actual EULA before relying on it.
- **Nemotron Speech** (NVIDIA's newer speech models): NVIDIA's page says "available for free production use", deployable via NIM; ASR and TTS run on a single L40, A100 or H100 **[verified]**. That is data-centre GPU hardware, so it is not free for a hobbyist unless you already own one. Magpie TTS lists 7 languages, but the page does not name them, and ASR language coverage is not stated (check Hindi if that matters).
- NIM Developer Program: free for research, development and test only **[verified]**.

### 9.2 Design
Speech is a **channel component, not an MCP tool.** The live audio loop cannot go through MCP without breaking latency; MCP carries the *actions* (book, transfer, send SMS).

```
Caller (WebRTC in browser for free testing; SIP/PSTN needs a paid trunk)
  -> realtime framework (Pipecat or LiveKit, self-hosted)
      -> ASR provider -> agent turn (Fabric multi-turn runtime) -> TTS provider
  -> audio back
Speech providers (pluggable):  open-source ASR/TTS (default, CPU-friendly)  |  NVIDIA Riva / Nemotron Speech (optional, needs GPU)
```
- **Default free path:** open ASR/TTS models running locally, plus browser-based WebRTC voice testing. Real phone numbers cost money, so PSTN is out of scope unless the user brings their own SIP trunk.
- Latency target about one second per turn: stream ASR, stream LLM tokens, stream TTS, support barge-in. Fabric supports multi-turn runtimes and OpenAI-style streaming **[verified]**.
- Voice guardrails: disclose it is an AI, no medical, legal or financial advice, escalate to a human, redact PII in transcripts.
- Compliance (call-recording consent, India TRAI DND rules for outbound calls) needs a review before any outbound calling.
- `voice:` block in the AgentSpec selects ASR, TTS, language and transport.

## 10. Guardrails, policy and auth
- **Three layers, three failure modes:** NeMo Guardrails (what the agent says or plans) / OPA (whether a call is allowed) / OpenShell (what the process can touch at OS and network level).
- Relay's tool-execution middleware is the candidate hook for calling OPA before each tool call **[verify in S4]**. The Relay docs list its own NeMo Guardrails plugin as deprecated, so wire Guardrails directly instead.
- **Retrieved content is untrusted.** Documents and web pages can carry injected instructions (section 8.7). The knowledge service labels retrieved text as data, and no tool-call authority ever comes from it; OPA, OpenShell and Tier 2 approval catch what slips through.
- Auth: local auth for the MVP, Keycloak later; per-agent service identity; OAuth with a token store for third-party accounts; tenant ID on every row.
- **BYOK key handling is the biggest security liability.** Encrypt at rest (OpenBao or SOPS+age), audit every use, never log or return it. OpenShell holds provider credentials **outside** the sandbox and routes model calls through `inference.local` **[verified in NemoClaw docs]**, so the agent never sees the key.

## 11. Evaluation and observability
- **Relay** instruments LLM calls, tool calls and subagents, exporting ATOF, ATIF trajectories and OTel **[verified]**.
- **NAT** has its own offline evaluation and profiling **[verified]**. This is the **primary** eval engine for the MVP, since it needs no extra service.
- **NeMo Evaluator** is open source (Apache-2.0), Python 3.12 to 3.13, Docker for code sandboxes, no GPU or Kubernetes mentioned. It supports agentic benchmarks and Harbor-style agents, but **its README does not say it scores arbitrary agent trajectories** **[verified]**. This corrects my earlier claim; S4 tests it.
- **garak** for red-teaming before publish. **Fallback judge:** your own LLM-as-judge over ATIF trajectories.
- **RAG evals** (section 8.8): retrieval hit rate, faithfulness, citation correctness, correct abstention, exact-field accuracy. Tools unconfirmed (S10); Ragas or a custom judge is the fallback.
- **Publish gate:** disabled until the template's tool-use, retrieval and grounding thresholds pass.
- Overlap to resolve in S4: NAT and Relay both do telemetry; pick one as the source of truth to avoid double instrumentation.

## 12. Phase 0: spikes (weeks 1 to 2)

| Spike | Question | Exit criterion |
|---|---|---|
| S1 NAT hello world | `pip install nvidia-nat`, run a workflow with an OpenAI-compatible BYOK model and one MCP tool | Agent answers using the tool, no NVIDIA key required |
| S2 NAT via Fabric | Wire NAT as Fabric's shared-framework adapter target; run `plan`, `doctor`, `run` | A `RunResult` with telemetry refs |
| S3 Inside OpenShell | Run S2 in an OpenShell sandbox using a NemoClaw-style blueprint with a generated policy | Allowed egress works, denied egress is blocked; note start-up time and RAM per sandbox |
| S4 Relay and evals | Relay emits ATIF from S3; NAT eval and Evaluator each score it; try OPA via Relay middleware | One scored trajectory; decision on telemetry source of truth |
| S5 Helix check | Read Helix and Studio Agents docs: free, self-hostable, no-code, BYOK? | Build / borrow / ignore decision |
| S6 Free-stack run | Run S1 to S4 fully on a laptop with Ollama, no cloud spend | Works end to end, and the quality of the small model is noted |
| S7 Licences | Read Fabric and Relay licence pages, OpenShell Support Matrix and licence, NIM or Riva EULA | One-page licence table committed to `docs/` |
| S8 Speech (optional) | Compare open ASR/TTS vs Riva/Nemotron Speech on latency and Hindi/English | Numbers, plus a go or no-go for GPU speech |
| S9 RAG baseline | Ingest about 50 real documents (including a few resumes) with **NeMo Retriever** (hosted endpoint if no GPU) and with the pgvector lite backend; compare retrieval quality, file-type coverage, Hindi/English, and CPU vs GPU/hosted latency; parse a resume into the `candidate_v1` schema | Hit rate, abstention behaviour, p95 latency, and the resume field accuracy before and after user confirmation |
| S10 NAT retrievers and RAG evals | Read the NAT retrievers and "Adding a Retriever" docs; check whether NeMo Retriever has hybrid search, reranking and metadata filters, and whether NAT can use it as a retriever; test whether NAT eval or Evaluator can score RAG | Written decision: own MCP service around NeMo Retriever, NAT custom retriever, or both; chosen RAG eval tool |
| S13 NeMo Retriever multi-tenancy | Create two tenants' collections in LanceDB; try cross-tenant queries, metadata filters, delete-and-verify-erased, re-embed into a new versioned index | Isolation holds under attack tests; erasure is real; decision on one-collection-per-tenant vs filters; default engine decision |
| S14 Tool calling and gateway | (a) Run our `simple-agent` as a NAT `tool_calling_agent` and as `react_agent` on 3 to 4 models (a free one, a local Ollama one, a stronger paid one) and score pass rate over 10+ runs each, logging raw responses to tell empty output, 429 and wrong format apart. (b) Check whether the Fabric NAT adapter can take a tool-calling target or needs our own adapter target. (c) Put LiteLLM or OpenRouter behind the BYOK interface and run the same set. (d) Try Switchyard 0.3.0 as a local proxy with two models and, if feasible, its Relay plugin against our pinned Relay | A pass-rate table per model and agent mode; a decision on default agent mode, the capability table fields, whether Fabric needs a custom adapter, and whether Switchyard is worth enabling |

| S11 Database connector | Point a read-only connector at a seeded Postgres and a SQLite file: introspect, map `customer` and `order` entities in a throwaway form, generate `customer.find` and `order.get` as MCP tools, call them from the S1 agent; then enable guarded NL-to-SQL and count how often a small local model writes a query the guard rejects or should have rejected | Agent answers "where is order 123" from the database with no hand-written tool code; privilege check refuses a read-write user; a list of guard rejections and misses |
| S12 OpenAPI to tools | Feed a public OpenAPI spec (Petstore, then Zammad or OpenCATS) through FastMCP `from_openapi` or an alternative; wrap in manifests; tier by HTTP method; call through the gateway | Generated tools work end to end; choice of generator library with its licence recorded in the S7 table |

S9 to S14 may spill into week 3 without blocking Phase 1, because Phase 1 uses the personal-automation template, which depends on neither RAG nor connectors beyond Google OAuth.

## 13. Roadmap after Phase 0

| Phase | Weeks | Deliverable |
|---|---|---|
| 1. Vertical slice | 3 to 6 | Wizard (BYOK, personal-automation template, 5 to 8 tools), AgentSpec compilers A to C, run in OpenShell sandbox in test mode, trace view |
| 2. Safety | 7 to 9 | Guardrails profiles, OPA policies, risk tiers, approval UI, per-tool sandbox policy generation |
| 3. Integrations v1 | 10 to 12 | Connector service with database (read-only) and CSV/Sheets connectors, schema introspection and entity mapping in the wizard, generated typed lookup tools with manifests, compiler F, synthetic demo datasets and snapshot test mode, record viewer, web-chat widget and webhook channels |
| 4. Knowledge layer v1 | 13 to 16 | `RetrievalEngine` interface with NeMo Retriever and pgvector_lite backends, ingestion worker, `knowledge.search`, `faq.lookup`, `profile.get` over MCP, gateway-injected tenant scope, wizard "Add knowledge" step with fact confirmation, connector-to-collection sync, citations in the trace view |
| 5. Evals | 17 to 19 | NAT eval suites, RAG golden sets and metrics, connector tests against snapshot data (including cross-tenant and allowlist-escape attempts), garak (including injection-in-document tests), publish gate |
| 6. More templates | 20 to 24 | Support first (database + helpdesk + RAG), then recruiting (ATS or folder, review queue) and job-applying, then research, ops, sales; OpenAPI and bring-your-own-MCP connectors, first app packs, email and schedule channels; bigger tool catalog |
| 7. Caller agents | 25 to 31 | WebRTC voice, pluggable ASR/TTS, FAQ-first low-latency retrieval, voice guardrails and evals; PSTN only via user-supplied trunk |
| 8. Distribution | later | Docs, one-command install, sample agents, optional hosted demo (costs money, so a separate decision) |

## 14. Suggested repo layout (monorepo, VS Code)
```
agent-platform/
  apps/web/                  # Next.js wizard
  services/control/          # FastAPI: specs, catalog, policy + config compilers
  services/runner/           # Fabric SDK wrapper, OpenShell lifecycle, Relay wiring
  services/mcp-gateway/      # per-agent tool exposure, OPA checks
  services/knowledge/        # RetrievalEngine wrapper (NeMo Retriever + pgvector_lite), ingestion worker, MCP tools (Phase 4)
  services/connectors/       # database, CSV/Sheets, OpenAPI, BYO-MCP connectors; semantic models; generated tools (Phase 3)
  services/channels/         # web chat widget API, email poller, webhook receiver, scheduler (Phase 3)
  services/voice/            # Phase 7
  packages/agent-spec/       # JSON Schema + typed models (the stable contract)
  packages/knowledge-schemas/ # profile schemas (candidate, business, FAQ card) and chunk metadata
  packages/semantic-models/  # entity mapping schemas per template (customer, order, ticket, candidate, requisition, booking)
  packages/connector-packs/  # curated app connectors (Zammad, FreeScout, Twenty, OpenCATS, Nextcloud)
  packages/demo-data/        # synthetic datasets per template for test mode
  packages/tool-manifests/   # one manifest per catalog tool
  packages/templates/        # per-template instructions, rails, evals, policy presets
  packages/model-capabilities/ # per-model: tool calling, streaming, JSON mode, context, reliability tier (from evals)
  policies/                  # Rego bundles, OpenShell policy presets, Colang configs
  evals/                     # suites per template
  evals/rag/                 # golden sets, retrieval and grounding metrics
  deploy/compose/            # docker-compose for the local-first stack
  spikes/                    # S1..S14
  docs/                      # this plan, ADRs, licence table
```
Write ADRs for: NAT-as-agent-layer, OpenShell tenancy model, Helix decision, telemetry source of truth, where OPA and Guardrails hook in, speech provider interface, knowledge service as own MCP service vs NAT retriever, embedding model and versioning policy, how tenant scope is injected, semantic model and tool generation from connectors, NL-to-SQL guard policy, channel and trigger identity model, agent mode selection and the model capability table, gateway choice (OpenRouter vs LiteLLM) and Switchyard's optional role.

## 15. Risks
1. **Scope.** Mitigation: vertical slice first, caller agents last.
2. **Upstream churn** (0.x versions). Mitigation: pin versions, own the AgentSpec and compilers.
3. **OpenShell fit.** Every published example is a coding agent; many short multi-user sessions are unproven, and its host OS and hardware requirements are unread. Mitigation: S3 and S7.
4. **Licences.** Fabric, Relay and OpenShell terms are not yet read; NVIDIA free tiers are dev/test only. Mitigation: S7, optional providers.
5. **Weak free models.** Small local models give poor agents; templates must degrade gracefully and the docs should say so.
6. **Helix overlap.** Mitigation: S5, then sharpen positioning on guided UX.
7. **BYOK security and tenant isolation.** Mitigation: design secrets first, security review.
8. **Voice cost and regulation.** Mitigation: optional, last, free WebRTC path first.
9b. **Model output-format failures** (S2b: ReAct parse errors on free models, about half of runs). Mitigation: native tool calling by default, ReAct fallback, one format-repair retry, capability table, eval gate that blocks weak model and template pairs, S14.
9c. **Switchyard maturity** (pre-1.0, demo server, experimental LiteLLM path, vendor-reported benchmarks). Mitigation: optional provider behind our interface, never on the MVP path, evaluate in S14.
9d. **Free-tier quotas** (50 requests a day on OpenRouter free). Mitigation: credits or local models for evals; cache and batch test runs; tell users in the wizard.
9a. **NeMo Retriever fit.** GPU-centric, LanceDB/Milvus rather than pgvector, unverified production licence terms, early versioning (26.x). Mitigation: `RetrievalEngine` interface, pgvector_lite fallback, S7/S13 before making it the default.
9. **Poor retrieval on messy real documents** (scans, tables, mixed languages). Mitigation: S9 on real files, parse previews in the wizard, hybrid search, and measured thresholds rather than guesses.
10. **Indirect prompt injection through documents.** Mitigation: treat retrieved text as data, no authority from it, OPA, OpenShell and Tier 2 approval as backstops, injection tests in the eval suite.
11. **Cross-tenant data leakage.** Mitigation: gateway-injected scope, service-side filters, Postgres row-level security, tests that try to read another tenant's data.
12. **Wrong exact facts** (bad resume parsing, stale policies). Mitigation: user-confirmed facts only, validity dates, flagged unverified fields.
13. **Embedding lock-in.** Mitigation: model id per chunk, versioned indexes, `Embedder` interface.
14. **Hiring-related regulation and bias, and personal-data law.** Mitigation: human review, no automatic rejection, consent and deletion paths; get proper advice before any real deployment.
15. **Writing to a real company database or system.** Mitigation: read-only database users checked at connect time, writes only through user-defined tiered actions with a preview, snapshot or synthetic data in test mode, no generic SQL writes ever.
16. **Data exfiltration through free-form queries** (a prompt-injected agent dumping a customer table). Mitigation: NL-to-SQL off by default; allowlisted tables and columns, row caps, statement timeouts, PII masking, query log and Relay trace; eval cases that try it.
17. **Schema drift and broken mappings** returning wrong data silently. Mitigation: nightly re-introspection, mapping health in `doctor`, tools fail closed with "I can't look that up right now".
18. **Connector sprawl.** Every app wants its own connector. Mitigation: four generic connectors first (database, CSV/Sheets, OpenAPI, bring-your-own MCP); app packs only when a template needs one, and built on the OpenAPI connector.
19. **Inbound channels as an attack surface** (unauthenticated webhooks, anonymous chat). Mitigation: signed webhooks with replay protection, rate limits, anonymous users limited to Tier 0, and every run tagged with its channel identity.

## 16. Reference links
- NeMo Agent Toolkit: https://github.com/NVIDIA/NeMo-Agent-Toolkit
- NeMo Fabric overview: https://docs.nvidia.com/nemo/fabric/about-nemo-fabric/overview
- NeMo Fabric adapter contract (NAT as shared framework adapter): https://docs.nvidia.com/nemo/fabric/adapter-contract/overview
- NeMo Fabric ecosystem (Helix, NemoClaw, Gym, Polar): https://docs.nvidia.com/nemo/fabric/about-ne-mo-fabric/ecosystem
- NeMo Relay overview: https://docs.nvidia.com/nemo/relay/about-nemo-relay/overview
- OpenShell docs: https://docs.nvidia.com/openshell/about/llms.txt and https://github.com/NVIDIA/OpenShell
- OpenShell community sandboxes: https://github.com/NVIDIA/OpenShell-Community
- NemoClaw architecture: https://docs.nvidia.com/nemoclaw/latest/about/how-it-works
- NeMo Agent Toolkit docs (retrievers, embedders, "Adding a Retriever"; versions 1.0 to 1.8): https://docs.nvidia.com/nemo/agent-toolkit/1.8/build-workflows/retrievers.html
- NeMo Switchyard (model routing): https://github.com/NVIDIA-NeMo/Switchyard and https://developer.nvidia.com/blog/route-ai-agent-workloads-across-models-with-nvidia-nemo-switchyard/
- LiteLLM (gateway): https://github.com/BerriAI/litellm
- NeMo Retriever library (GitHub, Apache-2.0): https://github.com/NVIDIA/NeMo-Retriever
- NeMo Retriever docs and support matrix: https://nvidia.github.io/NeMo-Retriever/extraction/prerequisites-support-matrix/
- NeMo Retriever (Nemotron embedding and reranking models): https://developer.nvidia.com/nemo-retriever/
- NeMo Evaluator: https://github.com/NVIDIA-NeMo/Evaluator
- NeMo Helix: https://github.com/NVIDIA-NeMo/nemo-helix
- NIM FAQ (free tier and Developer Program terms): https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317
- Riva free-usage thread: https://forums.developer.nvidia.com/t/riva-can-be-deployed-free-of-charge-up-to-a-certain-usage-limit-clarifications/209902
- Nemotron Speech self-hosting FAQ: https://perspectives.nvidia.com/nemotron-speech/task/faq/speech-ai-models-self-host-high-call-volumes/
