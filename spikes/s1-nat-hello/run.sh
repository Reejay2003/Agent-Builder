#!/usr/bin/env bash
# S1: run the NAT hello-world agent with an OpenRouter (OpenAI-compatible) model.
cd "$(dirname "$0")"
set -a; . ../../.env; set +a
. ../../.venv/bin/activate
nat run --config_file workflow.yml --input "${1:-What is the current date and time?}"
