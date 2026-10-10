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

## Part 2: S2 agent inside the sandbox (in progress)
- `Dockerfile.agent` builds Python 3.12 + NAT 1.9.0 + Fabric 0.4.0 (pinned), `policy-agent.yaml` is filesystem/process only,
  `provider-openrouter.yaml` is NVIDIA's OpenRouter profile with `binaries` edited to our Python. The key is held by an OpenShell
  provider (`openshell provider create --name openrouter --type openrouter --from-existing`), not baked into the image.
- Reached: sandbox starts and the agent boots NAT. Fixed on the way: `/opt/agent` must be owned by uid 1000 (`COPY --chown`), and the
  image needs `nvidia-nat-langchain[all]` (langchain-openai).
- Blocked by: Mac disk full (139 MB free) which made Docker's VM read-only. Needs space freed and Docker Desktop restarted, then rerun:
  `openshell sandbox create --name s3-agent --from agent-builder/s3-agent:0.1 --policy policy-agent.yaml --provider openrouter --no-keep -- python /opt/agent/run_calculator.py`
