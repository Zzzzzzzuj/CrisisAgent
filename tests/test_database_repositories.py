import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.core.human import approve, reject, request_review
from backend.core.state import REJECTED, WAITING_HUMAN, AgentState
from backend.db.repositories import SQLAlchemyCheckpointRepository
from backend.db.session import Base


@pytest.fixture()
def repository():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return SQLAlchemyCheckpointRepository(session_factory=session_factory)


def test_sqlalchemy_repository_saves_and_restores_checkpoint(repository):
    state = AgentState(session_id="session-db-1", plan_id="plan-1", event="food event")
    state.set_result("writer", {"statement": "draft"})

    saved = repository.save_checkpoint(state)
    restored = repository.load_checkpoint("session-db-1")

    assert saved["session_id"] == "session-db-1"
    assert restored is not None
    assert restored.session_id == "session-db-1"
    assert restored.plan_id == "plan-1"
    assert restored.event == "food event"
    assert restored.get_result("writer") == {"statement": "draft"}


def test_sqlalchemy_repository_restores_waiting_human_checkpoint(repository):
    state = AgentState(session_id="session-db-2", plan_id="plan-2", event="high risk")
    request_review(state, reason="Human review required.", reviewer="alice", comment="check")

    repository.save_checkpoint(state)
    restored = repository.load_checkpoint("session-db-2")

    assert restored.status == WAITING_HUMAN
    assert restored.approval["required"] is True
    assert restored.approval["decision"] == "pending"
    assert restored.approval["reviewer"] == "alice"
    assert restored.approval["comment"] == "check"


def test_sqlalchemy_repository_records_approve_audit(repository):
    state = AgentState(session_id="session-db-approve", plan_id="plan", event="event")
    request_review(state, "Need review.")
    approve(state, reviewer="legal-user", comment="approved")

    repository.save_checkpoint(state)
    audit_logs = repository.list_audit_logs("session-db-approve")

    assert any(item["action"] == "approved" for item in audit_logs)
    approved = [item for item in audit_logs if item["action"] == "approved"][0]
    assert approved["actor"] == "legal-user"
    assert approved["details"]["comment"] == "approved"
    assert approved["details"]["decision"] == "approved"


def test_sqlalchemy_repository_records_reject_audit(repository):
    state = AgentState(session_id="session-db-reject", plan_id="plan", event="event")
    request_review(state, "Need review.")
    reject(state, reviewer="manager", comment="reject")

    repository.save_checkpoint(state)
    restored = repository.load_checkpoint("session-db-reject")
    audit_logs = repository.list_audit_logs("session-db-reject")

    assert restored.status == REJECTED
    assert any(item["action"] == "rejected" for item in audit_logs)
    rejected = [item for item in audit_logs if item["action"] == "rejected"][0]
    assert rejected["actor"] == "manager"
    assert rejected["details"]["comment"] == "reject"
    assert rejected["details"]["decision"] == "rejected"


def test_sqlalchemy_repository_keeps_multiple_sessions_isolated(repository):
    first = AgentState(session_id="session-one", plan_id="plan-one", event="event one")
    second = AgentState(session_id="session-two", plan_id="plan-two", event="event two")
    first.set_result("writer", {"statement": "one"})
    second.set_result("writer", {"statement": "two"})

    repository.save_checkpoint(first)
    repository.save_checkpoint(second)

    restored_first = repository.load_checkpoint("session-one")
    restored_second = repository.load_checkpoint("session-two")
    sessions = repository.list_checkpoints()

    assert restored_first.get_result("writer") == {"statement": "one"}
    assert restored_second.get_result("writer") == {"statement": "two"}
    assert {item["session_id"] for item in sessions} == {"session-one", "session-two"}


def test_sqlalchemy_repository_delete_removes_checkpoint(repository):
    state = AgentState(session_id="session-delete", plan_id="plan", event="event")
    request_review(state, "Need review.")
    approve(state, reviewer="reviewer", comment="ok")
    repository.save_checkpoint(state)

    assert repository.delete_checkpoint("session-delete") is True
    assert repository.load_checkpoint("session-delete") is None
    assert repository.delete_checkpoint("session-delete") is False
