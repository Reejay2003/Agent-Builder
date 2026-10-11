#!/usr/bin/env bash
# Usage: ./run.sh "question"   (uses repo-root .venv and .env)
cd "$(dirname "$0")"
set -a; . ../../.env; set +a
export LLM_API_KEY="${LLM_API_KEY:-$OPENROUTER_API_KEY}"  # falls back for older .env files
. ../../.venv/bin/activate
Q="${1:-Who created Python, and what is the date today?}"
nat run --config_file workflow.yml --input "$Q"
