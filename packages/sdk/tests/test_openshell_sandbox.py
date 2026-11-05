"""The generated sandbox policy on a REAL OpenShell sandbox (microVM): declared hosts pass, everything else fails.

Needs a running gateway and the `agent-builder/s3-agent:0.1` image (spikes/s3-openshell); skipped otherwise.
Run with: pytest -m openshell
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from agentbuilder.compile import compile_agent, to_openshell_policy, to_openshell_yaml
from agentbuilder.spec import AgentSpec
from agentbuilder.tools import ToolCatalog, tool

pytestmark = pytest.mark.openshell
IMAGE = "agent-builder/s3-agent:0.1"  # built by spikes/s3-openshell
CURL = "/usr/bin/curl"
_EXTRA_PATH = [p for p in ("/Applications/Docker.app/Contents/Resources/bin", "/opt/homebrew/bin") if os.path.isdir(p)]
_ENV = {**os.environ, "PATH": os.pathsep.join([*_EXTRA_PATH, os.environ["PATH"]])}
_NOT_OUR_FAULT = ("Not authorized", "failed to resolve vm sandbox image", "connection refused")


def _openshell(*args: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["openshell", *args], capture_output=True, text=True, timeout=timeout, env=_ENV)


@pytest.fixture(scope="module", autouse=True)
def gateway() -> None:
    if not shutil.which("openshell", path=_ENV["PATH"]):
        pytest.skip("openshell is not installed")
    if "Connected" not in _openshell("status", timeout=30).stdout:
        pytest.skip("no OpenShell gateway is running")


@tool(namespace="web", description="Read the GitHub API.", egress_hosts=["api.github.com"])
def read_github(path: str) -> str:
    return ""


def _probe(policy_file: Path, url: str) -> tuple[str, str]:
    """Run curl inside a fresh sandbox; returns (curl exit code, http status)."""
    done = _openshell(
        "sandbox", "create", "--from", IMAGE, "--policy", str(policy_file), "--no-tty", "--no-keep", "--",
        "sh", "-c", f"curl -s -m 10 -o /dev/null -w 'http=%{{http_code}}' {url}; echo ' rc='$?",
    )  # fmt: skip
    found = re.search(r"http=(\d+) rc=(\d+)", done.stdout)
    if not found:
        output = (done.stdout + done.stderr)[-400:]
        if any(marker in output for marker in _NOT_OUR_FAULT):
            pytest.skip(f"sandbox image or gateway unavailable: {output}")
        pytest.fail(f"sandbox did not run the probe (a rejected policy lands here): {output}")
    return found.group(2), found.group(1)


def test_declared_host_is_reachable_and_everything_else_is_not():
    cat = ToolCatalog().add_tools("web", [read_github], command="python")
    spec = AgentSpec.from_dict(
        {
            "name": "x",
            "model": {"provider": "openai", "model": "m", "credential_ref": "env://K"},
            "tools": ["web.read_github"],
        }
    )
    policy = to_openshell_policy(compile_agent(spec, cat), binaries=[CURL])
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "policy.yaml"
        f.write_text(to_openshell_yaml(policy, "test"))
        allowed_rc, allowed_http = _probe(f, "https://api.github.com/zen")
        blocked_rc, _ = _probe(f, "https://example.com/")
    assert allowed_rc == "0" and allowed_http.startswith("2"), (allowed_rc, allowed_http)
    assert blocked_rc != "0"
