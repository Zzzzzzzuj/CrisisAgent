from __future__ import annotations

import asyncio

import httpx

from backend.api.ingestion_run_store import JsonIngestionRunStore
from backend.main import app


def _request(method: str, url: str, json_body: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json_body)

    return asyncio.run(send_request())


def _seed_run(monkeypatch, tmp_path, *, run_id: str = "run-1", cluster_id: str = "cluster-1"):
    run_path = tmp_path / "runs.json"
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(run_path))
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(tmp_path / "events.json"))
    JsonIngestionRunStore(run_path).save(
        {
            "run_id": run_id,
            "status": "completed",
            "live_fetch": False,
            "clusters": [
                {
                    "cluster_id": cluster_id,
                    "event": "示例公司产品存在质量投诉，事实仍待核实。",
                    "company": "示例公司",
                    "risk_level": "high",
                    "public_emotion": "concerned",
                    "fact_status": "unverified",
                    "event_status": "uncertain",
                    "human_review_required": True,
                    "source_count": 2,
                    "source_items": ["source-a", "source-b"],
                    "first_published_at": "2026-09-08T00:00:00+00:00",
                    "last_published_at": "2026-09-08T01:00:00+00:00",
                    "event_fingerprint": "fingerprint-1",
                }
            ],
        }
    )
    return run_id, cluster_id


def test_create_event_copies_cluster_and_is_idempotent(monkeypatch, tmp_path):
    run_id, cluster_id = _seed_run(monkeypatch, tmp_path)

    response = _request(
        "POST",
        "/api/events/from-ingestion-run",
        {"run_id": run_id, "cluster_id": cluster_id, "title": "产品质量事件"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["title"] == "产品质量事件"
    assert body["source_items"] == ["source-a", "source-b"]
    assert body["human_review_required"] is True

    duplicate = _request(
        "POST",
        "/api/events/from-ingestion-run",
        {"run_id": run_id, "cluster_id": cluster_id},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["created"] is False
    assert duplicate.json()["event_id"] == body["event_id"]

    stored = _request("GET", "/api/events").json()
    assert stored["count"] == 1


def test_missing_run_and_cluster_return_404(monkeypatch, tmp_path):
    _seed_run(monkeypatch, tmp_path)
    assert _request(
        "POST",
        "/api/events/from-ingestion-run",
        {"run_id": "missing", "cluster_id": "cluster-1"},
    ).status_code == 404
    assert _request(
        "POST",
        "/api/events/from-ingestion-run",
        {"run_id": "run-1", "cluster_id": "missing"},
    ).status_code == 404


def test_list_filters_detail_patch_and_archive(monkeypatch, tmp_path):
    run_id, cluster_id = _seed_run(monkeypatch, tmp_path)
    created = _request(
        "POST",
        "/api/events/from-ingestion-run",
        {"run_id": run_id, "cluster_id": cluster_id},
    ).json()
    event_id = created["event_id"]

    assert _request("GET", "/api/events?status=new&risk_level=high").json()["count"] == 1
    assert _request("GET", "/api/events?status=archived").json()["count"] == 0

    detail = _request("GET", f"/api/events/{event_id}")
    assert detail.status_code == 200
    assert detail.json()["event_fingerprint"] == "fingerprint-1"

    patched = _request(
        "PATCH",
        f"/api/events/{event_id}",
        {"title": "已确认标题", "event_summary": "更新摘要", "status": "ready_for_agent"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "ready_for_agent"
    assert patched.json()["event_summary"] == "更新摘要"

    archived = _request("POST", f"/api/events/{event_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert _request("GET", "/api/events?status=archived").json()["count"] == 1
    assert _request("GET", "/api/events/missing").status_code == 404


def test_invalid_status_is_rejected(monkeypatch, tmp_path):
    run_id, cluster_id = _seed_run(monkeypatch, tmp_path)
    event_id = _request(
        "POST",
        "/api/events/from-ingestion-run",
        {"run_id": run_id, "cluster_id": cluster_id},
    ).json()["event_id"]
    assert _request("PATCH", f"/api/events/{event_id}", {"status": "running"}).status_code == 422


def test_existing_crisis_routes_remain_available(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    response = _request("POST", "/api/crisis/run", {"event": "示例公司产品质量投诉"})
    assert response.status_code == 200
