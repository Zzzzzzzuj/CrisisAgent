import json
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select
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
        validate_state_status(state.status)
        data = self._read_checkpoint_data()
        state_data = state.to_dict()
        data[state.session_id] = state_data
        self._write_checkpoint_data(data)
        return state_data

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
        row = db.get(AgentCheckpoint, session_id)
        if row is None:
            row = AgentCheckpoint(session_id=session_id)
            db.add(row)
        row.plan_id = state_data.get("plan_id", "")
        row.event = state_data.get("event", "")
        row.status = state_data.get("status", "")
        row.results = state_data.get("results", {})
        row.trace = state_data.get("trace", [])
        row.metadata_json = state_data.get("metadata", {})
        row.approval = state_data.get("approval", {})
        row.failed_agents = state_data.get("failed_agents", [])
        row.current_agent = state_data.get("current_agent")
        row.state_payload = state_data

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
