from __future__ import annotations

import asyncio

import httpx

from backend.api.event_store import JsonCrisisEventStore
from backend.main import app


def _request(method: str, url: str, json_body: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json_body)

    return asyncio.run(send_request())


def _seed_event(monkeypatch, tmp_path) -> str:
    event_path = tmp_path / "events.json"
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(event_path))
    monkeypatch.setenv("EVENT_AGENT_RUN_STORE_PATH", str(tmp_path / "agent_runs.json"))
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setattr("backend.core.checkpoint.CHECKPOINT_PATH", tmp_path / "checkpoints.json")
    store = JsonCrisisEventStore(event_path)
    event, _ = store.create_from_cluster(
        source_run_id="run-1",
        cluster={
            "cluster_id": "cluster-1",
            "event": "某食品品牌被曝光使用过期原料，消费者要求监管介入。",
            "company": "示例食品公司",
            "risk_level": "high",
            "public_emotion": "angry",
            "fact_status": "unverified",
            "event_status": "uncertain",
            "human_review_required": True,
            "source_count": 2,
            "source_items": ["source-a", "source-b"],
            "event_fingerprint": "fingerprint-1",
        },
    )
    return event["event_id"]


def test_event_run_uses_mock_runtime_and_preserves_ingestion_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "llm")
    event_id = _seed_event(monkeypatch, tmp_path)

    response = _request("POST", f"/api/events/{event_id}/run", {})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "waiting_human"
    assert body["session_id"]
    assert body["agent_run_id"]
    assert body["human_review_required"] is True
    assert "ingestion_review_required" in body["policy_triggers"]
    assert body["automatic_publish"] is False

    trace = _request("GET", f"/api/events/{event_id}/trace")
    assert trace.status_code == 200
    assert trace.json()["metadata"]["ingestion"]["fact_status"] == "unverified"
    assert trace.json()["trace"]

    review = _request("GET", f"/api/events/{event_id}/review")
    assert review.status_code == 200
    assert review.json()["approval_status"] == "pending"
    assert "approve" in review.json()["allowed_actions"]


def test_event_run_is_idempotent_without_force_rerun(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    first = _request("POST", f"/api/events/{event_id}/run", {}).json()
    second_response = _request("POST", f"/api/events/{event_id}/run", {})
    assert second_response.status_code == 201
    assert second_response.json()["agent_run_id"] == first["agent_run_id"]

    rerun = _request(
        "POST",
        f"/api/events/{event_id}/run",
        {"force_rerun": True},
    )
    assert rerun.status_code == 201
    assert rerun.json()["agent_run_id"] != first["agent_run_id"]


def test_archived_event_cannot_run_and_missing_event_is_404(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    assert _request("POST", f"/api/events/{event_id}/archive").status_code == 200
    assert _request("POST", f"/api/events/{event_id}/run", {}).status_code == 409
    assert _request("POST", "/api/events/missing/run", {}).status_code == 404
    assert _request("GET", "/api/events/missing/run").status_code == 404
    assert _request("GET", "/api/events/missing/trace").status_code == 404
    assert _request("GET", "/api/events/missing/review").status_code == 404


def test_event_run_detail_and_event_status(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    run = _request("POST", f"/api/events/{event_id}/run", {}).json()
    detail = _request("GET", f"/api/events/{event_id}/run")
    assert detail.status_code == 200
    assert detail.json()["session_id"] == run["session_id"]
    assert _request("GET", "/api/events?status=waiting_human").json()["count"] == 1
