import asyncio

import httpx

from backend.core.state import AgentState
from backend.main import app


def _request(method: str, url: str, json: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json)

    return asyncio.run(send_request())


def _patch_checkpoint(monkeypatch):
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
    return store


def _state_with_trace(session_id="session-observe"):
    state = AgentState(session_id=session_id, plan_id="plan-1", event="event")
    state.trace = [
        {
            "agent": "sentiment",
            "reason": "analyze public emotion",
            "start_time": "2026-07-24T00:00:00+00:00",
            "end_time": "2026-07-24T00:00:00.250000+00:00",
            "status": "success",
            "input": {"event": "event"},
            "output": {"risk_level": "high"},
            "error": None,
            "tools": [
                {
                    "name": "sentiment_analysis",
                    "success": True,
                }
            ],
        },
        {
            "agent": "legal",
            "reason": "review legal safety",
            "start_time": "2026-07-24T00:00:01+00:00",
            "end_time": "2026-07-24T00:00:01.500000+00:00",
            "status": "failed",
            "output": None,
            "error": "RuntimeError: legal unavailable",
            "rag": {"hit": True},
            "memory": {"hit": True},
        },
    ]
    state.mark_failed("legal", "RuntimeError: legal unavailable")
    return state


def test_dynamic_trace_fields_are_complete(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = _state_with_trace()
    store[state.session_id] = state.to_dict()

    response = _request("GET", "/api/dynamic/session-observe")

    assert response.status_code == 200
    trace = response.json()["trace"]
    assert trace[0]["start_time"] == "2026-07-24T00:00:00+00:00"
    assert trace[0]["end_time"] == "2026-07-24T00:00:00.250000+00:00"
    assert trace[0]["duration_ms"] == 250
    assert "event" in trace[0]["input_summary"]
    assert "risk_level" in trace[0]["output_summary"]
    assert trace[1]["error"] == "RuntimeError: legal unavailable"


def test_dynamic_metrics_are_calculated(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = _state_with_trace()
    state.status = "WAITING_HUMAN"
    state.approval.update(
        {
            "required": True,
            "decision": "pending",
            "reason": "high risk",
        }
    )
    store[state.session_id] = state.to_dict()

    response = _request("GET", "/api/dynamic/session-observe/metrics")

    assert response.status_code == 200
    metrics = response.json()
    assert metrics["total_duration"] == 750
    assert metrics["agent_count"] == 2
    assert metrics["failed_agents"] == ["legal"]
    assert metrics["rag_hits"] == 1
    assert metrics["memory_hits"] == 1
    assert metrics["tool_calls"] == 1
    assert metrics["human_status"]["state_status"] == "WAITING_HUMAN"
    assert metrics["human_status"]["decision"] == "pending"


def test_dynamic_metrics_keep_sessions_isolated(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    first = _state_with_trace("session-first")
    second = AgentState(session_id="session-second", plan_id="plan-2", event="event")
    second.trace = [
        {
            "agent": "writer",
            "start_time": "2026-07-24T00:00:00+00:00",
            "end_time": "2026-07-24T00:00:00.100000+00:00",
            "status": "success",
            "output": {"statement": "ok"},
            "error": None,
        }
    ]
    store[first.session_id] = first.to_dict()
    store[second.session_id] = second.to_dict()

    first_response = _request("GET", "/api/dynamic/session-first/metrics")
    second_response = _request("GET", "/api/dynamic/session-second/metrics")

    assert first_response.json()["agent_count"] == 2
    assert second_response.json()["agent_count"] == 1
    assert first_response.json()["total_duration"] == 750
    assert second_response.json()["total_duration"] == 100


def test_dynamic_metrics_empty_session_returns_zero_values(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = AgentState(session_id="session-empty", plan_id="plan-empty", event="event")
    store[state.session_id] = state.to_dict()

    response = _request("GET", "/api/dynamic/session-empty/metrics")

    assert response.status_code == 200
    metrics = response.json()
    assert metrics["total_duration"] == 0
    assert metrics["agent_count"] == 0
    assert metrics["failed_agents"] == []
    assert metrics["rag_hits"] == 0
    assert metrics["memory_hits"] == 0
    assert metrics["tool_calls"] == 0


def test_dynamic_metrics_missing_session_returns_404(monkeypatch):
    _patch_checkpoint(monkeypatch)

    response = _request("GET", "/api/dynamic/missing/metrics")

    assert response.status_code == 404
