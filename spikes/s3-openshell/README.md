# S3: OpenShell sandbox (egress part passed 2026-10-10)

OpenShell 0.1.3 (Apache-2.0), Docker driver on macOS M4 / 16 GB.

Run: `spikes/s3-openshell/test_egress.sh` (builds on `Dockerfile`: ubuntu 24.04 + curl).

Results:
- Allowed egress (openrouter.ai:443 via /usr/bin/curl) returned HTTP 200.
- Denied egress (example.com) blocked; log shows `NET:OPEN DENIED /usr/bin/curl -> example.com:443 [transparent_tcp_policy_denied]`.
- Start-up about 0.6 s per sandbox (image already local; first pull 8 s).
- RAM per idle sandbox about 24 MiB (supervisor 17 MiB + workload 6.5 MiB).

Gotchas:
- Docker Desktop needs Settings > Resources > Network > "Enable host networking", otherwise the supervisor cannot reach the gateway at 127.0.0.1:17670.
- Policy `run_as_user` must exist in the image; the default image has no user named `sandbox`, use numeric "1000".
- The default image has no curl/python; build your own and pass `--from`.
- Policies are enforced per binary path (the allow rule names /usr/bin/curl).

Not done yet: running the S2 Fabric + NAT run inside the sandbox. Needs an image with Python 3.12, nvidia-nat, nemo-fabric and the adapter, plus a policy allowing openrouter.ai for the python binary.

## Part 2: S2 agent inside the sandbox (passed 2026-10-10)
Fabric 0.4.0 (stable, pinned) + NAT 1.9.0 + the NAT adapter ran the calculator agent inside an OpenShell sandbox:
`RunResult.status = succeeded`, response "42.0", about 9.5 s end to end including the LLM call.

Files: `Dockerfile.agent`, `policy-agent.yaml` (filesystem/process only), `provider-openrouter.yaml` (NVIDIA's OpenRouter profile,
`binaries` edited to our Python). Run:
```
openshell provider profile import -f provider-openrouter.yaml --global
set -a; . ../../.env; set +a; openshell provider create --name openrouter --type openrouter --from-existing
docker build -f Dockerfile.agent -t agent-builder/s3-agent:0.1 .
openshell sandbox create --name s3-run --from agent-builder/s3-agent:0.1 --policy policy-agent.yaml --provider openrouter --no-tty --no-keep -- python /opt/agent/run_calculator.py
```
Containment checks from Python inside that sandbox:
- openrouter.ai:443 allowed (HTTP 200); example.com and api.github.com blocked (Permission denied).
- `OPENROUTER_API_KEY` inside the sandbox is a placeholder (`openshel...`), not the real key; OpenShell substitutes it for openrouter.ai only.

Gotchas found:
- `COPY --chown=1000:1000` so the sandbox user can write `/opt/agent`; the image needs `nvidia-nat-langchain[all]`.
- A Docker build during a full disk silently produced 0-byte files and a bad image; rebuild with `--no-cache` after freeing space.
- `--no-keep` sandboxes delete on exit and may keep their name for a few seconds ("already exists").
- Pin `nemo-fabric==0.4.0`; installing with `--prerelease=allow` pulls 0.5.0b3.
- Plan impact: per-tool egress via provider profiles (binaries + host) fits compiler C; secrets never enter the sandbox.

## Part 3: Docker driver vs MicroVM driver, egress compared (2026-10-14)
Probe: `egress_probe.py` runs inside a sandbox (policy `policy-egress.yaml`: only `/usr/bin/curl` may reach `openrouter.ai:443`) and tries 16 things that must be blocked plus 2 that must work: proxy bypass (`curl --noproxy`), IP literals, a non-allowed binary (python) to the allowed host, raw TCP, UDP DNS to 8.8.8.8 (exfil path), the Mac's own Postgres on 127.0.0.1, `host.docker.internal`, the OpenShell gateway port, the home-LAN gateway, the cloud-metadata IP, a neighbouring Docker container (172.18.0.2:5432) and Docker Desktop VM internals. Run: `./run_egress.sh <label>`; switch drivers with `./switch_driver.sh docker|vm`.

