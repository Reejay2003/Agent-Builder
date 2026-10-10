#!/usr/bin/env bash
# Usage: ./run.sh "question"   (uses repo-root .venv and .env)
cd "$(dirname "$0")"
set -a; . ../../.env; set +a
. ../../.venv/bin/activate
Q="${1:-Who created Python, and what is the date today?}"
nat run --config_file workflow.yml --input "$Q"
