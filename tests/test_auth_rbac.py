import asyncio

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import create_user, get_auth_db_session
from backend.core.human import request_review
from backend.core.state import AgentState
from backend.db.repositories import SQLAlchemyCheckpointRepository
from backend.db.session import Base, get_db_session
from backend.main import app


@pytest.fixture()
def auth_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    def override_db_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_auth_db_session] = override_db_session
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")

    with session_factory() as db:
        operator = create_user(db, "operator", "operator-pass", "operator")
        reviewer = create_user(db, "reviewer", "reviewer-pass", "legal_reviewer")
        admin = create_user(db, "admin", "admin-pass", "admin")

    yield {
        "session_factory": session_factory,
        "repository": SQLAlchemyCheckpointRepository(session_factory=session_factory),
        "operator": operator,
        "reviewer": reviewer,
        "admin": admin,
    }

    app.dependency_overrides.clear()


def test_login_success(auth_db):
    response = _request("POST", "/api/auth/login", json={"username": "operator", "password": "operator-pass"})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "operator"
    assert body["user"]["role"] == "operator"


def test_login_wrong_password_fails(auth_db):
    response = _request("POST", "/api/auth/login", json={"username": "operator", "password": "wrong"})

    assert response.status_code == 401


def test_operator_cannot_approve(auth_db, monkeypatch):
    session_id = _save_waiting_session(auth_db["repository"], "session-operator")
    monkeypatch.setattr("backend.main.load_checkpoint", auth_db["repository"].load_checkpoint)
    monkeypatch.setattr("backend.main.save_checkpoint", auth_db["repository"].save_checkpoint)
    token = _login("operator", "operator-pass")

    response = _request(
        "POST",
        f"/api/dynamic/{session_id}/approve",
        json={"comment": "try approve"},
        token=token,
    )

    assert response.status_code == 403


def test_legal_reviewer_can_approve_and_audit_log_records_user(auth_db, monkeypatch):
    session_id = _save_waiting_session(auth_db["repository"], "session-reviewer")
    monkeypatch.setattr("backend.main.load_checkpoint", auth_db["repository"].load_checkpoint)
    monkeypatch.setattr("backend.main.save_checkpoint", auth_db["repository"].save_checkpoint)
    monkeypatch.setattr("backend.main.resume_agent_loop", lambda session_id: {"session_id": session_id, "status": "completed"})
    token = _login("reviewer", "reviewer-pass")

    response = _request(
        "POST",
        f"/api/dynamic/{session_id}/approve",
        json={"comment": "approved by legal"},
        token=token,
    )

    assert response.status_code == 200
    restored = auth_db["repository"].load_checkpoint(session_id)
    audit_logs = auth_db["repository"].list_audit_logs(session_id)
    assert restored.approval["reviewer_id"] == auth_db["reviewer"].id
    assert restored.approval["reviewer_username"] == "reviewer"
    assert restored.approval["reviewer_role"] == "legal_reviewer"
    assert any(log["action"] == "approved" and log["actor"] == "reviewer" for log in audit_logs)


def test_admin_can_approve(auth_db, monkeypatch):
    session_id = _save_waiting_session(auth_db["repository"], "session-admin")
    monkeypatch.setattr("backend.main.load_checkpoint", auth_db["repository"].load_checkpoint)
    monkeypatch.setattr("backend.main.save_checkpoint", auth_db["repository"].save_checkpoint)
    monkeypatch.setattr("backend.main.resume_agent_loop", lambda session_id: {"session_id": session_id, "status": "completed"})
    token = _login("admin", "admin-pass")

    response = _request(
        "POST",
        f"/api/dynamic/{session_id}/approve",
        json={"comment": "admin approved"},
        token=token,
    )

    assert response.status_code == 200
    restored = auth_db["repository"].load_checkpoint(session_id)
    assert restored.approval["reviewer_username"] == "admin"
    assert restored.approval["reviewer_role"] == "admin"


def test_operator_created_dynamic_case_records_created_by(auth_db, monkeypatch):
    monkeypatch.setattr("backend.main.run_dynamic_agent", lambda event: _dynamic_result("session-created-by", event))
    monkeypatch.setattr("backend.main.save_checkpoint", auth_db["repository"].save_checkpoint)
    token = _login("operator", "operator-pass")

    response = _request(
        "POST",
        "/api/dynamic/run",
        json={"event": "用户反馈普通问题"},
        token=token,
    )

    assert response.status_code == 200
    restored = auth_db["repository"].load_checkpoint("session-created-by")
    assert restored.metadata["created_by"]["username"] == "operator"
    assert restored.metadata["created_by"]["role"] == "operator"


def test_auth_disabled_keeps_demo_approve_behavior(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    store = {}
    state = AgentState(session_id="session-demo", plan_id="plan", event="event")
    request_review(state, "Need review.")
    store[state.session_id] = state.to_dict()

    def load(session_id):
        return AgentState.from_dict(store[session_id])

    def save(state):
        store[state.session_id] = state.to_dict()
        return store[state.session_id]

    monkeypatch.setattr("backend.main.load_checkpoint", load)
    monkeypatch.setattr("backend.main.save_checkpoint", save)
    monkeypatch.setattr("backend.main.resume_agent_loop", lambda session_id: {"session_id": session_id, "status": "completed"})

    response = _request(
        "POST",
        "/api/dynamic/session-demo/approve",
        json={"reviewer": "demo-human", "comment": "ok"},
    )

    assert response.status_code == 200
    assert store["session-demo"]["approval"]["reviewer"] == "demo-human"


def _request(method: str, url: str, json: dict | None = None, token: str | None = None):
    async def send_request():
        headers = {"Authorization": f"Bearer {token}"} if token else None
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json, headers=headers)

    return asyncio.run(send_request())


def _login(username: str, password: str) -> str:
    response = _request("POST", "/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _save_waiting_session(repository: SQLAlchemyCheckpointRepository, session_id: str) -> str:
    state = AgentState(session_id=session_id, plan_id="plan", event="event")
    request_review(state, "Need legal review.")
    repository.save_checkpoint(state)
    return session_id


def _dynamic_result(session_id: str, event: str) -> dict:
    return {
        "session_id": session_id,
        "plan_id": "plan",
        "event": event,
        "planner_input": {"event": event, "category": "general", "risk_level": "low"},
        "raw_plan": {"plan_id": "plan", "plan": []},
        "validated_plan": {"plan_id": "plan", "plan": []},
        "executed_agents": ["decision"],
        "results": {
            "decision": {
                "final_statement": "ok",
                "scores": {"legal_safety": 8, "empathy": 8, "robustness": 8},
            }
        },
        "failed_agents": [],
        "execution_trace": [],
    }
