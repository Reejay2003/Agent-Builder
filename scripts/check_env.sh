#!/usr/bin/env bash
# Checks that this machine can run the project. Prints OK / MISSING / WARN lines, exits 1 if anything required is missing.
cd "$(dirname "$0")/.."
export PATH="/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"
fail=0
ok()   { printf "  OK       %s\n" "$1"; }
miss() { printf "  MISSING  %s\n" "$1"; fail=1; }
warn() { printf "  WARN     %s\n" "$1"; }

py=""; for p in python3.12 python3.13 python3.11; do command -v $p >/dev/null && { py=$p; break; }; done
if [ -n "$py" ]; then ok "python $($py --version | awk '{print $2}') ($py)"
elif command -v uv >/dev/null; then ok "uv installed (make setup will fetch Python 3.12)"
else miss "Python 3.11-3.13 or uv (python3 here is $(python3 --version 2>&1); NAT does not support 3.14)"; fi

if command -v docker >/dev/null && docker info >/dev/null 2>&1; then ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"
else miss "docker (install Docker Desktop and start it)"; fi

[ -f .env ] && ok ".env exists" || miss ".env (run: make env)"
if [ -f .env ]; then
  grep -q '^POSTGRES_PASSWORD=change-me' .env && warn "POSTGRES_PASSWORD is still the default"
  grep -Eq '^OPENROUTER_API_KEY=.+' .env && ok "OPENROUTER_API_KEY set" || warn "OPENROUTER_API_KEY empty (LLM runs will fail)"
fi

if [ -x .venv/bin/python ] && .venv/bin/python -c "import nat, nemo_fabric" 2>/dev/null; then
  ok "venv: nat $(.venv/bin/pip list 2>/dev/null | awk '/^nvidia-nat-core /{print $2}'), nemo-fabric $(.venv/bin/pip list 2>/dev/null | awk '/^nemo-fabric /{print $2}')"
else miss ".venv with dependencies (run: make setup)"; fi

if docker info >/dev/null 2>&1; then
  n=$(docker compose -f deploy/compose/docker-compose.yml --env-file .env ps --status running -q 2>/dev/null | wc -l | tr -d ' ')
  [ "$n" -ge 2 ] && ok "compose services running ($n)" || warn "compose services not running (run: make up)"
fi

command -v openshell >/dev/null && ok "openshell $(openshell --version 2>/dev/null | head -1)" || warn "openshell not installed (only needed for sandbox spikes, see spikes/s3-openshell/README.md)"
exit $fail
