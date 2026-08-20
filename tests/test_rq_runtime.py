import asyncio

import httpx

from backend.core.runtime_tasks import (
    check_rq_backend,
    get_rq_queue_name,
    get_task_queue_backend,
    submit_dynamic_session,
    submit_resume_session,
)
from backend.main import app


def _request(method: str, url: str, json: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json)

    return asyncio.run(send_request())


class FakeQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, func_path, session_id, job_timeout=None, meta=None):
        job = FakeJob(func_path, session_id, job_timeout, meta)
        self.enqueued.append(job)
        return job


class FakeJob:
    def __init__(self, func_path, session_id, job_timeout, meta):
        self.func_path = func_path
        self.session_id = session_id
        self.job_timeout = job_timeout
        self.meta = meta or {}

    def get_status(self, refresh=True):
        return "queued"


def test_task_queue_backend_defaults_to_inprocess(monkeypatch):
    monkeypatch.delenv("TASK_QUEUE_BACKEND", raising=False)

    assert get_task_queue_backend() == "inprocess"


def test_task_queue_backend_reads_rq_config(monkeypatch):
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "rq")
    monkeypatch.setenv("RQ_QUEUE_NAME", "critical")

    assert get_task_queue_backend() == "rq"
    assert get_rq_queue_name() == "critical"


def test_rq_submit_dynamic_session_enqueues_importable_worker(monkeypatch):
    fake_queue = FakeQueue()
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "rq")
    monkeypatch.setattr("backend.core.runtime_tasks.get_rq_queue", lambda: fake_queue)

    job = submit_dynamic_session("session-rq")

    assert job.func_path == "backend.core.runtime_tasks.run_dynamic_session_task"
    assert job.session_id == "session-rq"
    assert job.meta == {"session_id": "session-rq", "task_type": "dynamic"}
    assert fake_queue.enqueued == [job]


def test_rq_submit_resume_session_enqueues_importable_worker(monkeypatch):
    fake_queue = FakeQueue()
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "rq")
    monkeypatch.setattr("backend.core.runtime_tasks.get_rq_queue", lambda: fake_queue)

    job = submit_resume_session("session-review")

    assert job.func_path == "backend.core.runtime_tasks.run_resume_session_task"
    assert job.session_id == "session-review"
    assert job.meta == {"session_id": "session-review", "task_type": "resume"}


def test_rq_backend_reports_unavailable_without_redis(monkeypatch):
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "rq")
    monkeypatch.setattr(
        "backend.core.runtime_tasks.get_redis_connection",
        lambda: (_ for _ in ()).throw(ConnectionError("redis down")),
    )

    status = check_rq_backend()

    assert status["ok"] is False
    assert status["backend"] == "rq"
    assert status["error"] == "ConnectionError"


def test_readiness_reports_rq_unavailable_without_requiring_real_redis(monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "async")
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "rq")
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setattr(
        "backend.observability.readiness.check_rq_backend",
        lambda: {
            "ok": False,
            "backend": "rq",
            "queue_name": "crisisagent",
            "redis_url_configured": True,
            "error": "ConnectionError",
        },
    )

    response = _request("GET", "/ready")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["checks"]["async_worker"]["task_queue_backend"] == "rq"
    assert detail["checks"]["async_worker"]["error"] == "ConnectionError"


def test_async_run_api_contract_stays_queued_with_rq_backend(monkeypatch):
    submitted = []
    monkeypatch.setenv("RUNTIME_MODE", "async")
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "rq")
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setattr("backend.main.submit_dynamic_session", lambda session_id: submitted.append(session_id))

    response = _request("POST", "/api/dynamic/run", json={"event": "食品安全事件"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["state_status"] == "QUEUED"
    assert submitted == [body["session_id"]]
