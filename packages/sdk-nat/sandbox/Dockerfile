# The OpenShell sandbox image for SandboxRunner: our SDK, adapter and tool servers on top of the spike image.
# Build from the repository root: make sandbox-image-sdk
# The code goes into site-packages (not PYTHONPATH): the micro-VM driver ignores ENV, and tool servers start with a
# cleaned environment, so only an installed package is importable everywhere.
FROM agent-builder/s3-agent:0.1
# Same pin as packages/sdk-nat/pyproject.toml: Relay writes the trajectory the host reads back.
RUN /opt/venv/bin/pip install --no-cache-dir -q nemo-relay==0.9.4
ARG SITE=/opt/venv/lib/python3.12/site-packages
COPY --chown=root:root packages/sdk/src/agentbuilder ${SITE}/agentbuilder
COPY --chown=root:root packages/sdk-nat/src/agentbuilder_nat ${SITE}/agentbuilder_nat
COPY --chown=root:root packages/sdk-nat/src/nemo_fabric_adapters ${SITE}/nemo_fabric_adapters
