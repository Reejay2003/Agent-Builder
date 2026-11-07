"""The control service (PLAN 4 "Control" plane, tracker P1.6): stores AgentSpecs as immutable versions and runs them.

It is a client of the SDK's public API only: the SDK validates and compiles every spec before it is stored, and the
SDK's runners execute runs. Same access rules as the local SDK server: loopback only, a shared token in
`X-AgentBuilder-Token`, and any request from a browser (`Origin` header) is refused. Real user auth (Keycloak or local
accounts) and tenants come later.

    POST /agents                           {"spec": {...}}          201 version 1; 409 if the name exists
    GET  /agents                                                    names with their latest version
    GET  /agents/{name}                                             the latest version
    POST /agents/{name}/versions           {"spec": {...}}          201 the next version (the name must match)
    GET  /agents/{name}/versions/{n}                                one version
    POST /agents/{name}/runs               {"prompt", "mock"?, "version"?}  202 {run_id}; mock defaults to true
    GET  /runs/{id}                                                 status, answer, tools used, the version it ran
"""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from agentbuilder.compile import CompileError, compile_agent, unapproved_live_tools
from agentbuilder.gateway import LocalGateway
from agentbuilder.models.credentials import CredentialError
from agentbuilder.runtime import Runner, RunnerNotInstalled, credential_env, load_runner
from agentbuilder.spec import AgentSpec, SpecError
from agentbuilder.tools import ToolCatalog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from agentbuilder_control.db import Agent, AgentVersion, Run, make_engine, make_sessions

TOKEN_HEADER = "X-AgentBuilder-Token"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class SpecBody(BaseModel):
    spec: dict[str, Any]


class RunBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    mock: bool = True  # a run never touches live systems unless the caller says so
    version: int | None = Field(None, ge=1)


def _problem(status: int, message: str, field: str = "") -> HTTPException:
    return HTTPException(status, detail=[{"field": field, "message": message}])


def _version_view(agent: Agent, v: AgentVersion) -> dict[str, Any]:
    return {"name": agent.name, "version": v.version, "spec": v.spec, "spec_yaml": v.spec_yaml,
            "created_at": v.created_at.isoformat()}  # fmt: skip


