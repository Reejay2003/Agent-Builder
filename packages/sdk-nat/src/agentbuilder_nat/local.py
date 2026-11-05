"""LocalRunner: run a CompiledAgent on NAT through Fabric, on this machine, and read back the trajectory.

Fabric starts our adapter in a separate Python process that inherits THIS process's environment. So a run needs three
things in the environment (set here, restored afterwards): the model key under the variable the spec names,
ADAPTER_PYTHON (Fabric picks the adapter's Python from it, not from PATH) and an ABSOLUTE PYTHONPATH that contains our
adapter module (a relative one resolves against the adapter's own working directory and silently fails).

shortcut: runs are serialised by one lock because the environment is process-wide; two runs with different keys must not
overlap. Fine for a local, single-user UI; a sandboxed runner (Phase 2) does not have this limit.
"""

from __future__ import annotations

import asyncio
import glob
import os
import sys
import tempfile
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from agentbuilder.compile import CompiledAgent, to_fabric_config
from agentbuilder.observe import Trajectory, TrajectoryError, load
from agentbuilder.runtime import RunResult, redact_values

PACKAGE_SRC = Path(__file__).resolve().parents[1]  # the directory that holds agentbuilder_nat and nemo_fabric_adapters
ADAPTER_DIR = Path(__file__).resolve().parent / "adapter"  # descriptor + targets, as package data
_ENV_LOCK = threading.Lock()


@contextmanager
def _environment(updates: Mapping[str, str]) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _python_path() -> str:
    return os.pathsep.join(p for p in (str(PACKAGE_SRC), os.environ.get("PYTHONPATH", "")) if p)


class LocalRunner:
    name = "local"

    def __init__(self, *, keep_dir: str | os.PathLike[str] | None = None) -> None:
        """`keep_dir`: write run artifacts (events, trajectory) there instead of a temporary directory."""
        self._keep_dir = Path(keep_dir) if keep_dir else None

    def run(self, compiled: CompiledAgent, prompt: str, *, environ: Mapping[str, str] | None = None) -> RunResult:
        """Blocking run. Do not call from inside a running event loop (use `arun`)."""
        return asyncio.run(self.arun(compiled, prompt, environ=environ))

    async def arun(
        self, compiled: CompiledAgent, prompt: str, *, environ: Mapping[str, str] | None = None
    ) -> RunResult:
        env = dict(os.environ if environ is None else environ)
        key_name = compiled.model.api_key_env
        secrets = {key_name: env[key_name]} if key_name and key_name in env else {}
        if key_name and key_name not in secrets:
            return RunResult(
                status="failed",
                error=f"the model key is missing: set the environment variable {key_name} (or use secret:// with a "
                "vault) and run again",
            )
        if self._keep_dir:
            self._keep_dir.mkdir(parents=True, exist_ok=True)
            return await self._run_in(self._keep_dir, compiled, prompt, secrets)
        with tempfile.TemporaryDirectory(prefix="agentbuilder-run-") as tmp:
            return await self._run_in(Path(tmp), compiled, prompt, secrets)

    async def _run_in(self, out: Path, compiled: CompiledAgent, prompt: str, secrets: Mapping[str, str]) -> RunResult:
        try:
            import nemo_fabric  # imported here so `import agentbuilder_nat` works to list/describe without the stack
        except ImportError as exc:
            return RunResult(status="failed", error=f"NeMo Fabric is not installed: {exc}")
        config = nemo_fabric.FabricConfig.model_validate(
            to_fabric_config(compiled, adapter_dir=str(ADAPTER_DIR), relay_output_dir=str(out))
        )
        updates = {**secrets, "ADAPTER_PYTHON": sys.executable, "PYTHONPATH": _python_path()}
        # Take the lock in a worker thread: blocking here would freeze the event loop while another run holds it.
        await asyncio.to_thread(_ENV_LOCK.acquire)
        try:
            with _environment(updates):
                outcome = (await nemo_fabric.Fabric().run(config, base_dir=str(out), input=prompt)).to_mapping()
        except Exception as exc:  # noqa: BLE001  Fabric raises its own error types; whatever happens, the caller gets a RunResult
            return RunResult(status="failed", error=redact_values(f"{type(exc).__name__}: {exc}", secrets))
        finally:
            _ENV_LOCK.release()

        warnings: list[str] = []
        trajectory = _read_trajectory(out, warnings)
        text = (outcome.get("output") or {}).get("response")
        if outcome.get("status") == "succeeded":
            return RunResult(status="succeeded", text=text, trajectory=trajectory, warnings=tuple(warnings))
        error = outcome.get("error")
        return RunResult(
            status="failed",
            text=text,
            error=redact_values(str(error) if error else "the run failed without an error message", secrets),
            trajectory=trajectory,
            warnings=tuple(warnings),
        )


def _read_trajectory(out: Path, warnings: list[str]) -> Trajectory | None:
    files = sorted(glob.glob(str(out / "**" / "nemo-relay-atif-*.json"), recursive=True))
    if not files:
        warnings.append("the run wrote no trajectory file")
        return None
    try:
        return load(files[-1])
    except TrajectoryError as exc:
        warnings.append(f"the trajectory could not be read: {exc}")
        return None
