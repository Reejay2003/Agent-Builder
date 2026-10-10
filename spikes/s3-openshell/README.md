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
