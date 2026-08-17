import asyncio

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import hash_password
from backend.core.state import AgentState
from backend.db.models import User
from backend.db.repositories import SQLAlchemyCheckpointRepository
from backend.db.session import Base
from backend.main import app


def _request(method: str, url: str, json: dict | None = None, token: str | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json, headers=headers)

    return asyncio.run(send_request())


@pytest.fixture()
def auth_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr("backend.auth.get_session_factory", lambda: session_factory)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    with session_factory() as db:
        db.add_all(
            [
                User(username="operator", password_hash=hash_password("operator-pass"), role="operator"),
                User(username="legal", password_hash=hash_password("legal-pass"), role="legal_reviewer"),
                User(username="admin", password_hash=hash_password("admin-pass"), role="admin"),
            ]
        )
        db.commit()
    return session_factory


@pytest.fixture()
def checkpoint_store(monkeypatch):
    store = {}

    def save(state):
        store[state.session_id] = state.to_dict()
        return store[state.session_id]

    def load(session_id):
        data = store.get(session_id)
        if data is None:
            return None
        return AgentState.from_dict(data)

    monkeypatch.setattr("backend.main.save_checkpoint", save)
    monkeypatch.setattr("backend.main.load_checkpoint", load)
    monkeypatch.setattr("backend.core.runtime_tasks.save_checkpoint", save)
    monkeypatch.setattr("backend.core.runtime_tasks.load_checkpoint", load)
    return store


def _login(username: str, password: str) -> str:
    response = _request("POST", "/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _waiting_human_state(session_id: str = "review-session") -> AgentState:
    state = AgentState(session_id=session_id, plan_id="plan", event="event")
    state.status = "WAITING_HUMAN"
    state.approval.update(
        {
            "required": True,
            "decision": "pending",
            "reason": "human required",
        }
    )
    return state


def test_login_success_and_me_returns_user(auth_db):
    token = _login("legal", "legal-pass")

    response = _request("GET", "/api/auth/me", token=token)

    assert response.status_code == 200
    body = response.json()
    assert body["auth_enabled"] is True
    assert body["user"]["username"] == "legal"
    assert body["user"]["role"] == "legal_reviewer"


def test_login_wrong_password_fails(auth_db):
    response = _request("POST", "/api/auth/login", json={"username": "legal", "password": "wrong"})

    assert response.status_code == 401


def test_operator_cannot_approve(auth_db, checkpoint_store):
    state = _waiting_human_state()
    checkpoint_store[state.session_id] = state.to_dict()
    token = _login("operator", "operator-pass")

    response = _request(
        "POST",
        f"/api/dynamic/{state.session_id}/approve",
        json={"comment": "approve"},
        token=token,
    )

    assert response.status_code == 403


def test_operator_async_run_records_creator_identity(auth_db, checkpoint_store, monkeypatch):
    submitted = []
    monkeypatch.setenv("RUNTIME_MODE", "async")
    monkeypatch.setattr("backend.main.submit_dynamic_session", lambda session_id: submitted.append(session_id))
    token = _login("operator", "operator-pass")

    response = _request(
        "POST",
        "/api/dynamic/run",
        json={"event": "食品安全事件"},
        token=token,
    )

    assert response.status_code == 200
    session_id = response.json()["session_id"]
    assert submitted == [session_id]
    assert checkpoint_store[session_id]["metadata"]["created_by"]["username"] == "operator"
    assert checkpoint_store[session_id]["metadata"]["created_by"]["role"] == "operator"


def test_legal_reviewer_can_approve_with_real_identity(auth_db, checkpoint_store, monkeypatch):
    state = _waiting_human_state("legal-review")
    checkpoint_store[state.session_id] = state.to_dict()
    token = _login("legal", "legal-pass")

    def resume(session_id):
        restored = AgentState.from_dict(checkpoint_store[session_id])
        return {
            "session_id": session_id,
            "status": "completed",
            "state_status": restored.status,
            "approval": restored.approval,
        }

    monkeypatch.setattr("backend.main.resume_agent_loop", resume)
    response = _request(
        "POST",
        f"/api/dynamic/{state.session_id}/approve",
        json={"reviewer": "spoofed", "comment": "ok"},
        token=token,
    )

    assert response.status_code == 200
    approval = response.json()["approval"]
    assert approval["decision"] == "approved"
    assert approval["reviewer"] == "legal"
    assert approval["reviewer_username"] == "legal"
    assert approval["reviewer_role"] == "legal_reviewer"
    assert approval["reviewer_id"] is not None


def test_admin_can_approve(auth_db, checkpoint_store, monkeypatch):
    state = _waiting_human_state("admin-review")
    checkpoint_store[state.session_id] = state.to_dict()
    token = _login("admin", "admin-pass")
    monkeypatch.setattr(
        "backend.main.resume_agent_loop",
        lambda session_id: {
            "session_id": session_id,
            "status": "completed",
            "approval": AgentState.from_dict(checkpoint_store[session_id]).approval,
        },
    )

    response = _request(
        "POST",
        f"/api/dynamic/{state.session_id}/approve",
        json={"comment": "admin ok"},
        token=token,
    )

    assert response.status_code == 200
    assert response.json()["approval"]["reviewer_role"] == "admin"


def test_audit_log_records_real_authenticated_user(auth_db):
    repository = SQLAlchemyCheckpointRepository(session_factory=auth_db)
    state = _waiting_human_state("audit-review")
    state.approval.update(
        {
            "required": False,
            "decision": "approved",
            "reviewer": "legal",
            "reviewer_id": 2,
            "reviewer_username": "legal",
            "reviewer_role": "legal_reviewer",
            "comment": "approved",
            "timestamp": "2026-08-17T00:00:00+00:00",
        }
    )
    state.trace.append(
        {
            "agent": "human_gate",
            "status": "approved",
            "reason": "Human approved runtime continuation.",
            "start_time": "2026-08-17T00:00:00+00:00",
            "end_time": "2026-08-17T00:00:00+00:00",
            "output": {"approval": dict(state.approval)},
            "error": None,
        }
    )

    repository.save_checkpoint(state)
    audit_logs = repository.list_audit_logs("audit-review")

    assert audit_logs[0]["actor"] == "legal"
    assert audit_logs[0]["details"]["reviewer_id"] == 2
    assert audit_logs[0]["details"]["reviewer_username"] == "legal"
    assert audit_logs[0]["details"]["reviewer_role"] == "legal_reviewer"


def test_auth_disabled_keeps_demo_approve_behavior(monkeypatch, checkpoint_store):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    state = _waiting_human_state("demo-review")
    checkpoint_store[state.session_id] = state.to_dict()
    monkeypatch.setattr(
        "backend.main.resume_agent_loop",
        lambda session_id: {
            "session_id": session_id,
            "status": "completed",
            "approval": AgentState.from_dict(checkpoint_store[session_id]).approval,
        },
    )

    response = _request(
        "POST",
        f"/api/dynamic/{state.session_id}/approve",
        json={"reviewer": "demo-human", "comment": "ok"},
    )

    assert response.status_code == 200
    assert response.json()["approval"]["reviewer"] == "demo-human"
