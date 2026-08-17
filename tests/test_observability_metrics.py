import asyncio

import httpx

from backend.core.state import AgentState
from backend.main import app
from backend.observability.metrics import collect_runtime_metrics


def _request(method: str, url: str, json: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json)

    return asyncio.run(send_request())


def test_health_returns_ok(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")

    response = _request("GET", "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_for_json_fallback(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("AUTH_ENABLED", "false")

    response = _request("GET", "/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["checks"]["checkpoint_backend"]["backend"] == "json"


def test_ready_fails_when_auth_enabled_without_secret(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    response = _request("GET", "/ready")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["ready"] is False
    assert detail["checks"]["auth"]["ok"] is False
    assert "SECRET_KEY" in detail["checks"]["auth"]["error"]


def test_runtime_metrics_collector_counts_session_status_and_signals(monkeypatch):
    completed = AgentState(session_id="completed", plan_id="p1", event="completed event")
    completed.status = "COMPLETED"
    completed.add_trace(
        {
            "agent": "legal",
            "status": "success",
            "duration_ms": 100,
            "rag": {"hit": True, "count": 1, "fallback_used": False},
            "llm": {"success": True, "fallback_used": False},
        }
    )

    failed = AgentState(session_id="failed", plan_id="p2", event="failed event")
    failed.status = "FAILED"
    failed.mark_failed("writer", "boom")
    failed.add_trace(
        {
            "agent": "writer",
            "status": "failed",
            "duration_ms": 300,
            "llm": {"success": False, "fallback_used": True},
        }
    )

    waiting = AgentState(session_id="waiting", plan_id="p3", event="waiting event")
    waiting.status = "WAITING_HUMAN"
    waiting.approval["decision"] = "approved"
    waiting.metadata["guardrails"] = {
        "input": {"hit": True},
        "output": {"hit": False},
    }
    waiting.add_trace(
        {
            "agent": "legal",
            "status": "success",
            "duration_ms": 200,
            "rag": {"hit": False, "fallback_used": True},
        }
    )

    states = {
        state.session_id: state
        for state in [completed, failed, waiting]
    }

    monkeypatch.setattr(
        "backend.observability.metrics.checkpoint.list_checkpoints",
        lambda: [{"session_id": session_id} for session_id in states],
    )
    monkeypatch.setattr(
        "backend.observability.metrics.checkpoint.load_checkpoint",
        lambda session_id: states.get(session_id),
    )
    monkeypatch.setattr(
        "backend.observability.metrics.checkpoint.list_audit_logs",
        lambda: [{"session_id": "failed", "action": "rejected"}],
    )

    metrics = collect_runtime_metrics()

    assert metrics["total_sessions"] == 3
    assert metrics["completed_sessions"] == 1
    assert metrics["failed_sessions"] == 1
    assert metrics["waiting_human_sessions"] == 1
    assert metrics["agent_failure_count"] == 2
    assert metrics["llm_call_count"] == 2
    assert metrics["llm_fallback_count"] == 1
    assert metrics["guardrail_trigger_count"] == 1
    assert metrics["rag_hit_count"] == 1
    assert metrics["rag_fallback_count"] == 1
    assert metrics["approval_count"] == 1
    assert metrics["rejection_count"] == 1
    assert metrics["average_runtime_latency_ms"] == 200


def test_runtime_metrics_api_returns_collector_output(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setattr(
        "backend.main.collect_runtime_metrics",
        lambda: {
            "total_sessions": 1,
            "completed_sessions": 1,
            "failed_sessions": 0,
            "waiting_human_sessions": 0,
            "agent_failure_count": 0,
            "llm_call_count": 1,
            "llm_fallback_count": 0,
            "guardrail_trigger_count": 0,
            "rag_hit_count": 1,
            "rag_fallback_count": 0,
            "approval_count": 0,
            "rejection_count": 0,
            "average_runtime_latency_ms": 123,
        },
    )

    response = _request("GET", "/api/metrics/runtime")

    assert response.status_code == 200
    assert response.json()["total_sessions"] == 1
    assert response.json()["average_runtime_latency_ms"] == 123
