"""The local SDK server. Standard library only (no web framework to install); built for one user on one machine.

Security model: it binds to 127.0.0.1, every request needs the shared token in `X-AgentBuilder-Token` (the web app's
server holds it; browsers never see it), the `Host` header must be a loopback name (blocks DNS rebinding) and a request
that carries an `Origin` header (a browser page calling directly) is refused. Endpoints are listed in PLAN.md 16.12.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import sys
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agentbuilder import __version__
from agentbuilder.compile import CompiledAgent, CompileError, approval_needed, compile_agent, unapproved_live_tools
from agentbuilder.gateway import Gateway, LocalGateway
from agentbuilder.models import ProbeResult, probe_tool_calling, resolve_model
from agentbuilder.models.credentials import CredentialError, SecretStore
from agentbuilder.models.vault import LOOPBACK, TOKEN_HEADER
from agentbuilder.observe import Trajectory
from agentbuilder.runtime import Runner, RunnerNotInstalled, credential_env, load_runner
from agentbuilder.spec import AgentSpec, SpecError
from agentbuilder.tools import ToolCatalog

MAX_BODY = 1_000_000
MAX_RUNS = 50  # finished runs kept in memory
MAX_TEXT = 4000  # characters of one tool result shown in a trace


def _problem(text: str) -> dict[str, str]:
    field_name, sep, message = text.partition(": ")
    return {"field": field_name, "message": message} if sep else {"field": "", "message": text}


def trace_of(trajectory: Trajectory | None) -> dict[str, Any] | None:
    if trajectory is None:
        return None

    def clip(value: Any) -> Any:
        return value[:MAX_TEXT] + "…" if isinstance(value, str) and len(value) > MAX_TEXT else value

    return {
        "model": trajectory.model_name,
        "tools_used": trajectory.tools_used,
        "tokens": {
            "prompt": trajectory.prompt_tokens,
            "completion": trajectory.completion_tokens,
            "total": trajectory.total_tokens,
        },
        "steps": [
            {
                "id": s.id,
                "source": s.source,
                "model": s.model,
                "text": clip(s.text),
                "tokens": {"prompt": s.prompt_tokens, "completion": s.completion_tokens},
                "tool_calls": [
                    {"name": c.name, "arguments": c.arguments, "result": clip(c.result), "status": c.status}
                    for c in s.tool_calls
                ],
            }
            for s in trajectory.steps
        ],
    }


class _Invalid(Exception):
    """The request is well-formed JSON but not acceptable; `problems` are shown to the user as field messages."""

    def __init__(self, problems: list[dict[str, str]]) -> None:
        super().__init__(problems[0]["message"])
        self.problems = problems


@dataclass
class _Run:
    id: str
    status: str = "running"
    text: str | None = None
    error: str | None = None
    warnings: tuple[str, ...] = ()
    trace: dict[str, Any] | None = None

    def public(self) -> dict[str, Any]:
        return {
            "run_id": self.id,
            "status": self.status,
            "text": self.text,
            "error": self.error,
            "warnings": list(self.warnings),
            "trace": self.trace,
        }


@dataclass
class LocalServer:
    token: str
    catalog: ToolCatalog
    stores: Sequence[SecretStore] = ()
    runner_factory: Callable[[], Runner] = load_runner
    gateway: Gateway = field(default_factory=LocalGateway)
    audit_log: str | None = None  # one shared log of every tool call, written by the tool servers
    # Variables the server may resolve `env://` references from. Empty on purpose: a spec can name any variable and any
    # base_url, so reading the server's own environment would let a shared spec send it elsewhere.
    environ: Mapping[str, str] = field(default_factory=dict)
    _runs: OrderedDict[str, _Run] = field(default_factory=OrderedDict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=2))

    # ---- handlers: pure functions of (body) -> (status, json) -------------------------------------------------

    def health(self) -> tuple[int, Any]:
        try:
            self.runner_factory()
            runner = "ready"
        except RunnerNotInstalled:
            runner = "not installed"
        return 200, {"ok": True, "version": __version__, "runner": runner}

    def tools(self) -> tuple[int, Any]:
        listing = []
        for t in self.catalog.resolve(self.catalog.tool_ids):
            m = t.manifest
            listing.append(
                {
                    "id": t.id,
                    "description": m.description_plain,
                    "risk_tier": m.risk_tier,
                    "side_effects": m.side_effects,
                    "egress_hosts": m.egress_hosts,
                    "input_schema": m.input_schema,
                }
            )
        return 200, {"tools": listing}

    def _compile(self, spec_data: Any, catalog: ToolCatalog | None = None) -> tuple[AgentSpec, CompiledAgent]:
        if not isinstance(spec_data, Mapping):
            raise _Invalid([{"field": "spec", "message": "spec must be an object"}])
        try:
            spec = AgentSpec.from_dict(spec_data)
            return spec, compile_agent(spec, catalog or self.catalog)
        except SpecError as exc:
            raise _Invalid([_problem(p) for p in exc.problems]) from exc
        except CompileError as exc:
            raise _Invalid([{"field": "tools", "message": str(exc)}]) from exc

    def validate(self, body: Mapping[str, Any]) -> tuple[int, Any]:
        spec, compiled = self._compile(body.get("spec"))
        return 200, {
            "ok": True,
            "spec_yaml": spec.to_yaml(),
            "agent_mode": compiled.model.agent_mode,
            "tools": [t.id for t in compiled.tools],
            "warnings": compiled.warnings,
        }

    def check_model(self, body: Mapping[str, Any]) -> tuple[int, Any]:
        """The wizard's "Test connection": one real model call (the model check, PLAN 4.4.1). The reply says whether
        the endpoint, key and model work and whether the model can use tools; `agent_mode` is what to write."""
        model = body.get("model")
        if not isinstance(model, Mapping):
            raise _Invalid([{"field": "model", "message": "model must be an object"}])
        try:
            spec = AgentSpec.from_dict({"name": "model-check", "model": dict(model)})
            resolved = resolve_model(spec.model, environ=self.environ, stores=self.stores)
        except SpecError as exc:
            raise _Invalid([_problem(p) for p in exc.problems]) from exc
        except CredentialError as exc:
            raise _Invalid([{"field": "model.credential_ref", "message": str(exc)}]) from exc
        result: ProbeResult = probe_tool_calling(resolved)
        return 200, {
            "ok": result.ok,
            "tool_calling": result.tool_calling,
            "agent_mode": result.agent_mode,
            "message": result.message,
        }

    def start_run(self, body: Mapping[str, Any]) -> tuple[int, Any]:
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise _Invalid([{"field": "prompt", "message": "give the agent something to do"}])
        mock = body.get("mock", True)  # a test run never touches live systems unless the caller says so
        if not isinstance(mock, bool):
            raise _Invalid([{"field": "mock", "message": "mock must be true or false"}])
        try:
            catalog = self.gateway.apply(self.catalog, mock=mock, audit_log=self.audit_log)
        except ValueError as exc:
            raise _Invalid([{"field": "mock", "message": str(exc)}]) from exc
        spec, compiled = self._compile(body.get("spec"), catalog)
        if live := unapproved_live_tools(compiled):
            raise _Invalid([{"field": "mock", "message": approval_needed(live)}])
        run = _Run(id=uuid.uuid4().hex)
        with self._lock:
            if sum(r.status == "running" for r in self._runs.values()) >= MAX_RUNS:
                return 429, {"ok": False, "errors": [{"field": "", "message": "too many runs waiting; try again soon"}]}
            self._runs[run.id] = run
            for old_id in [i for i, r in self._runs.items() if r.status != "running"]:
                if len(self._runs) <= MAX_RUNS:
                    break
                del self._runs[old_id]  # only finished runs are forgotten, oldest first
        self._pool.submit(self._execute, run, spec, compiled, prompt)
        return 202, {"run_id": run.id}

    def _execute(self, run: _Run, spec: AgentSpec, compiled: CompiledAgent, prompt: str) -> None:
        try:
            env = credential_env(spec, compiled, environ=self.environ, stores=self.stores)
            result = self.runner_factory().run(compiled, prompt, environ=env)
            run.text, run.error, run.warnings, run.trace = (
                result.text,
                result.error,
                result.warnings,
                trace_of(result.trajectory),
            )
            run.status = result.status
        except (CredentialError, RunnerNotInstalled) as exc:
            run.error, run.status = str(exc), "failed"
        except Exception as exc:
            run.error, run.status = f"unexpected {type(exc).__name__}", "failed"

    def get_run(self, run_id: str) -> tuple[int, Any]:
        with self._lock:
            run = self._runs.get(run_id)
        return (
            (200, run.public())
            if run
            else (404, {"ok": False, "errors": [{"field": "run_id", "message": "unknown run"}]})
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def _handler(app: LocalServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "agentbuilder"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send(self, status: int, payload: Any) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _refuse(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            if host not in LOOPBACK:
                self._send(403, {"ok": False, "errors": [{"field": "", "message": "bad Host header"}]})
            elif self.headers.get("Origin"):
                self._send(403, {"ok": False, "errors": [{"field": "", "message": "browsers may not call this API"}]})
            elif not hmac.compare_digest(self.headers.get(TOKEN_HEADER, ""), app.token):
                self._send(401, {"ok": False, "errors": [{"field": "", "message": "missing or wrong token"}]})
            else:
                return False
            return True

        def _body(self) -> Mapping[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                self._send(
                    413 if length > MAX_BODY else 400,
                    {"ok": False, "errors": [{"field": "", "message": "bad body size"}]},
                )
                return None
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._send(400, {"ok": False, "errors": [{"field": "", "message": "body is not valid JSON"}]})
                return None
            if not isinstance(body, dict):
                self._send(400, {"ok": False, "errors": [{"field": "", "message": "body must be a JSON object"}]})
                return None
            return body

        def _guarded(self, handle: Callable[[], None]) -> None:
            """Any error a handler did not expect becomes a plain 500. Only the error's type is logged: its text could
            hold a provider reply, and a provider reply can hold a key."""
            try:
                handle()
            except Exception as exc:
                sys.stderr.write(f"agentbuilder server: unexpected {type(exc).__name__} on {self.path.split('?')[0]}\n")
                with contextlib.suppress(OSError):  # the client may be gone, or a reply may be half sent
                    self._send(500, {"ok": False, "errors": [{"field": "", "message": "unexpected server error"}]})

        def do_GET(self) -> None:
            self._guarded(self._get)

        def do_POST(self) -> None:
            self._guarded(self._post)

        def _get(self) -> None:
            if self._refuse():
                return
            path = self.path.split("?")[0]
            if path == "/health":
                self._send(*app.health())
            elif path == "/tools":
                self._send(*app.tools())
            elif path.startswith("/runs/"):
                self._send(*app.get_run(path.removeprefix("/runs/")))
            else:
                self._send(404, {"ok": False, "errors": [{"field": "", "message": "no such endpoint"}]})

        def _post(self) -> None:
            if self._refuse():
                return
            path = self.path.split("?")[0]
            routes = {"/spec/validate": app.validate, "/runs": app.start_run, "/model/check": app.check_model}
            if path not in routes:
                self._send(404, {"ok": False, "errors": [{"field": "", "message": "no such endpoint"}]})
                return
            body = self._body()
            if body is None:
                return
            try:
                self._send(*routes[path](body))
            except _Invalid as exc:
                self._send(422, {"ok": False, "errors": exc.problems})

    return Handler


def build_server(app: LocalServer, *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """A ready (not yet serving) HTTP server on a loopback address. `port=0` picks a free port."""
    if host not in LOOPBACK:
        raise ValueError("the SDK server only binds to the loopback interface")
    return ThreadingHTTPServer((host, port), _handler(app))
