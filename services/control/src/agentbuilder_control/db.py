"""Tables of the control service: agents, their immutable spec versions, and runs. SQLAlchemy 2; Postgres in
deployment (`postgresql+psycopg://...`), SQLite in unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(63), unique=True)  # the spec's slug name
    created_at: Mapped[datetime] = mapped_column(default=_now)
    versions: Mapped[list[AgentVersion]] = relationship(back_populates="agent", order_by="AgentVersion.version")


class AgentVersion(Base):
    """A spec as the SDK validated it. Never updated: a change is a new version, so a run always names what it ran."""

    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    version: Mapped[int]
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)  # normalised by the SDK (defaults filled in)
    spec_yaml: Mapped[str] = mapped_column(Text)  # written by the SDK, never by hand
    created_at: Mapped[datetime] = mapped_column(default=_now)
    agent: Mapped[Agent] = relationship(back_populates="versions")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    agent_version_id: Mapped[int] = mapped_column(ForeignKey("agent_versions.id", ondelete="CASCADE"))
    prompt: Mapped[str] = mapped_column(Text)
    mock: Mapped[bool]
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | succeeded | failed
    text: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    tools_used: Mapped[list[str]] = mapped_column(JSON, default=list)
    total_tokens: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    agent_version: Mapped[AgentVersion] = relationship()


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):  # tests: one in-memory database shared by every thread
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


def make_sessions(engine: Engine) -> sessionmaker:  # type: ignore[type-arg]
    Base.metadata.create_all(engine)  # shortcut: no migrations yet (Alembic when the schema first changes)
    return sessionmaker(engine, expire_on_commit=False)
