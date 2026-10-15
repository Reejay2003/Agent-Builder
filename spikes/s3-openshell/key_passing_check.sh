#!/usr/bin/env bash
# Proves OpenShell's key passing end to end with the CURRENT compute driver (run with the microVM driver):
#   host secret store -> sandbox sees only a placeholder -> the proxy substitutes the real key only for the allowed host
# and only for the allowed binaries. The real key is read from ../../.env (LLM_API_KEY) and is never printed.
set -u
export PATH="/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")"; mkdir -p results
PROV=openai-key
# the real key stays in OpenShell's credential store while the provider exists: remove it afterwards unless KEEP_PROVIDER=1
trap '[ "${KEEP_PROVIDER:-0}" = 1 ] || openshell provider delete "$PROV" >/dev/null 2>&1' EXIT
echo "== compute driver: $(openshell gateway info 2>&1 | grep -A1 'Compute drivers' | tail -1 | xargs)"
openshell provider profile import -f provider-openai.yaml --global >/dev/null 2>&1 || true
openshell provider delete "$PROV" >/dev/null 2>&1 || true
# the key goes through the environment of one command (not argv, not a file) and into OpenShell's credential store
OPENAI_API_KEY="$(python3 - <<'PY'
import re
for line in open("../../.env"):
    if line.startswith("LLM_API_KEY="):
        print(line.split("=", 1)[1].strip().strip('"').strip("'")); break
PY
)" openshell provider create --name "$PROV" --type openai --credential OPENAI_API_KEY >/dev/null 2>&1 \
  && echo "== provider $PROV created from the environment (value not shown)" || { echo "provider create FAILED"; exit 1; }
echo "== A. sandbox WITH the provider (microVM):"
openshell sandbox create --name keycheck --from agent-builder/s3-agent:0.1 --policy policy-agent.yaml --provider "$PROV" \
  --no-tty --no-keep -- python3 -c "$(cat key_probe.py)" > results/key-with-provider.txt 2>&1
grep -E "^K[0-9]" results/key-with-provider.txt | cut -c1-200
echo "== B. does the REAL key appear anywhere in what the sandbox could see (env, /proc, command lines, files)?"
python3 - <<'PY'
real = ""
for line in open("../../.env"):
    if line.startswith("LLM_API_KEY="):
        real = line.split("=", 1)[1].strip().strip('"').strip("'")
out = open("results/key-with-provider.txt", errors="replace").read()
print("   real key present in sandbox-visible output:", "YES  <-- LEAK" if real and real in out else "no")
print("   output size checked (chars):", len(out))
PY
echo "== C. sandbox WITHOUT the provider:"
openshell sandbox create --name keycheck2 --from agent-builder/s3-agent:0.1 --policy policy-agent.yaml \
  --no-tty --no-keep -- sh -c 'echo "OPENAI_API_KEY set: ${OPENAI_API_KEY:+yes}${OPENAI_API_KEY:-no}"; curl -s -m 8 -o /dev/null -w "api.openai.com http=%{http_code}\n" https://api.openai.com/v1/models' > results/key-no-provider.txt 2>&1
grep -E "OPENAI|http=" results/key-no-provider.txt | cut -c1-160
echo "== D. verdict:"
python3 key_verdict.py results/key-with-provider.txt results/key-no-provider.txt
