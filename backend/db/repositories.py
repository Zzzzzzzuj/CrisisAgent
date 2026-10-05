import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.core.state import AgentState, validate_state_status
from backend.db.models import (
    AgentCheckpoint,
    AgentTrace,
    Approval,
    AuditLog,
    CrisisSession,
)
from backend.db.session import get_session_factory


@dataclass(frozen=True)
class ExecutionLease:
    session_id: str
    owner: str
    fence: int
    expires_at: datetime


class StaleExecutionLease(RuntimeError):
    """The worker no longer owns the checkpoint it is trying to write."""


_CURRENT_LEASE: ContextVar[ExecutionLease | None] = ContextVar("runtime_execution_lease", default=None)


@contextmanager
def use_execution_lease(lease: ExecutionLease):
    token = _CURRENT_LEASE.set(lease)
    try:
        yield
    finally:
        _CURRENT_LEASE.reset(token)


class CheckpointRepository(Protocol):
    def save_checkpoint(self, state: AgentState) -> dict:
        ...

    def load_checkpoint(self, session_id: str) -> AgentState | None:
        ...

    def list_checkpoints(self) -> list[dict]:
        ...

    def delete_checkpoint(self, session_id: str) -> bool:
        ...

    def list_audit_logs(self, session_id: str | None = None) -> list[dict]:
        ...


