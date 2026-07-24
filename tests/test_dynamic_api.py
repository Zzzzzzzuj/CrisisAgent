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


def _dynamic_result(session_id: str, event: str) -> dict:
    return {
        "session_id": session_id,
        "plan_id": f"plan-{session_id}",
        "event": event,
        "planner_input": {
            "event": event,
            "category": "food_safety",
            "risk_level": "high",
        },
        "raw_plan": {"plan_id": f"raw-{session_id}", "plan": []},
        "validated_plan": {"plan_id": f"plan-{session_id}", "plan": []},
        "executed_agents": ["sentiment", "writer", "decision"],
        "results": {
            "sentiment": {"risk_level": "high"},
            "writer": {"statement": "draft"},
            "decision": {
                "final_statement": "final",
                "scores": {
                    "legal_safety": 8,
                    "empathy": 8,
                    "robustness": 8,
                },
            },
        },
        "failed_agents": [],
        "execution_trace": [
            {
                "agent": "sentiment",
                "reason": "analyze",
                "start_time": "start",
                "end_time": "end",
                "status": "success",
                "output": {"risk_level": "high"},
                "error": None,
            }
        ],
    }


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


def test_dynamic_run_creates_task_and_checkpoint(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    monkeypatch.setattr(
        "backend.main.run_dynamic_agent",
        lambda event: _dynamic_result("session-1", event),
    )
    monkeypatch.setattr(
        "backend.main.evaluate_runtime_state",
        lambda state: {"passed": True, "issues": []},
    )
    monkeypatch.setattr(
        "backend.main.evaluate_human_policy",
        lambda state, evaluation: {"required": False, "reason": "", "triggers": []},
    )

    response = _request("POST", "/api/dynamic/run", json={"event": "食品安全事件"})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-1"
    assert body["status"] == "completed"
    assert "session-1" in store


def test_dynamic_get_returns_checkpoint_state(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = AgentState(session_id="session-2", plan_id="plan-2", event="event")
    state.set_result("writer", {"statement": "draft"})
    store[state.session_id] = state.to_dict()

    response = _request("GET", "/api/dynamic/session-2")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-2"
    assert body["results"]["writer"] == {"statement": "draft"}


def test_dynamic_approve_resumes_runtime(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = AgentState(session_id="session-3", plan_id="plan-3", event="event")
    state.status = "WAITING_HUMAN"
    state.approval.update(
        {
            "required": True,
            "decision": "pending",
            "reason": "human required",
        }
    )
    store[state.session_id] = state.to_dict()

    def resume(session_id):
        restored = AgentState.from_dict(store[session_id])
        assert restored.status == "RUNNING"
        assert restored.approval["decision"] == "approved"
        return {
            "session_id": session_id,
            "status": "completed",
            "state_status": restored.status,
            "approval": restored.approval,
        }

    monkeypatch.setattr("backend.main.resume_agent_loop", resume)

    response = _request(
        "POST",
        "/api/dynamic/session-3/approve",
        json={"reviewer": "alice", "comment": "ok"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["approval"]["decision"] == "approved"
    assert body["approval"]["reviewer"] == "alice"
    assert body["approval"]["comment"] == "ok"


def test_dynamic_reject_marks_session_failed(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = AgentState(session_id="session-4", plan_id="plan-4", event="event")
    state.status = "WAITING_HUMAN"
    state.approval.update(
        {
            "required": True,
            "decision": "pending",
            "reason": "human required",
        }
    )
    store[state.session_id] = state.to_dict()

    def resume(session_id):
        restored = AgentState.from_dict(store[session_id])
        assert restored.status == "FAILED"
        assert restored.approval["decision"] == "rejected"
        return {
            "session_id": session_id,
            "status": "failed",
            "state_status": restored.status,
            "approval": restored.approval,
        }

    monkeypatch.setattr("backend.main.resume_agent_loop", resume)

    response = _request(
        "POST",
        "/api/dynamic/session-4/reject",
        json={"reviewer": "bob", "comment": "not acceptable"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["approval"]["decision"] == "rejected"
    assert body["approval"]["reviewer"] == "bob"
    assert body["approval"]["comment"] == "not acceptable"


def test_dynamic_sessions_are_isolated(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    first = AgentState(session_id="session-a", plan_id="plan-a", event="event a")
    second = AgentState(session_id="session-b", plan_id="plan-b", event="event b")
    first.set_result("writer", {"statement": "a"})
    second.set_result("writer", {"statement": "b"})
    store[first.session_id] = first.to_dict()
    store[second.session_id] = second.to_dict()

    first_response = _request("GET", "/api/dynamic/session-a")
    second_response = _request("GET", "/api/dynamic/session-b")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["results"]["writer"] == {"statement": "a"}
    assert second_response.json()["results"]["writer"] == {"statement": "b"}


def test_dynamic_missing_session_returns_404(monkeypatch):
    _patch_checkpoint(monkeypatch)

    response = _request("GET", "/api/dynamic/missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
