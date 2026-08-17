import asyncio

import httpx

from backend.core.runtime_tasks import run_dynamic_session_task
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
    monkeypatch.setattr("backend.core.runtime_tasks.save_checkpoint", save)
    monkeypatch.setattr("backend.core.runtime_tasks.load_checkpoint", load)
    return store


def test_async_dynamic_run_returns_queued_session_and_checkpoint(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    submitted = []
    monkeypatch.setenv("RUNTIME_MODE", "async")
    monkeypatch.setattr(
        "backend.main.submit_dynamic_session",
        lambda session_id: submitted.append(session_id),
    )

    response = _request("POST", "/api/dynamic/run", json={"event": "食品安全事件"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["state_status"] == "QUEUED"
    assert body["session_id"] in store
    assert store[body["session_id"]]["status"] == "QUEUED"
    assert submitted == [body["session_id"]]


def test_async_worker_executes_queued_session_to_completed(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = AgentState(session_id="async-complete", plan_id="", event="event")
    state.set_status("QUEUED")
    store[state.session_id] = state.to_dict()
    monkeypatch.setattr("backend.core.runtime_tasks.evaluate_runtime_state", lambda state: {"passed": True})
    monkeypatch.setattr(
        "backend.core.runtime_tasks.evaluate_human_policy",
        lambda state, evaluation: {"required": False, "reason": "", "triggers": []},
    )

    def execute(state):
        assert store[state.session_id]["status"] == "RUNNING"
        state.plan_id = "plan-async"
        state.set_result("decision", {"final_statement": "ok"})
        state.add_trace(
            {
                "agent": "decision",
                "reason": "decide",
                "start_time": "start",
                "end_time": "end",
                "status": "success",
                "output": {"final_statement": "ok"},
                "error": None,
            }
        )
        return {
            "session_id": state.session_id,
            "plan_id": state.plan_id,
            "event": state.event,
            "raw_plan": {},
            "validated_plan": {},
            "executed_agents": ["decision"],
            "results": state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(state.trace),
        }

    monkeypatch.setattr("backend.core.runtime_tasks.execute_dynamic_state", execute)

    result = run_dynamic_session_task("async-complete")

    assert result["status"] == "completed"
    assert store["async-complete"]["status"] == "COMPLETED"
    assert store["async-complete"]["results"]["decision"]["final_statement"] == "ok"


def test_async_worker_failure_marks_checkpoint_failed(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = AgentState(session_id="async-failed", plan_id="", event="event")
    state.set_status("QUEUED")
    store[state.session_id] = state.to_dict()
    monkeypatch.setattr(
        "backend.core.runtime_tasks.execute_dynamic_state",
        lambda state: (_ for _ in ()).throw(RuntimeError("worker failed")),
    )

    result = run_dynamic_session_task("async-failed")

    assert result["status"] == "failed"
    restored = store["async-failed"]
    assert restored["status"] == "FAILED"
    assert restored["failed_agents"] == [
        {
            "agent": "runtime_worker",
            "reason": "worker failed",
        }
    ]
    assert restored["trace"][-1]["agent"] == "runtime_worker"
    assert restored["trace"][-1]["status"] == "failed"


def test_async_approve_queues_resume_without_blocking(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    submitted = []
    monkeypatch.setenv("RUNTIME_MODE", "async")
    monkeypatch.setattr(
        "backend.main.submit_resume_session",
        lambda session_id: submitted.append(session_id),
    )
    state = AgentState(session_id="async-review", plan_id="plan", event="event")
    state.status = "WAITING_HUMAN"
    state.approval.update(
        {
            "required": True,
            "decision": "pending",
            "reason": "human required",
        }
    )
    store[state.session_id] = state.to_dict()

    response = _request(
        "POST",
        "/api/dynamic/async-review/approve",
        json={"reviewer": "alice", "comment": "ok"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["state_status"] == "RUNNING"
    assert body["approval"]["decision"] == "approved"
    assert submitted == ["async-review"]
    assert store["async-review"]["status"] == "RUNNING"


def test_json_checkpoint_fallback_still_works_with_sync_runtime(monkeypatch, tmp_path):
    from backend.core.checkpoint import load_checkpoint, save_checkpoint

    monkeypatch.delenv("CHECKPOINT_STORAGE", raising=False)
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="json-session", plan_id="plan", event="event")

    save_checkpoint(state, checkpoint_path)
    restored = load_checkpoint("json-session", checkpoint_path)

    assert restored is not None
    assert restored.session_id == "json-session"
