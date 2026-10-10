#!/usr/bin/env bash
# S3: allowed egress works, denied egress is blocked. Needs `openshell` installed and Docker running.
# Note: the exact `openshell sandbox create --policy` / exec syntax is checked against `openshell --help` first run.
set -u
export PATH="/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")"
NAME=s3-demo
openshell status || exit 1
time openshell sandbox create --name "$NAME" --from agent-builder/s3-sandbox:0.1 --policy policy.yaml --no-keep -- \
  sh -c 'echo "allowed:"; curl -s -o /dev/null -w "%{http_code}\n" https://openrouter.ai/api/v1/models;
         echo "denied:";  curl -s -m 8 -o /dev/null -w "%{http_code}\n" https://example.com || echo "blocked"'
openshell logs "$NAME" --since 5m --source sandbox | tail -20
openshell sandbox delete "$NAME"
