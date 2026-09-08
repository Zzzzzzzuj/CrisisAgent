from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import create_user, get_auth_db_session
from backend.db.session import Base, get_db_session
from backend.main import app


@pytest.fixture()
def secured_workspace(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_db_session] = override_db
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "workspace-test-secret")
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(tmp_path / "ingestion.json"))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    with factory() as db:
        for role in ("admin", "operator", "legal_reviewer", "viewer"):
            create_user(db, role, f"{role}-pass", role)
    yield
    app.dependency_overrides.clear()


def test_auth_enabled_product_api_matrix(secured_workspace):
    source = {"source_id": "secure-rss", "source_name": "Secure RSS", "source_type": "rss", "url": "https://example.com/feed", "risk_keywords": ["投诉"]}
    assert request("POST", "/api/sources", source).status_code == 401

    admin = token("admin")
    created = request("POST", "/api/sources", source, admin)
    assert created.status_code == 201
    record = created.json()
    assert record["created_by"] and record["updated_by"]
    assert record["created_at"] and record["updated_at"]
    assert request("GET", "/api/audit/logs", token=admin).status_code == 200

    viewer = token("viewer")
    assert request("GET", "/api/sources", token=viewer).status_code == 200
    assert request("POST", "/api/sources", {**source, "source_id": "viewer-rss"}, viewer).status_code == 403
    assert request("GET", "/api/audit/logs", token=viewer).status_code == 403

    operator = token("operator")
    assert request("POST", "/api/ingestion/run", {"source_ids": ["secure-rss"]}, operator).status_code == 201
    assert request("GET", "/api/ingestion/runs", token=operator).status_code == 200
    assert request("GET", "/api/audit/logs", token=operator).status_code == 403

    reviewer = token("legal_reviewer")
    assert request("GET", "/api/sources", token=reviewer).status_code == 200
    assert request("POST", "/api/sources", {**source, "source_id": "reviewer-rss"}, reviewer).status_code == 403
    assert request("POST", "/api/ingestion/run", {"source_ids": ["secure-rss"]}, reviewer).status_code == 403

    patched = request("PATCH", "/api/sources/secure-rss", {"enabled": True}, admin).json()
    assert patched["created_by"] == record["created_by"]
    assert patched["created_at"] == record["created_at"]
    assert patched["updated_by"] == "1"
    assert patched["updated_at"] >= record["updated_at"]
    logs = request("GET", "/api/audit/logs", token=admin).json()["logs"]
    assert any(item["action"] == "source.create" and item["result"] == "success" and item["actor_role"] == "admin" for item in logs)
    assert any(item["action"] == "source.create" and item["result"] == "denied" for item in logs)


def request(method, path, body=None, token=None):
    async def send():
        headers = {"Authorization": f"Bearer {token}"} if token else None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.request(method, path, json=body, headers=headers)
    return asyncio.run(send())


def token(role):
    response = request("POST", "/api/auth/login", {"username": role, "password": f"{role}-pass"})
    assert response.status_code == 200
    return response.json()["access_token"]
