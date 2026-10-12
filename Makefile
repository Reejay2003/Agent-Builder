# Common tasks. Run `make help`. Needs: Docker Desktop (or Docker Engine 28+) and either uv or Python 3.11-3.13.
SHELL := /bin/bash
# NAT needs Python 3.11-3.13. Plain `python3` may be newer (3.14) and fail, so pick explicitly. Override: make setup PY=/path/to/python3.12
PY ?= $(shell for p in python3.12 python3.13 python3.11; do command -v $$p && break; done)
COMPOSE := docker compose -f deploy/compose/docker-compose.yml --env-file .env
# LLM_API_KEY falls back to OPENROUTER_API_KEY so older .env files keep working
RUN_ENV := set -a; . ./.env; set +a; export LLM_API_KEY="$${LLM_API_KEY:-$$OPENROUTER_API_KEY}"; . .venv/bin/activate

.PHONY: help test eval env setup setup-full check up down ps logs agent fabric-agent fabric-doctor sandbox-image dev-shell

help:  ## list targets
	@grep -E '^[a-zA-Z_-]+:.*##' Makefile | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

env:  ## create .env from the template (does not overwrite)
	@test -f .env || (cp .env.example .env && echo "Created .env. Edit it: set POSTGRES_PASSWORD and OPENROUTER_API_KEY.")

setup: env  ## create .venv and install pinned dependencies (uses uv if installed, else pip)
	@if command -v uv >/dev/null; then \
	  uv venv --python 3.12 --allow-existing .venv && uv pip install --python .venv/bin/python -r requirements.lock; \
	elif [ -n "$(PY)" ]; then \
	  $(PY) -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.lock; \
	else echo "No Python 3.11-3.13 found. Install uv (https://docs.astral.sh/uv/) or Python 3.12, or run: make setup PY=/path/to/python3.12"; exit 1; fi
	@echo "Done. Next: make check"

setup-full: setup  ## also install every NAT extra (large, about 2 GB)
	.venv/bin/pip install -q --pre -r requirements-full.txt

check:  ## verify the environment (tools, .env, services)
	@./scripts/check_env.sh

up:  ## start Postgres+pgvector and Valkey
	$(COMPOSE) up -d

down:  ## stop services (data is kept)
	$(COMPOSE) stop

ps:  ## service status
	$(COMPOSE) ps

logs:  ## follow service logs
	$(COMPOSE) logs -f --tail=50

agent:  ## run the simple NAT agent: make agent Q="your question"
	$(RUN_ENV); nat run --config_file agents/simple-agent/workflow.yml --input "$${Q:-Who created Python, and what is the date today?}"

test:  ## offline tests for our adapter additions (no LLM, no cost)
	$(RUN_ENV); python spikes/s2-fabric-nat/test_adapter_patches.py

eval:  ## NAT eval with ATIF output: make eval KIND=react|tool_calling REPS=3 MODEL=gpt-4.1-mini (costs LLM calls)
	$(RUN_ENV); export JUDGE_MODEL=$${JUDGE_MODEL:-$${LLM_MODEL}}; $${MODEL:+export LLM_MODEL=$$MODEL;} nat eval --config_file spikes/s4-relay-eval/eval-$${KIND:-tool_calling}.yml --reps=$${REPS:-1}; python spikes/s4-relay-eval/summarize.py spikes/s4-relay-eval/out/$${KIND:-tool_calling}

fabric-agent:  ## run the same agent through Fabric (ARGS=--plan or --doctor skips the LLM call)
	$(RUN_ENV); export PYTHONPATH="$$PWD/spikes/s2-fabric-nat/src"; python spikes/s2-fabric-nat/run_simple_agent.py $(ARGS)

fabric-doctor:  ## Fabric pre-flight check (no LLM call)
	$(MAKE) fabric-agent ARGS=--doctor

sandbox-image:  ## build the OpenShell agent image (OpenShell must be installed, see spikes/s3-openshell/README.md)
	docker build -f spikes/s3-openshell/Dockerfile.agent -t agent-builder/s3-agent:0.1 spikes/s3-openshell

dev-shell:  ## shell in a container with all Python deps (no local Python needed)
	$(COMPOSE) --profile dev run --rm dev bash
