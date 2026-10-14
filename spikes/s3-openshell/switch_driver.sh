#!/usr/bin/env bash
# Switch the local OpenShell gateway (Homebrew service, macOS) between compute drivers.  Usage: ./switch_driver.sh docker|vm
# vm needs: e2fsprogs (brew install e2fsprogs) and Docker Desktop running (the VM driver finds local images through it).
# Backs up the previous gateway.toml next to it. Does not touch your sandboxes' images.
set -eu
export PATH="/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:$PATH"
D="${1:?usage: switch_driver.sh docker|vm}"; P="$(brew --prefix)/var/openshell"
cp -p "$P/gateway.toml" "$P/gateway.toml.bak-$(date +%Y%m%d-%H%M%S)"
case "$D" in
  docker) printf '[openshell]\nversion = 2\n\n[openshell.gateway]\ncompute_driver = "docker"\n' > "$P/gateway.toml.new" ;;
  vm)     printf '[openshell]\nversion = 2\n\n[openshell.gateway]\ncompute_driver = "vm"\n\n[openshell.drivers.vm]\nvcpus = 2\nmem_mib = 2048\n' > "$P/gateway.toml.new"
          printf 'DOCKER_HOST=unix:///Users/%s/.docker/run/docker.sock\n' "$USER" > "$P/gateway.env" ;;
  *) echo "driver must be docker or vm" >&2; exit 2 ;;
esac
openshell-gateway config preflight --path "$P/gateway.toml.new" >/dev/null
mv "$P/gateway.toml.new" "$P/gateway.toml"
brew services restart openshell >/dev/null
for _ in $(seq 1 15); do sleep 2; openshell status 2>&1 | grep -q Connected && break; done
openshell gateway info 2>&1 | grep -A1 "Compute drivers"
