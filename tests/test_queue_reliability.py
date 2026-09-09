from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from backend.api.ingestion_recovery import recover_stuck_runs
from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.ingestion_worker import run_ingestion_job
from backend.api.ingestion_heartbeat import list_worker_heartbeats, update_worker_heartbeat
from backend.main import app


def _request(method: str, url: str):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.request(method, url)
    return asyncio.run(send())


def _queued_run(run_id: str = "run-1") -> dict:
    return {"run_id": run_id, "status": "queued", "live_fetch": False, "execution_mode": "background", "queue_backend": "redis", "retry_count": 0, "max_retries": 1, "timeout_seconds": 10, "created_by": "tester", "source_results": []}


def test_failure_schedules_same_run_retry(monkeypatch):
    store = get_ingestion_run_store()
    store.save(_queued_run())
    monkeypatch.setattr("backend.api.ingestion_worker.execute_ingestion_payload", lambda _payload: (_ for _ in ()).throw(RuntimeError("transient")))
    monkeypatch.setattr("backend.api.ingestion_worker.schedule_ingestion_retry", lambda *_args: "retry-job")
    monkeypatch.setattr("backend.api.ingestion_worker.update_worker_heartbeat", lambda *_args, **_kwargs: {})

    result = run_ingestion_job("run-1", {}, {"id": "tester", "role": "admin"})
    assert result["status"] == "queued"
    assert result["retry_count"] == 1
    assert result["job_id"] == "retry-job"
    assert result["last_error"] == "transient"


def test_retry_exhaustion_dead_letters_and_timeout_is_audited(monkeypatch):
    store = get_ingestion_run_store()
    run = _queued_run("run-2")
    run.update({"retry_count": 1, "max_retries": 1})
    store.save(run)
    timeout = type("JobTimeoutException", (Exception,), {})
    monkeypatch.setattr("backend.api.ingestion_worker.execute_ingestion_payload", lambda _payload: (_ for _ in ()).throw(timeout("timeout")))
    monkeypatch.setattr("backend.api.ingestion_worker.enqueue_dead_letter", lambda *_args: "dead-job")
    monkeypatch.setattr("backend.api.ingestion_worker.update_worker_heartbeat", lambda *_args, **_kwargs: {})

    result = run_ingestion_job("run-2", {}, {"id": "tester", "role": "admin"})
    assert result["status"] == "failed"
    assert result["dead_lettered_at"]
    assert result["last_error"] == "timeout"


def test_heartbeat_api_and_stuck_recovery(monkeypatch):
    monkeypatch.setattr("backend.api.ingestion_routes.list_worker_heartbeats", lambda: [{"worker_id": "worker-1", "queue_name": "crisis-ingestion", "status": "idle", "last_seen_at": "now"}])
    response = _request("GET", "/api/ingestion/workers")
    assert response.status_code == 200
    assert response.json()["workers"][0]["worker_id"] == "worker-1"

    stale = _queued_run("run-3")
    stale["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    get_ingestion_run_store().save(stale)
    assert recover_stuck_runs(60, dry_run=True) == ["run-3"]
    assert get_ingestion_run_store().get("run-3")["status"] == "queued"
    assert recover_stuck_runs(60, mode="mark-failed", dry_run=False) == ["run-3"]
    assert get_ingestion_run_store().get("run-3")["status"] == "failed"


def test_worker_heartbeat_writes_and_reads_without_real_redis():
    class FakeRedis:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def setex(self, key, _ttl, value):
            self.values[key] = value

        def scan_iter(self, match):
            assert match == "worker:ingestion:*:heartbeat"
            return list(self.values)

    fake = FakeRedis()
    update_worker_heartbeat("worker-2", "crisis-ingestion", "idle", connection=fake)
    assert list_worker_heartbeats(connection=fake)[0]["worker_id"] == "worker-2"


def test_stuck_requeue_uses_same_run_id(monkeypatch):
    stale = _queued_run("run-4")
    stale["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    get_ingestion_run_store().save(stale)
    calls = []
    monkeypatch.setattr("backend.api.ingestion_recovery.submit_ingestion_job", lambda run_id, *_args: calls.append(run_id) or "recovery-job")
    assert recover_stuck_runs(60, mode="requeue", dry_run=False) == ["run-4"]
    assert calls == ["run-4"]
    assert get_ingestion_run_store().get("run-4")["job_id"] == "recovery-job"
