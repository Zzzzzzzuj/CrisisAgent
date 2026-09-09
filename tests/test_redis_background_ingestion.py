from __future__ import annotations

import asyncio

import httpx

from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.ingestion_worker import run_ingestion_job
from backend.main import app
from scripts.run_ingestion_worker import resolve_worker_class


def _request(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=body, headers=headers)

    return asyncio.run(send_request())


def _source(source_id: str = "queue-source") -> dict:
    return {
        "source_id": source_id,
        "source_name": source_id,
        "source_type": "rss",
        "url": f"https://example.com/{source_id}.xml",
        "enabled": True,
        "company_keywords": ["示例公司"],
        "risk_keywords": ["投诉"],
        "respect_robots": True,
        "rate_limit_seconds": 0,
        "timeout_seconds": 10,
        "max_items": 3,
    }


def _configure_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(tmp_path / "runs.json"))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    assert _request("POST", "/api/sources", _source()).status_code == 201


def _fake_enqueue(monkeypatch, job_id: str = "job-test-1"):
    monkeypatch.setattr("backend.api.ingestion_routes.submit_ingestion_job", lambda *_args, **_kwargs: job_id)


def test_worker_class_selection_is_platform_safe(monkeypatch):
    monkeypatch.delenv("INGESTION_WORKER_CLASS", raising=False)
    assert resolve_worker_class(os_name="nt").__name__ == "SimpleWorker"
    assert resolve_worker_class(os_name="posix").__name__ == "Worker"
    assert resolve_worker_class("simple", os_name="posix").__name__ == "SimpleWorker"
    assert resolve_worker_class("worker", os_name="nt").__name__ == "Worker"

    try:
        resolve_worker_class("not-a-worker", os_name="nt")
    except ValueError as exc:
        assert "INGESTION_WORKER_CLASS" in str(exc)
    else:
        raise AssertionError("invalid worker class must fail clearly")


def test_sync_ingestion_remains_default_and_background_queues(monkeypatch, tmp_path):
    _configure_stores(monkeypatch, tmp_path)
    sync = _request("POST", "/api/ingestion/run", {})
    assert sync.status_code == 201
    assert sync.json()["execution_mode"] == "sync"

    _fake_enqueue(monkeypatch)
    queued = _request("POST", "/api/ingestion/run", {"background": True})
    assert queued.status_code == 201
    body = queued.json()
    assert body["status"] == "queued"
    assert body["execution_mode"] == "background"
    assert body["queue_backend"] == "redis"
    assert body["job_id"] == "job-test-1"

    detail = _request("GET", f"/api/ingestion/runs/{body['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["job_id"] == "job-test-1"


def test_missing_or_failed_redis_is_explicit_and_audited(monkeypatch, tmp_path):
    _configure_stores(monkeypatch, tmp_path)

    def unavailable(*_args, **_kwargs):
        from backend.api.ingestion_queue import IngestionQueueUnavailable

        raise IngestionQueueUnavailable("REDIS_URL is required for background ingestion runs.")

    monkeypatch.setattr("backend.api.ingestion_routes.submit_ingestion_job", unavailable)
    response = _request("POST", "/api/ingestion/run", {"background": True})
    assert response.status_code == 503
    assert "REDIS_URL" in response.json()["detail"]
    run = get_ingestion_run_store().list_runs()[0]
    assert run["status"] == "failed"

    audit = _request("GET", "/api/audit/logs")
    assert any(item["action"] == "ingestion.run.failed" for item in audit.json()["logs"])


def test_worker_updates_lifecycle_and_does_not_repeat_terminal_run(monkeypatch, tmp_path):
    _configure_stores(monkeypatch, tmp_path)
    _fake_enqueue(monkeypatch, "job-worker")
    queued = _request("POST", "/api/ingestion/run", {"background": True}).json()

    completed = run_ingestion_job(
        queued["run_id"],
        {"source_ids": None, "live_fetch": False, "max_items_override": None, "dry_run": False},
        {"id": "demo-system", "role": "admin"},
    )
    assert completed["status"] == "completed"
    assert completed["started_at"]
    assert completed["finished_at"]
    assert completed["queue_backend"] == "redis"

    duplicate = run_ingestion_job(queued["run_id"], {}, {"id": "demo-system", "role": "admin"})
    assert duplicate["skipped"] is True
    assert duplicate["status"] == "completed"

    audit = _request("GET", "/api/audit/logs").json()["logs"]
    actions = {entry["action"] for entry in audit}
    assert {"ingestion.run.queued", "ingestion.run.started", "ingestion.run.completed"}.issubset(actions)


def test_worker_failure_is_persisted(monkeypatch, tmp_path):
    _configure_stores(monkeypatch, tmp_path)
    _fake_enqueue(monkeypatch)
    queued = _request("POST", "/api/ingestion/run", {"background": True}).json()
    monkeypatch.setattr("backend.api.ingestion_worker.execute_ingestion_payload", lambda _payload: (_ for _ in ()).throw(RuntimeError("fake pipeline failure")))

    failed = run_ingestion_job(queued["run_id"], {}, {"id": "demo-system", "role": "admin"})
    assert failed["status"] == "failed"
    assert "fake pipeline failure" in failed["error"]
    audit = _request("GET", "/api/audit/logs").json()["logs"]
    assert any(entry["action"] == "ingestion.run.failed" for entry in audit)


def test_background_respects_live_fetch_guard_and_roles(monkeypatch, tmp_path):
    _configure_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "false")
    monkeypatch.setattr("backend.api.ingestion_routes.submit_ingestion_job", lambda *_args: (_ for _ in ()).throw(AssertionError("must not enqueue")))

    guarded = _request("POST", "/api/ingestion/run", {"background": True, "live_fetch": True})
    assert guarded.status_code == 403

    viewer = _request(
        "POST",
        "/api/ingestion/run",
        {"background": True},
        {"X-User-Id": "viewer-1", "X-User-Role": "viewer"},
    )
    assert viewer.status_code == 403

    _fake_enqueue(monkeypatch, "operator-job")
    operator = _request(
        "POST",
        "/api/ingestion/run",
        {"background": True},
        {"X-User-Id": "operator-1", "X-User-Role": "operator"},
    )
    assert operator.status_code == 201
