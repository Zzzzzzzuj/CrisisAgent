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
from backend.mcp.schemas import MCP_SAFE_TOOL_NAMES
from backend.skills.tool_runner import TOOL_INPUT_INVALID, ToolResult


def request(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.request(method, path, json=body, headers=headers)

    return asyncio.run(send())


def _headers(role: str) -> dict[str, str]:
    return {"X-User-Id": f"{role}-1", "X-User-Role": role}


@pytest.fixture()
def secured_tools(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_db_session] = override_db
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "http-tool-test-secret")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    with factory() as db:
        for role in ("admin", "operator", "legal_reviewer", "viewer"):
            create_user(db, role, f"{role}-pass", role)
    yield
    app.dependency_overrides.clear()


def _token(role: str) -> str:
    response = request("POST", "/api/auth/login", {"username": role, "password": f"{role}-pass"})
    assert response.status_code == 200
    return response.json()["access_token"]


def _token_headers(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role)}"}


def test_tools_list_is_the_mcp_safe_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))

    response = request("GET", "/api/tools", headers=_headers("viewer"))

    assert response.status_code == 200
    names = {item["tool_name"] for item in response.json()["tools"]}
    assert names == set(MCP_SAFE_TOOL_NAMES)
    assert all(item["read_only"] is True for item in response.json()["tools"])


def test_safe_tool_uses_mcp_adapter_and_tool_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    captured = {}

    def fake_call(name, arguments, *, transport):
        captured.update({"name": name, "arguments": arguments, "transport": transport})
        return {
            "tool_result": ToolResult(
                tool_name=name,
                success=False,
                error_code=TOOL_INPUT_INVALID,
                error_message="bad input",
                human_review_required=True,
                trace={"attempts": 0},
            ).to_dict()
        }

    monkeypatch.setattr("backend.api.tool_routes.call_mcp_tool", fake_call)
    response = request(
        "POST",
        "/api/tools/run",
        {"tool_name": "legal_rag_search", "arguments": {"query": "食品安全"}, "request_id": "req-1"},
        _headers("admin"),
    )

    assert response.status_code == 200
    assert captured == {"name": "legal_rag_search", "arguments": {"query": "食品安全"}, "transport": "http"}
    assert response.json()["status"] == "failed"
    assert response.json()["error_code"] == TOOL_INPUT_INVALID
    assert response.json()["human_review_required"] is True


def test_viewer_and_forbidden_tools_are_denied_and_audited(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    audit_path = tmp_path / "audit.json"
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(audit_path))

    viewer = request("POST", "/api/tools/run", {"tool_name": "guardrail_check", "arguments": {}}, _headers("viewer"))
    forbidden = request("POST", "/api/tools/run", {"tool_name": "publish", "arguments": {}}, _headers("admin"))
    logs = request("GET", "/api/audit/logs", headers=_headers("admin")).json()["logs"]

    assert viewer.status_code == 403
    assert forbidden.status_code == 403
    assert any(item["action"] == "tool.run.denied" and item["resource_id"] == "guardrail_check" for item in logs)
    assert any(item["action"] == "tool.run.denied" and item["resource_id"] == "publish" for item in logs)


def test_legal_reviewer_only_runs_legal_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    monkeypatch.setattr(
        "backend.api.tool_routes.call_mcp_tool",
        lambda name, arguments, *, transport: {"tool_result": ToolResult(tool_name=name, success=True, output={"ok": True}).to_dict()},
    )

    allowed = request("POST", "/api/tools/run", {"tool_name": "guardrail_check", "arguments": {}}, _headers("legal_reviewer"))
    denied = request("POST", "/api/tools/run", {"tool_name": "runtime_metrics_query", "arguments": {}}, _headers("legal_reviewer"))

    assert allowed.status_code == 200
    assert allowed.json()["status"] == "success"
    assert denied.status_code == 403


def test_dry_run_does_not_execute_handler(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    monkeypatch.setattr("backend.api.tool_routes.call_mcp_tool", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")))

    response = request("POST", "/api/tools/run", {"tool_name": "guardrail_check", "arguments": {}, "dry_run": True}, _headers("operator"))

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["output"]["dry_run"] is True


def test_auth_enabled_tool_api_role_matrix_and_audit(secured_tools):
    assert request("POST", "/api/tools/run", {"tool_name": "guardrail_check", "arguments": {}}).status_code == 401

    admin = _token_headers("admin")
    operator = _token_headers("operator")
    reviewer = _token_headers("legal_reviewer")
    viewer = _token_headers("viewer")

    assert request("GET", "/api/tools", headers=viewer).status_code == 200
    assert request("POST", "/api/tools/run", {"tool_name": "guardrail_check", "arguments": {}}, headers=admin).status_code == 200
    assert request("POST", "/api/tools/run", {"tool_name": "runtime_metrics_query", "arguments": {}}, headers=operator).status_code == 200
    assert request("POST", "/api/tools/run", {"tool_name": "guardrail_check", "arguments": {}}, headers=reviewer).status_code == 200
    assert request("POST", "/api/tools/run", {"tool_name": "runtime_metrics_query", "arguments": {}}, headers=reviewer).status_code == 403
    assert request("POST", "/api/tools/run", {"tool_name": "guardrail_check", "arguments": {}}, headers=viewer).status_code == 403

    logs = request("GET", "/api/audit/logs", headers=admin).json()["logs"]
    assert any(item["action"] == "tool.run" and item["actor_role"] == "admin" for item in logs)
    assert any(item["action"] == "tool.run.denied" and item["actor_role"] == "legal_reviewer" for item in logs)
