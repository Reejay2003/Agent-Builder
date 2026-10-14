#!/usr/bin/env bash
# Run the egress probe in a fresh OpenShell sandbox with whichever compute driver the gateway is using.
# Usage: ./run_egress.sh <label>      (label e.g. docker or vm; output saved to results/egress-<label>.txt)
set -u
export PATH="/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")"; mkdir -p results
LABEL="${1:-run}"; NAME="egress-$LABEL-$$"
LAN_GW=$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}'); LAN_GW=${LAN_GW:-192.168.1.1}
PG_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' agent-builder-postgres-1 2>/dev/null); PG_IP=${PG_IP:-172.18.0.2}
SCRIPT=$(sed -e "s/__LAN_GW__/$LAN_GW/" -e "s/__PG_IP__/$PG_IP/" egress_probe.py)
START=$(python3 -c 'import time;print(time.time())')
openshell sandbox create --name "$NAME" --from agent-builder/s3-agent:0.1 --policy policy-egress.yaml --no-tty --no-keep -- python3 -c "$SCRIPT" 2>&1 | grep -v "Pulling image" | tee "results/egress-$LABEL.txt"
END=$(python3 -c 'import time;print(time.time())')
python3 -c "print('total wall time incl. sandbox create+delete: %.1fs' % ($END-$START))" | tee -a "results/egress-$LABEL.txt"
