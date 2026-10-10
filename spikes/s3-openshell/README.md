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
