"""SandboxRunner: runs the agent INSIDE an OpenShell microVM (SDK 0.3 row of the PLAN roadmap).

What the sandbox gets: a network policy generated from the tools' declared hosts (compiler C), a read-only system, and
the model key only as OpenShell's placeholder. The real key lives in an OpenShell provider created for this one run
(through the environment of one command, never argv or a file) and deleted afterwards; the proxy adds it to requests to
the model host only.

Needs: the `openshell` CLI, a running gateway, and the image built by `make sandbox-image-sdk`.
Limits (stated, not hidden): only the SDK's own tool servers (`python -m agentbuilder.library.server ...`) can run in the
sandbox, because other servers are programs on this machine; the audit log is not collected.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

from agentbuilder.compile import (
    approval_needed,
    to_openshell_policy,
    to_openshell_provider_profile,
    to_openshell_yaml,
    unapproved_live_tools,
)
from agentbuilder.compile.compiled import CompiledAgent
from agentbuilder.models.credentials import redact
from agentbuilder.runtime import RunResult

from agentbuilder_nat.sandbox_main import MARKER

IMAGE = "agent-builder/sdk-agent:0.1"
SANDBOX_PYTHON = "/opt/venv/bin/python"
_SDK_SERVER = ["-m", "agentbuilder.library.server"]

Run = Callable[..., "subprocess.CompletedProcess[str]"]


def _sandbox_servers(compiled: CompiledAgent) -> tuple[CompiledAgent | None, list[str], str]:
    """The agent with its tool servers pointed at the image's Python, or (None, [], why not)."""
    servers, notes = [], []
    for s in compiled.servers:
        if s.args[:2] != _SDK_SERVER:
            return (
                None,
                [],
                (
                    f"tool server '{s.name}' is a program on this machine, so it cannot run in the sandbox yet; "
                    "only the SDK's own tools (Gmail, Calendar, Sheets, web search) can"
                ),
            )
        args = list(s.args)
        if "--log" in args:  # a host path means nothing in the sandbox
            i = args.index("--log")
            del args[i : i + 2]
            notes.append("the tool-call audit log is not collected from the sandbox yet")
        servers.append(s.model_copy(update={"command": SANDBOX_PYTHON, "args": args}))
    return compiled.model_copy(update={"servers": servers}), notes, ""


class SandboxRunner:
    name = "sandbox"

    def __init__(self, *, image: str = IMAGE, timeout: int = 300, run: Run | None = None) -> None:
        self._image, self._timeout = image, timeout
        self._run: Run = run or (lambda *a, **kw: subprocess.run(*a, capture_output=True, text=True, check=False, **kw))

    def _openshell(
        self, *args: str, env: Mapping[str, str] | None = None, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self._run(["openshell", *args], input=stdin, timeout=self._timeout, env={**os.environ, **(env or {})})

    def run(self, compiled: CompiledAgent, prompt: str, *, environ: Mapping[str, str] | None = None) -> RunResult:
        if live := unapproved_live_tools(compiled):
            return RunResult(status="failed", error=approval_needed(live))
        remote, notes, why = _sandbox_servers(compiled)
        if remote is None:
            return RunResult(status="failed", error=why)
        env = dict(os.environ if environ is None else environ)
        key_name = remote.model.api_key_env
        if key_name and key_name not in env:
            return RunResult(
                status="failed", error=f"the model key is missing: set the environment variable {key_name}"
            )
        secrets = [env[key_name]] if key_name else []
        self._sweep()
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:4]}"  # time lets a later run spot leftovers; OpenShell names: at most 19
        provider = f"ab-{run_id}" if key_name else None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                return self._run_in_sandbox(remote, prompt, env, key_name, provider, run_id, Path(tmp), notes)
        except (OSError, subprocess.SubprocessError) as exc:  # no openshell, a hung sandbox, a dead gateway
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                self._openshell("sandbox", "delete", f"ab-{run_id}")  # a timeout must not leave the VM running
            return RunResult(status="failed", error=redact(f"{type(exc).__name__}: {exc}", secrets))
        finally:
            if provider:
                self._openshell("provider", "delete", provider)  # the real key must not outlive the run

    def _sweep(self) -> None:
        """Delete per-run providers a killed run left behind (each holds a real key). Only ones older than the run
        timeout are touched, so a run still going in another process keeps its provider."""
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            listing = self._openshell("provider", "list").stdout or ""
            for name, started in re.findall(r"^(ab-(\d{10})-[0-9a-f]{4})\s", listing, re.MULTILINE):
                if time.time() - int(started) > self._timeout + 120:
                    self._openshell("provider", "delete", name)

    def _run_in_sandbox(
        self,
        c: CompiledAgent,
        prompt: str,
        env: Mapping[str, str],
        key_name: str | None,
        provider: str | None,
        run_id: str,
        tmp: Path,
        notes: list[str],
    ) -> RunResult:
        secrets = [env[key_name]] if key_name else []
        binaries = ["/usr/bin/python3.12", SANDBOX_PYTHON]
        policy = to_openshell_policy(c, binaries=binaries, read_only=["/usr", "/lib", "/etc", "/opt/venv"])
        (tmp / "policy.yaml").write_text(to_openshell_yaml(policy, "sandbox policy"))
        provider_args: list[str] = []
        if provider and key_name:
            profile = to_openshell_provider_profile(c, binaries=binaries)
            assert profile is not None  # a key variable means the model has a profile
            (tmp / "profile.yaml").write_text(to_openshell_yaml(profile, "provider profile"))
            self._openshell("provider", "profile", "import", "-f", str(tmp / "profile.yaml"), "--global")
            made = self._openshell(
                "provider", "create", "--name", provider, "--type", profile["id"], "--credential", key_name,
                env={key_name: env[key_name]},
            )  # fmt: skip
            if made.returncode != 0:
                return RunResult(
                    status="failed", error=redact(f"could not set up the model key: {made.stderr[-300:]}", secrets)
                )
            provider_args = ["--provider", provider]
        # One JSON line on standard input, not an argument: arguments show up in `ps` for every user of this machine.
        # (OpenShell forwards stdin but not its end, so the reader takes exactly one line.)
        payload = json.dumps({"compiled": c.model_dump(mode="json"), "prompt": prompt}) + "\n"
        done = self._openshell(
            "sandbox", "create", "--name", f"ab-{run_id}", "--from", self._image, "--policy", str(tmp / "policy.yaml"),
            *provider_args, "--no-tty", "--no-keep", "--",
            SANDBOX_PYTHON, "-m", "agentbuilder_nat.sandbox_main",
            stdin=payload,
        )  # fmt: skip
        found = re.search(rf"^{re.escape(MARKER)}(.+)$", done.stdout or "", re.MULTILINE)
        if not found:
            tail = redact(((done.stdout or "") + (done.stderr or ""))[-400:], secrets)
            return RunResult(status="failed", error=f"the sandbox produced no result: {tail}")
        result = RunResult.model_validate_json(found.group(1))
        return result.model_copy(update={"warnings": (*result.warnings, *notes)})