| | Docker driver | MicroVM driver (libkrun) |
|---|---|---|
| Egress tests (16 must-block, 2 must-work) | **all pass, no leaks** | **all pass, no leaks** (identical results and error codes) |
| Network interfaces the sandbox sees | `lo` plus 9 tunnel devices of the shared Docker Desktop kernel | **`lo` only** (no NIC; traffic leaves through the host supervisor) |
| Kernel shared with other workloads | yes (Docker Desktop VM, same kernel as your Postgres container) | **no** (own VM kernel) |
| Denial log format | `NET:OPEN DENIED /usr/bin/curl -> example.com:443 [transparent_tcp_policy_denied]` | identical (same supervisor code) |
| First start (image export, disk format) | about 4 s | **about 40 s** (once per image) |
| Warm start (create to exit) | about 0.6 s | about 6 s |
| Memory per idle sandbox | about 24 MiB | about 180 MiB (VM process; 2 vCPU, 2 GiB configured) |

**Reading:** the policy engine, not the driver, decides egress, so outcomes are the same. The MicroVM upgrade is **defense in depth**: if the policy is wrong or a kernel/container-escape bug exists, a VM has no network device to misuse and no shared kernel with neighbours. Cost: about 10x slower warm start and about 8x the memory. Suggested use: Docker driver for development and tests, MicroVM for untrusted tools and production-like runs; make the driver a setting in the SDK's `SandboxRunner`.
Not tested: a deliberately over-permissive policy under each driver; GPU; many concurrent VMs; Linux hosts.

Setup needed for the MicroVM driver on macOS (all done on this machine):
1. `brew install e2fsprogs` (the driver builds ext4 disks; the gateway preflight names the missing tools).
2. `compute_driver = "vm"` and a `[openshell.drivers.vm]` table in `$(brew --prefix)/var/openshell/gateway.toml`; the VM driver is opt-in and never auto-detected.
3. `DOCKER_HOST=unix:///Users/<you>/.docker/run/docker.sock` in `$(brew --prefix)/var/openshell/gateway.env` so the VM driver can find local Docker Desktop images (macOS has no `/var/run/docker.sock` by default; without this it tries Docker Hub and fails with "Not authorized").
4. `brew services restart openshell`. `openshell gateway info` should list `vm`. Docker Desktop must stay running.

## Part 4: key passing on the MicroVM driver (2026-10-15)
OpenShell's provider feature keeps API keys OUT of the sandbox. Verified end to end with your OpenAI key on the `vm` driver: `./key_passing_check.sh` (9 checks, exit code 0 only if all hold; `key_verdict.py` is the judge).

Flow: the key is read from `.env` into the environment of ONE command (`openshell provider create --type openai --credential OPENAI_API_KEY`, never argv or a file) -> OpenShell's credential store -> sandbox created with `--provider openai-key` -> the agent sees only a placeholder (`openshell:...`, 56 characters) -> the supervisor proxy swaps in the real key on requests to `api.openai.com:443` from the allowed binaries only.

| Check | Result |
|---|---|
| Sandbox env var is a placeholder, not the key | PASS |
| Python and curl reach `api.openai.com` (HTTP 200, key injected by the proxy) | PASS |
| The key is not sent to another host (`example.com`, curl and python) | PASS, blocked |
| The real key appears nowhere the sandbox can read: env, `/proc/*/environ`, `/proc/*/cmdline`, home, `/sandbox` | PASS (host-side search of the dump) |
| Sandbox network interfaces | `lo` only |
| Sandbox WITHOUT the provider | no key variable; `api.openai.com` unreachable |
| Real agent end to end: Fabric 0.4.0 + NAT 1.9.0 calculator agent inside a VM sandbox, real OpenAI call | `succeeded`, response `42`, agent process saw only the placeholder; about 15 s including VM start |
| VM, not a container | `openshell gateway info` lists `vm`; no sandbox container in `docker ps -a`; the `openshell-driver-vm` process runs |

**Design rules learned**
- **Allowed-binary rules follow process ancestry.** `bash` alone is BLOCKED for `api.openai.com`, but `bash` started by the allowed `python` is OPEN. It can only reach the same allowed host and still only holds the placeholder, but it means an agent with a shell tool can use the allowed host through a child process. Keep shell tools out of agents that hold provider access, and allow only the runtime binary in the profile.
- **The MicroVM driver does not apply the image's Dockerfile `ENV`.** `PATH` and `PYTHONPATH` were unset (`python` not found, exit 127). A sandbox runner must set `PATH`, `PYTHONPATH` and `ADAPTER_PYTHON` explicitly or use absolute paths.
- The provider stays in OpenShell's credential store (holding the real key) until deleted; the check script deletes it on exit unless `KEEP_PROVIDER=1`.
- Adapted profile: `provider-openai.yaml` (NVIDIA's `providers/openai.yaml` with `binaries` set to our Python and curl).
- Not checked: whether OpenShell encrypts the store at rest; keys that agents must put in request bodies instead of headers (the profile injects a bearer header only).