def create_app(
    database_url: str,
    token: str,
    *,
    catalog_factory: Callable[[], ToolCatalog] | None = None,
    runner_factory: Callable[[], Runner] = load_runner,
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    """`environ`: where `env://` keys come from; empty by default, like the SDK server (a stored spec must not be able
    to name and read any variable of this process)."""
    sessions: sessionmaker[Session] = make_sessions(make_engine(database_url))
    pool = ThreadPoolExecutor(max_workers=2)
    env = dict(environ or {})

    def catalog() -> ToolCatalog:
        if catalog_factory:
            return catalog_factory()
        from agentbuilder.library import personal_catalog

        return personal_catalog()

    app = FastAPI(title="Agent Builder control service", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def guard(request: Request, call_next: Callable[..., Any]) -> Any:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in LOOPBACK or request.headers.get("origin"):
            return JSONResponse({"ok": False, "errors": [{"field": "", "message": "not allowed"}]}, status_code=403)
        if not hmac.compare_digest(request.headers.get(TOKEN_HEADER, ""), token):
            return JSONResponse({"ok": False, "errors": [{"field": "", "message": "missing or wrong token"}]}, 401)
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def errors(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"ok": False, "errors": exc.detail}, status_code=exc.status_code)

    def db() -> Any:
        with sessions() as s:
            yield s

    def checked(data: dict[str, Any]) -> tuple[AgentSpec, str]:
        """The SDK's verdict: a valid spec that compiles against the tool catalog, and the YAML it writes."""
        try:
            spec = AgentSpec.from_dict(data)
            compile_agent(spec, catalog())
        except SpecError as exc:
            raise HTTPException(422, detail=[_split(p) for p in exc.problems]) from exc
        except CompileError as exc:
            raise _problem(422, str(exc), "tools") from exc
        return spec, spec.to_yaml()

    def agent_or_404(s: Session, name: str) -> Agent:
        agent = s.scalar(select(Agent).where(Agent.name == name))
        if agent is None:
            raise _problem(404, "unknown agent", "name")
        return agent

    @app.post("/agents", status_code=201)
    def create_agent(body: SpecBody, s: Session = Depends(db)) -> dict[str, Any]:  # noqa: B008
        spec, yaml_text = checked(body.spec)
        agent = Agent(name=spec.name)
        version = AgentVersion(agent=agent, version=1, spec=spec.model_dump(mode="json"), spec_yaml=yaml_text)
        s.add_all([agent, version])
        try:
            s.commit()
        except IntegrityError as exc:
            raise _problem(409, f"an agent named {spec.name!r} already exists; add a version instead", "name") from exc
        return _version_view(agent, version)

    @app.get("/agents")
    def list_agents(s: Session = Depends(db)) -> dict[str, Any]:  # noqa: B008
        latest = (
            select(Agent.name, func.max(AgentVersion.version))
            .join(AgentVersion)
            .group_by(Agent.name)
            .order_by(Agent.name)
        )
        return {"agents": [{"name": n, "latest_version": v} for n, v in s.execute(latest)]}

    @app.get("/agents/{name}")
    def get_agent(name: str, s: Session = Depends(db)) -> dict[str, Any]:  # noqa: B008
        agent = agent_or_404(s, name)
        return _version_view(agent, agent.versions[-1])

    @app.post("/agents/{name}/versions", status_code=201)
    def add_version(name: str, body: SpecBody, s: Session = Depends(db)) -> dict[str, Any]:  # noqa: B008
        agent = agent_or_404(s, name)
        spec, yaml_text = checked(body.spec)
        if spec.name != name:
            raise _problem(422, f"the spec is named {spec.name!r}, not {name!r}", "spec.name")
        number = (s.scalar(select(func.max(AgentVersion.version)).where(AgentVersion.agent_id == agent.id)) or 0) + 1
        version = AgentVersion(agent=agent, version=number, spec=spec.model_dump(mode="json"), spec_yaml=yaml_text)
        s.add(version)
        try:
            s.commit()  # two writers picking the same number: the unique constraint stops the second
        except IntegrityError as exc:
            raise _problem(409, "another version was saved at the same moment; retry", "version") from exc
        return _version_view(agent, version)

    @app.get("/agents/{name}/versions/{number}")
    def get_version(name: str, number: int, s: Session = Depends(db)) -> dict[str, Any]:  # noqa: B008
        agent = agent_or_404(s, name)
        version = next((v for v in agent.versions if v.version == number), None)
        if version is None:
            raise _problem(404, "unknown version", "version")
        return _version_view(agent, version)

    @app.post("/agents/{name}/runs", status_code=202)
    def start_run(name: str, body: RunBody, s: Session = Depends(db)) -> dict[str, Any]:  # noqa: B008
        agent = agent_or_404(s, name)
        version = (
            agent.versions[-1]
            if body.version is None
            else next((v for v in agent.versions if v.version == body.version), None)
        )
        if version is None:
            raise _problem(404, "unknown version", "version")
        spec = AgentSpec.from_dict(version.spec)
        try:
            tools = LocalGateway().apply(catalog(), mock=body.mock)
        except ValueError as exc:
            raise _problem(422, str(exc), "mock") from exc
        compiled = compile_agent(spec, tools)
        if live := unapproved_live_tools(compiled):  # nobody to ask here yet: refuse instead of acting unasked
            raise _problem(422, f"live runs of {', '.join(live)} need human approval; run in mock mode", "mock")
        run = Run(id=uuid.uuid4().hex, agent_version_id=version.id, prompt=body.prompt, mock=body.mock)
        s.add(run)
        s.commit()
        pool.submit(_execute, sessions, run.id, spec, compiled, body.prompt, runner_factory, env)
        return {"run_id": run.id, "version": version.version}

    @app.get("/runs/{run_id}")
    def get_run(run_id: str, s: Session = Depends(db)) -> dict[str, Any]:  # noqa: B008
        run = s.get(Run, run_id)
        if run is None:
            raise _problem(404, "unknown run", "run_id")
        return {
            "run_id": run.id, "agent": run.agent_version.agent.name, "version": run.agent_version.version,
            "status": run.status, "mock": run.mock, "text": run.text, "error": run.error,
            "tools_used": run.tools_used, "total_tokens": run.total_tokens,
        }  # fmt: skip

    app.state.shutdown = lambda: pool.shutdown(wait=True, cancel_futures=False)
    return app


def _split(problem: str) -> dict[str, str]:
    field, sep, message = problem.partition(": ")
    return {"field": field, "message": message} if sep else {"field": "", "message": problem}


def _execute(
    sessions: sessionmaker[Session],
    run_id: str,
    spec: AgentSpec,
    compiled: Any,
    prompt: str,
    runner_factory: Callable[[], Runner],
    environ: Mapping[str, str],
) -> None:
    try:
        result = runner_factory().run(compiled, prompt, environ=credential_env(spec, compiled, environ=environ))
        update: dict[str, Any] = {
            "status": result.status, "text": result.text, "error": result.error,
            "tools_used": list(result.trajectory.tools_used) if result.trajectory else [],
            "total_tokens": result.total_tokens,
        }  # fmt: skip
    except (CredentialError, RunnerNotInstalled) as exc:
        update = {"status": "failed", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001  the run row must never stay "running" forever
        update = {"status": "failed", "error": f"unexpected {type(exc).__name__}"}
    with sessions() as s:
        run = s.get(Run, run_id)
        if run is not None:
            for key, value in update.items():
                setattr(run, key, value)
            run.finished_at = datetime.now(UTC)
            s.commit()
