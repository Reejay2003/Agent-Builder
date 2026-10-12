# Agent Builder

A free, open-source, local-first platform where a non-technical person builds, tests and deploys AI agents through a guided wizard. Built on NVIDIA's open-source agent stack (NeMo Agent Toolkit, NeMo Fabric, OpenShell) with bring-your-own-key LLMs.

**Status: early research (Phase 0 spikes).** There is no product UI yet. Start with [COMPLETED.md](COMPLETED.md) (what is done, decided and broken) and [PLAN.md](PLAN.md) (the full design). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).

## Quick start (about 10 minutes)
You need: **Docker Desktop** (or Docker Engine 28+), and either **[uv](https://docs.astral.sh/uv/)** or **Python 3.11 to 3.13**. macOS (Apple Silicon) is what we develop on; Linux should work. No GPU needed.

```bash
git clone https://github.com/Reejay2003/Agent-Builder.git && cd Agent-Builder
make setup        # creates .env and .venv, installs pinned dependencies
# edit .env: set POSTGRES_PASSWORD (any random string, letters and digits) and OPENROUTER_API_KEY (your own key)
make up           # Postgres + pgvector, Valkey
make check        # verifies everything
make agent        # runs the simple NAT agent (needs your key)
make fabric-agent # same agent through NeMo Fabric
```
`make help` lists everything. No key yet? `make fabric-doctor` and `make fabric-agent ARGS=--plan` run without one.

**Use your own API key.** Never share or commit keys; `.env` is git-ignored. The default model is a free OpenRouter model (50 requests a day, flaky as an agent brain; see COMPLETED.md Gotchas).

## Repo map
| Path | What |
|---|---|
| [PLAN.md](PLAN.md) | The master plan (architecture, wizard, phases, spikes, risks) |
| [COMPLETED.md](COMPLETED.md) | Progress, decisions, gotchas, next tasks. Update it with every PR |
| `agents/simple-agent/` | A minimal NAT agent (YAML) |
| `services/runner/nat_adapter/` | Our NAT adapter for Fabric (ReAct + tool calling, Relay, repair); run `make test` |
| `packages/mcp-tools/`, `packages/tool-manifests/` | Demo MCP server and its tool manifest (the start of the tool store) |
| `spikes/` | Phase 0 experiments, one folder each, with a README holding the result |
| `deploy/compose/` | Docker Compose stack (Postgres+pgvector, Valkey, optional dev container) |
| `deploy/docker/` | Dockerfiles (dev container) |
| `scripts/` | Helper scripts (`check_env.sh`) |
| `requirements.txt` / `.lock` | Direct pins / fully resolved pins (what `make setup` installs) |
| `.claude/`, `.mcp.json` | Optional Claude Code skills and Playwright MCP config |

Folders from the plan's layout (`apps/`, `services/`, `packages/`) are created when their phase starts.

## Optional pieces
- **No local Python:** `make dev-shell` opens a container with all dependencies.
- **OpenShell sandbox spikes (S3):** need NVIDIA OpenShell on the host and Docker Desktop's host networking enabled. See [spikes/s3-openshell/README.md](spikes/s3-openshell/README.md).
- **Everything NAT ships:** `make setup-full` (about 2 GB).

## Troubleshooting
Run `make check` first. Common causes are in COMPLETED.md under Gotchas: Python 3.14, pre-release pins, Docker not on PATH, a full disk, free-tier rate limits.

## Licence
Apache License 2.0, see [LICENSE](LICENSE). Files copied from NVIDIA projects keep their own Apache-2.0 notices (for example `services/runner/nat_adapter/LICENSE-NVIDIA-Fabric`).
