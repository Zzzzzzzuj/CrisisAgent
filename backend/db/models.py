from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CrisisSession(Base):
    __tablename__ = "crisis_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    final_statement_preview: Mapped[str] = mapped_column(Text, default="")
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    checkpoint: Mapped["AgentCheckpoint | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoints"

    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    plan_id: Mapped[str] = mapped_column(String(128), default="")
    event: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    approval: Mapped[dict] = mapped_column(JSON, default=dict)
    failed_agents: Mapped[list] = mapped_column(JSON, default=list)
    current_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    session: Mapped[CrisisSession] = relationship(back_populates="checkpoint")


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"))
    agent: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    start_time: Mapped[str] = mapped_column(String(64), default="")
    end_time: Mapped[str] = mapped_column(String(64), default="")
    trace_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"))
    required: Mapped[bool] = mapped_column(default=False)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer: Mapped[str] = mapped_column(String(128), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"))
    evaluator: Mapped[str] = mapped_column(String(128), default="runtime")
    passed: Mapped[bool] = mapped_column(default=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

