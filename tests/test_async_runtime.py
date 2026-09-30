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
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
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
    monkeypatch.setattr("backend.main.list_checkpoints", lambda: [
        {"session_id": session_id} for session_id in store
    ])
    monkeypatch.setattr(
        "backend.core.runtime_tasks.list_checkpoints",
        lambda: [{"session_id": session_id} for session_id in store],
    )
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


def test_dynamic_create_explicit_async_persists_before_worker_and_is_idempotent(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    submitted = []
    monkeypatch.setattr("backend.main.submit_dynamic_session", lambda session_id: submitted.append(session_id))
    payload = {
        "event": "系统故障，原因仍在排查",
        "execution_mode": "async",
        "client_request_id": "client-request-001",
    }

    first = _request("POST", "/api/dynamic/run", json=payload)
    assert first.status_code == 200
    first_body = first.json()
    session_id = first_body["session_id"]
    assert first_body["state_status"] == "QUEUED"
    assert store[session_id]["status"] == "QUEUED"
    assert submitted == [session_id]

    # The detail API can recover the task while the deliberately unstarted worker is pending.
    detail = _request("GET", f"/api/dynamic/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "QUEUED"
    listed = _request("GET", "/api/dynamic/sessions")
    assert session_id in {item["session_id"] for item in listed.json()}

    repeated = _request("POST", "/api/dynamic/run", json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["session_id"] == session_id
    assert repeated.json()["reused"] is True
    assert submitted == [session_id]


def test_create_idempotency_does_not_deduplicate_distinct_requests_or_changed_payload(monkeypatch):
    _patch_checkpoint(monkeypatch)
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    submitted = []
    monkeypatch.setattr("backend.main.submit_dynamic_session", lambda session_id: submitted.append(session_id))
    base = {"event": "相同事件", "execution_mode": "async"}

    first = _request("POST", "/api/dynamic/run", json={**base, "client_request_id": "request-a"}).json()
    second = _request("POST", "/api/dynamic/run", json={**base, "client_request_id": "request-b"}).json()
    assert first["session_id"] != second["session_id"]
    assert len(submitted) == 2

    conflict = _request(
        "POST",
        "/api/dynamic/run",
        json={"event": "不同内容", "execution_mode": "async", "client_request_id": "request-a"},
    )
    assert conflict.status_code == 409
    assert len(submitted) == 2


def test_async_queue_submission_failure_is_queryable_and_safe(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    monkeypatch.setattr(
        "backend.main.submit_dynamic_session",
        lambda _session_id: (_ for _ in ()).throw(RuntimeError("provider credential leaked in raw error")),
    )

    response = _request(
        "POST",
        "/api/dynamic/run",
        json={"event": "event", "execution_mode": "async", "client_request_id": "enqueue-failure"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state_status"] == "FAILED"
    saved = store[body["session_id"]]
    assert saved["metadata"]["runtime_failure"]["summary"] == "后台处理失败，请稍后重试或联系管理员。"
    assert "provider credential leaked" not in str(saved)


def test_async_final_review_rejection_does_not_enqueue_resume(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    state = AgentState(session_id="async-reject", plan_id="plan", event="event")
    state.status = "WAITING_HUMAN"
    state.metadata.update({"runtime_mode": "async", "human_wait_type": "FINAL_REVIEW"})
    state.approval.update({"required": True, "decision": "pending", "reason": "review"})
    store[state.session_id] = state.to_dict()
    submitted = []
    monkeypatch.setattr("backend.main.submit_resume_session", lambda session_id: submitted.append(session_id))

    response = _request("POST", "/api/dynamic/async-reject/reject", json={"reviewer": "alice"})
    assert response.status_code == 200
    assert response.json()["state_status"] == "REJECTED"
    assert submitted == []


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
            "reason": "后台处理失败，请稍后重试或联系管理员。",
        }
    ]
    assert restored["trace"][-1]["agent"] == "runtime_worker"
    assert restored["trace"][-1]["status"] == "failed"
    assert restored["metadata"]["runtime_failure"]["summary"] == "后台处理失败，请稍后重试或联系管理员。"
    assert "worker failed" not in str(restored)


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
