from __future__ import annotations

import asyncio

import httpx

from backend.api.event_store import JsonCrisisEventStore
from backend.api.ingestion_run_store import JsonIngestionRunStore
from backend.api.dashboard_service import build_urgency
from backend.main import app


def _request(method: str, url: str):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url)

    return asyncio.run(send_request())


def _prepare_stores(monkeypatch, tmp_path) -> JsonCrisisEventStore:
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(tmp_path / "events.json"))
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(tmp_path / "runs.json"))
    return JsonCrisisEventStore(tmp_path / "events.json")


def _create_event(store: JsonCrisisEventStore, **changes: object) -> dict:
    defaults = {
        "cluster_id": f"cluster-{changes.get('name', 'default')}",
        "event": f"{changes.get('name', '示例')} 舆情事件",
        "company": "示例公司",
        "risk_level": "low",
        "public_emotion": "worried",
        "fact_status": "verified",
        "event_status": "current",
        "human_review_required": False,
        "source_count": 1,
        "source_items": ["source-a"],
        "event_fingerprint": f"fingerprint-{changes.get('name', 'default')}",
    }
    defaults.update(changes)
    event, _ = store.create_from_cluster(
        source_run_id=f"run-{defaults['cluster_id']}",
        cluster=defaults,
    )
    if "status" in changes:
        event = store.update(event["event_id"], {"status": changes["status"]}) or event
    return event


def test_urgency_score_and_severity_bands(monkeypatch, tmp_path):
    store = _prepare_stores(monkeypatch, tmp_path)
    _create_event(
        store,
        name="sev1",
        risk_level="high",
        fact_status="conflicting",
        event_status="current",
        human_review_required=True,
        source_count=5,
        status="waiting_human",
    )
    _create_event(
        store,
        name="sev2",
        risk_level="medium",
        fact_status="unverified",
        event_status="current",
        source_count=2,
    )
    _create_event(store, name="sev3", risk_level="low", fact_status="unverified", event_status="current")
    _create_event(store, name="sev4", risk_level="low", fact_status="verified", event_status="historical", status="completed")

    body = _request("GET", "/api/dashboard/severity").json()
    groups = {group["severity"]: group["events"] for group in body["groups"]}
    assert len(groups["SEV-1"]) == 1
    assert len(groups["SEV-2"]) == 1
    assert len(groups["SEV-3"]) == 1
    assert len(groups["SEV-4"]) == 1
    assert groups["SEV-1"][0]["urgency_score"] == 100
    assert groups["SEV-2"][0]["recommended_action"] == "尽快审核并准备声明草稿"


def test_completed_event_lowers_urgency_score():
    event = {
        "event_id": "score-event",
        "title": "评分事件",
        "risk_level": "low",
        "fact_status": "verified",
        "event_status": "current",
        "source_count": 1,
        "human_review_required": False,
        "status": "new",
    }
    active_score = build_urgency(event)["urgency_score"]
    completed_score = build_urgency({**event, "status": "completed"})["urgency_score"]
    assert completed_score == active_score - 10


def test_overview_review_queue_and_archived_priority(monkeypatch, tmp_path):
    store = _prepare_stores(monkeypatch, tmp_path)
    active = _create_event(
        store,
        name="active",
        risk_level="high",
        fact_status="unverified",
        event_status="uncertain",
        human_review_required=True,
        source_count=5,
        status="waiting_human",
    )
    archived = _create_event(
        store,
        name="archived",
        risk_level="high",
        fact_status="conflicting",
        event_status="current",
        human_review_required=True,
        source_count=5,
        status="archived",
    )

    overview = _request("GET", "/api/dashboard/overview").json()
    assert overview["total_events"] == 2
    assert overview["waiting_human_count"] == 1
    assert overview["unverified_count"] == 1
    assert overview["high_risk_count"] == 2
    assert overview["automatic_publish"] is False
    assert [item["event_id"] for item in overview["top_urgent_events"]] == [active["event_id"]]
    assert archived["event_id"] not in [item["event_id"] for item in overview["top_urgent_events"]]

    queue = _request("GET", "/api/dashboard/review-queue").json()
    assert queue["count"] == 1
    assert queue["events"][0]["event_id"] == active["event_id"]


def test_trends_and_source_health_keep_no_match_out_of_failures(monkeypatch, tmp_path):
    store = _prepare_stores(monkeypatch, tmp_path)
    _create_event(store, name="trend", risk_level="high", status="waiting_human")

    run_store = JsonIngestionRunStore(tmp_path / "runs.json")
    run_store.save(
        {
            "run_id": "run-one",
            "source_results": [
                {"source_id": "rss-a", "status": "no_match"},
                {"source_id": "rss-b", "status": "collected"},
            ],
        }
    )
    run_store.save(
        {
            "run_id": "run-two",
            "source_results": [
                {"source_id": "rss-a", "status": "failed"},
                {"source_id": "rss-b", "status": "skipped_by_robots"},
                {"source_id": "rss-c", "status": "disabled"},
            ],
        }
    )

    trends = _request("GET", "/api/dashboard/trends").json()
    assert len(trends["buckets"]) == 1
    assert trends["buckets"][0]["total"] == 1
    assert trends["buckets"][0]["high_risk"] == 1
    assert trends["buckets"][0]["waiting_human"] == 1

    health = _request("GET", "/api/dashboard/source-health").json()
    sources = {item["source_id"]: item for item in health["sources"]}
    assert sources["rss-a"]["latest_status"] == "failed"
    assert sources["rss-a"]["no_match_count"] == 1
    assert sources["rss-a"]["failed_count"] == 1
    assert sources["rss-a"]["failure_rate"] == 0.5
    assert sources["rss-b"]["skipped_by_robots_count"] == 1
    assert sources["rss-b"]["failure_rate"] == 0.5
    assert sources["rss-c"]["failure_rate"] == 0.0
