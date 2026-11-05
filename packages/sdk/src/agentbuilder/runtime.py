"""Run a compiled agent. The core package defines only WHAT a runner is; runners ship separately (`agentbuilder-nat`
provides `local`) and register under the entry-point group `agentbuilder.runners`, so the core never imports NVIDIA
or LangChain packages.

    runner = load_runner("local")
    result = runner.run(compiled, "What is 17.5 plus 25?", environ=credential_env(spec, compiled))
    result.ok, result.text, result.trajectory.tools_used
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from importlib.metadata import entry_points
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from agentbuilder.compile.compiled import CompiledAgent
from agentbuilder.models.credentials import SecretStore, redact, resolve_credential
from agentbuilder.observe import Trajectory
from agentbuilder.spec import AgentSpec

RUNNER_GROUP = "agentbuilder.runners"


class RunnerNotInstalled(LookupError):
    """No runner with that name is installed."""


class RunResult(BaseModel):
    """What one run produced. `error` never contains a credential value."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    status: Literal["succeeded", "failed"]
    text: str | None = None
    error: str | None = None
    trajectory: Trajectory | None = None
    warnings: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"

    @property
    def total_tokens(self) -> int | None:
        return self.trajectory.total_tokens if self.trajectory else None


class Runner(Protocol):
    name: str

    def run(self, compiled: CompiledAgent, prompt: str, *, environ: Mapping[str, str] | None = None) -> RunResult: ...


def load_runner(name: str = "local") -> Runner:
    for ep in entry_points(group=RUNNER_GROUP):
        if ep.name == name:
            runner: Runner = ep.load()()
            return runner
    installed = sorted(ep.name for ep in entry_points(group=RUNNER_GROUP))
    raise RunnerNotInstalled(
        f"no runner named '{name}' is installed (installed: {installed or 'none'}); "
        'install one, for example: pip install "agentbuilder-nat"'
    )


def credential_env(
    spec: AgentSpec,
    compiled: CompiledAgent,
    *,
    environ: Mapping[str, str] | None = None,
    stores: Sequence[SecretStore] = (),
) -> dict[str, str]:
    """The environment a runner needs for the model key: {variable name: value}, or {} when the model needs no key.

    Resolves the spec's `credential_ref` (env:// from `environ`, secret:// from `stores`, e.g. the web vault).
    Raises CredentialError with a plain message when it cannot. The value is only ever placed in this dict."""
    name = compiled.model.api_key_env
    if not name or not spec.model.credential_ref:
        return {}
    secret = resolve_credential(
        spec.model.credential_ref, environ=os.environ if environ is None else environ, stores=stores
    )
    return {name: secret.reveal()} if secret else {}


def redact_values(text: str, env: Mapping[str, str]) -> str:
    return redact(text, list(env.values()))