class JSONCheckpointRepository:
    def __init__(self, checkpoint_path: str | Path):
        self.checkpoint_path = Path(checkpoint_path)

    def save_checkpoint(self, state: AgentState) -> dict:
        if _CURRENT_LEASE.get() is not None:
            raise NotImplementedError("A DB execution lease cannot write to a JSON checkpoint.")
        validate_state_status(state.status)
        data = self._read_checkpoint_data()
        state_data = state.to_dict()
        data[state.session_id] = state_data
        self._write_checkpoint_data(data)
        return state_data

    def claim_execution(self, session_id: str, kind: str, *, lease_seconds: int = 3600,
                        now: datetime | None = None) -> ExecutionLease | None:
        raise NotImplementedError("Execution leases require the DB-backed checkpoint repository.")

    def load_checkpoint(self, session_id: str) -> AgentState | None:
        state_data = self._read_checkpoint_data().get(session_id)
        if state_data is None:
            return None
        return AgentState.from_dict(state_data)

    def list_checkpoints(self) -> list[dict]:
        data = self._read_checkpoint_data()
        return [
            {
                "session_id": state_data.get("session_id", session_id),
                "plan_id": state_data.get("plan_id", ""),
                "event": state_data.get("event", ""),
                "status": state_data.get("status", ""),
                "created_time": _extract_created_time(state_data),
            }
            for session_id, state_data in sorted(data.items())
        ]

    def delete_checkpoint(self, session_id: str) -> bool:
        data = self._read_checkpoint_data()
        if session_id not in data:
            return False
        del data[session_id]
        self._write_checkpoint_data(data)
        return True

    def list_audit_logs(self, session_id: str | None = None) -> list[dict]:
        return []

    def _read_checkpoint_data(self) -> dict:
        if not self.checkpoint_path.exists():
            return {}

        try:
            data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        return data if isinstance(data, dict) else {}

    def _write_checkpoint_data(self, data: dict) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class SQLAlchemyCheckpointRepository:
    def __init__(self, session_factory: sessionmaker | None = None):
        self.session_factory = session_factory or get_session_factory()

    def claim_execution(self, session_id: str, kind: str, *, lease_seconds: int = 3600,
                        now: datetime | None = None) -> ExecutionLease | None:
        if kind not in {"dynamic", "resume"} or lease_seconds <= 0:
            raise ValueError("A valid execution kind and positive lease duration are required.")
        owner = str(uuid4())
        with self.session_factory() as db:
            now = now or db.execute(select(func.now())).scalar_one()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            expiry = now + timedelta(seconds=lease_seconds)
            statement = (
                update(AgentCheckpoint)
                .where(
                    AgentCheckpoint.session_id == session_id,
                    AgentCheckpoint.execution_kind == kind,
                    AgentCheckpoint.status.in_(("QUEUED", "RUNNING")),
                    or_(AgentCheckpoint.execution_owner.is_(None), AgentCheckpoint.lease_expires_at <= now),
                )
                .values(
                    execution_owner=owner,
                    lease_expires_at=expiry,
                    execution_fence=AgentCheckpoint.execution_fence + 1,
                )
            )
            if db.execute(statement.execution_options(synchronize_session=False)).rowcount != 1:
                return None
            fence = db.execute(
                select(AgentCheckpoint.execution_fence).where(AgentCheckpoint.session_id == session_id)
            ).scalar_one()
            db.commit()
        return ExecutionLease(session_id, owner, fence, expiry)

    def renew_execution(self, lease: ExecutionLease, *, lease_seconds: int = 3600,
                        now: datetime | None = None) -> ExecutionLease | None:
        if lease_seconds <= 0:
            raise ValueError("A positive lease duration is required.")
        with self.session_factory() as db:
            now = now or db.execute(select(func.now())).scalar_one()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            expiry = now + timedelta(seconds=lease_seconds)
            statement = (
                update(AgentCheckpoint)
                .where(
                    AgentCheckpoint.session_id == lease.session_id,
                    AgentCheckpoint.execution_owner == lease.owner,
                    AgentCheckpoint.execution_fence == lease.fence,
                    AgentCheckpoint.lease_expires_at > now,
                    AgentCheckpoint.status.in_(("QUEUED", "RUNNING")),
                )
                .values(lease_expires_at=expiry)
            )
            if db.execute(statement.execution_options(synchronize_session=False)).rowcount != 1:
                return None
            db.commit()
        return ExecutionLease(lease.session_id, lease.owner, lease.fence, expiry)

    def find_stale_executions(self, *, now: datetime | None = None, limit: int = 100) -> list[dict]:
        if limit <= 0:
            return []
        with self.session_factory() as db:
            now = now or db.execute(select(func.now())).scalar_one()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            rows = db.execute(
                select(AgentCheckpoint.session_id, AgentCheckpoint.execution_kind,
                       AgentCheckpoint.status, AgentCheckpoint.execution_fence)
                .where(
                    AgentCheckpoint.status.in_(("QUEUED", "RUNNING")),
                    or_(AgentCheckpoint.lease_expires_at <= now,
                        and_(AgentCheckpoint.execution_owner.is_(None),
                             AgentCheckpoint.lease_expires_at.is_(None))),
                )
                .order_by(AgentCheckpoint.updated_at, AgentCheckpoint.session_id)
                .limit(limit)
            ).all()
        return [dict(session_id=row.session_id, kind=row.execution_kind,
                     status=row.status, fence=row.execution_fence) for row in rows]

    def save_checkpoint(self, state: AgentState) -> dict:
        validate_state_status(state.status)
        state_data = state.to_dict()
        with self.session_factory() as db:
            self._upsert_session(db, state_data)
            db.flush()
            self._upsert_checkpoint(db, state_data)
            self._replace_traces(db, state.session_id, state.trace)
            self._record_approval_if_present(db, state_data)
            self._record_audit_logs_from_human_traces(db, state.session_id, state.trace)
            db.commit()
        return state_data

    def load_checkpoint(self, session_id: str) -> AgentState | None:
        with self.session_factory() as db:
            checkpoint = db.get(AgentCheckpoint, session_id)
            if checkpoint is None:
                return None
            return AgentState.from_dict(dict(checkpoint.state_payload or {}))

    def list_checkpoints(self) -> list[dict]:
        with self.session_factory() as db:
            rows = db.execute(select(AgentCheckpoint).order_by(AgentCheckpoint.session_id)).scalars().all()
            return [
                {
                    "session_id": row.session_id,
                    "plan_id": row.plan_id,
                    "event": row.event,
                    "status": row.status,
                    "created_time": row.created_at.isoformat() if row.created_at else "",
                    "created_by": {
                        "id": row.session.created_by_id if row.session else None,
                        "username": row.session.created_by_username if row.session else "",
                        "role": row.session.created_by_role if row.session else "",
                    },
                }
                for row in rows
            ]

    def delete_checkpoint(self, session_id: str) -> bool:
        with self.session_factory() as db:
            existing = db.get(CrisisSession, session_id)
            if existing is None:
                return False
            db.delete(existing)
            db.commit()
            return True

    def list_audit_logs(self, session_id: str | None = None) -> list[dict]:
        with self.session_factory() as db:
            statement = select(AuditLog)
            if session_id:
                statement = statement.where(AuditLog.session_id == session_id)
            rows = db.execute(statement.order_by(AuditLog.id)).scalars().all()
            return [
                {
                    "id": row.id,
                    "session_id": row.session_id,
                    "action": row.action,
                    "actor": row.actor,
                    "details": row.details,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
                for row in rows
            ]

    def _upsert_session(self, db: Session, state_data: dict) -> None:
        session_id = state_data["session_id"]
        row = db.get(CrisisSession, session_id)
        final_statement = (
            state_data.get("results", {})
            .get("decision", {})
            .get("final_statement", "")
        )
        scores = (
            state_data.get("results", {})
            .get("decision", {})
            .get("scores", {})
        )
        if row is None:
            row = CrisisSession(session_id=session_id)
            db.add(row)
        row.event = state_data.get("event", "")
        row.status = state_data.get("status", "")
        row.final_statement_preview = str(final_statement)[:160]
        row.scores = scores if isinstance(scores, dict) else {}
        created_by = (state_data.get("metadata", {}) or {}).get("created_by", {})
        if isinstance(created_by, dict):
            row.created_by_id = created_by.get("id")
            row.created_by_username = str(created_by.get("username", ""))
            row.created_by_role = str(created_by.get("role", ""))

    def _upsert_checkpoint(self, db: Session, state_data: dict) -> None:
        session_id = state_data["session_id"]
        lease = _CURRENT_LEASE.get()
        if lease is not None and lease.session_id != session_id:
            raise StaleExecutionLease("Execution lease belongs to another session.")
        row = db.get(AgentCheckpoint, session_id)
        values = {
            "plan_id": state_data.get("plan_id", ""),
            "event": state_data.get("event", ""),
            "status": state_data.get("status", ""),
            "results": state_data.get("results", {}),
            "trace": state_data.get("trace", []),
            "metadata_json": state_data.get("metadata", {}),
            "approval": state_data.get("approval", {}),
            "failed_agents": state_data.get("failed_agents", []),
            "current_agent": state_data.get("current_agent"),
            "state_payload": state_data,
            "execution_kind": _execution_kind(state_data),
        }
        if row is None:
            if lease is not None:
                raise StaleExecutionLease("Claimed checkpoint no longer exists.")
            row = AgentCheckpoint(session_id=session_id)
            db.add(row)
            for key, value in values.items():
                setattr(row, key, value)
            return
        condition = [AgentCheckpoint.session_id == session_id]
        if lease is None:
            condition.append(AgentCheckpoint.execution_owner.is_(None))
        else:
            condition.extend((AgentCheckpoint.execution_owner == lease.owner,
                              AgentCheckpoint.execution_fence == lease.fence,
                              AgentCheckpoint.lease_expires_at > func.now()))
            if state_data.get("status") in {"WAITING_HUMAN", "COMPLETED", "FAILED", "REJECTED"}:
                values.update(execution_owner=None, lease_expires_at=None)
        statement = update(AgentCheckpoint).where(*condition).values(**values)
        if db.execute(statement.execution_options(synchronize_session=False)).rowcount != 1:
            raise StaleExecutionLease("Checkpoint write rejected: execution ownership changed.")

    def _replace_traces(self, db: Session, session_id: str, trace: list) -> None:
        db.execute(delete(AgentTrace).where(AgentTrace.session_id == session_id))
        for item in trace:
            if not isinstance(item, dict):
                continue
            db.add(
                AgentTrace(
                    session_id=session_id,
                    agent=str(item.get("agent", "")),
                    status=str(item.get("status", "")),
                    start_time=str(item.get("start_time", "")),
                    end_time=str(item.get("end_time", "")),
                    trace_payload=item,
                )
            )

    def _record_approval_if_present(self, db: Session, state_data: dict) -> None:
        approval = state_data.get("approval", {})
        if not isinstance(approval, dict) or not approval.get("decision"):
            return
        db.add(
            Approval(
                session_id=state_data["session_id"],
                required=bool(approval.get("required")),
                decision=approval.get("decision"),
                reviewer=str(approval.get("reviewer", "")),
                reviewer_id=approval.get("reviewer_id"),
                reviewer_username=str(approval.get("reviewer_username", approval.get("reviewer", ""))),
                reviewer_role=str(approval.get("reviewer_role", "")),
                comment=str(approval.get("comment", "")),
                reason=str(approval.get("reason", "")),
                timestamp=approval.get("timestamp"),
            )
        )

    def _record_audit_logs_from_human_traces(self, db: Session, session_id: str, trace: list) -> None:
        existing_keys = {
            (
                row.action,
                str((row.details or {}).get("timestamp", "")),
            )
            for row in db.execute(select(AuditLog).where(AuditLog.session_id == session_id)).scalars()
        }
        for item in trace:
            if not isinstance(item, dict) or item.get("agent") != "human_gate":
                continue
            status = str(item.get("status", ""))
            if status not in {"approved", "rejected", "waiting_human"}:
                continue
            approval = (item.get("output") or {}).get("approval", {})
            timestamp = str(approval.get("timestamp", item.get("end_time", "")))
            audit_key = (status, timestamp)
            if audit_key in existing_keys:
                continue
            db.add(
                AuditLog(
                    session_id=session_id,
                    action=status,
                    actor=str(approval.get("reviewer_username", approval.get("reviewer", ""))),
                    details={
                        "comment": approval.get("comment", ""),
                        "reason": approval.get("reason", item.get("reason", "")),
                        "decision": approval.get("decision"),
                        "reviewer_id": approval.get("reviewer_id"),
                        "reviewer_username": approval.get("reviewer_username", approval.get("reviewer", "")),
                        "reviewer_role": approval.get("reviewer_role", ""),
                        "timestamp": timestamp,
                    },
                )
            )
            existing_keys.add(audit_key)


def _extract_created_time(state_data: dict) -> str:
    trace = state_data.get("trace", [])
    if not isinstance(trace, list):
        return ""
    for item in trace:
        if isinstance(item, dict) and item.get("start_time"):
            return str(item["start_time"])
    return ""


def _execution_kind(state_data: dict) -> str:
    metadata = state_data.get("metadata") or {}
    fact = metadata.get("human_fact") or {}
    approval = state_data.get("approval") or {}
    if isinstance(fact, dict) and isinstance(fact.get("response"), dict):
        return "resume"
    if approval.get("decision") == "approved":
        return "resume"
    return "dynamic"
