from __future__ import annotations

import asyncio
import json

import httpx

from backend.api.case_memory_store import JsonCaseMemoryStore
from backend.api.event_store import JsonCrisisEventStore
from backend.main import app


def _request(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.request(method, path, json=body, headers=headers)
    return asyncio.run(send())


def _memory_payload(event_id: str) -> dict:
    return {
        "source_event_id": event_id,
        "crisis_type": "food_safety",
        "risk_level": "high",
        "fact_status": "verified",
        "event_status": "current",
        "final_statement_summary": "说明核查进展并提供消费者指引。",
        "legal_risk_summary": "保留事实边界，避免未经证实的承诺。",
        "redteam_summary": "检查时间线和责任表述。",
        "human_review_summary": "法务已审核。",
        "response_strategy": "先核实事实，再分阶段沟通。",
        "tags": ["food", "recall"],
    }


def _seed_event(monkeypatch, tmp_path, status="completed"):
    event_path = tmp_path / "events.json"
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(event_path))
    monkeypatch.setenv("CASE_MEMORY_STORE_PATH", str(tmp_path / "memories.json"))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    store = JsonCrisisEventStore(event_path)
    event, _ = store.create_from_cluster(
        source_run_id="run-memory",
        cluster={
            "cluster_id": "cluster-memory",
            "event": "示例食品公司产品质量事件",
            "company": "示例食品公司",
            "risk_level": "high",
            "public_emotion": "worried",
            "fact_status": "verified",
            "event_status": "current",
            "human_review_required": False,
            "source_count": 2,
            "source_items": ["source-a", "source-b"],
            "event_fingerprint": "memory-fingerprint",
        },
    )
    if status != "new":
        store.update(event["event_id"], {"status": status})
    return event["event_id"]


def test_completed_event_can_create_and_filter_memory(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    response = _request("POST", "/api/case-memories", _memory_payload(event_id))
    assert response.status_code == 201
    body = response.json()
    assert body["source_event_id"] == event_id
    assert body["owner_id"] == "demo-system"
    assert "created_at" in body

    listed = _request("GET", "/api/case-memories?tag=food")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_unreviewed_event_cannot_enter_memory(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path, status="waiting_human")
    response = _request("POST", "/api/case-memories", _memory_payload(event_id))
    assert response.status_code == 409


def test_viewer_cannot_create_but_legal_reviewer_can_read(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    payload = _memory_payload(event_id)
    viewer = {"X-User-Id": "viewer-1", "X-User-Role": "viewer"}
    assert _request("POST", "/api/case-memories", payload, viewer).status_code == 403
    created = _request("POST", "/api/case-memories", payload).json()
    reviewer = {"X-User-Id": "legal-1", "X-User-Role": "legal_reviewer"}
    assert _request("GET", f"/api/case-memories/{created['memory_id']}", headers=reviewer).status_code == 200


def test_memory_does_not_store_sensitive_or_full_text_fields(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    payload = {**_memory_payload(event_id), "content": "full article body"}
    assert _request("POST", "/api/case-memories", payload).status_code == 422
    store = JsonCaseMemoryStore(tmp_path / "memories.json")
    assert store.list_memories() == []


def test_case_memory_lifecycle_fields_are_optional_and_persisted(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    payload = {**_memory_payload(event_id), "case_group_id": "crisis-group-1", "round_index": 2,
               "previous_memory_id": "memory-round-1", "previous_statement_summary": "上一轮说明已启动核查。",
               "public_reaction_summary": "公众继续关注赔付进展。", "what_changed_since_previous": "新增召回范围。",
               "previous_redteam_findings": ["时间线不清"], "unresolved_redteam_findings": ["赔付标准未说明"],
               "previous_legal_constraints": ["避免承认未经证实的责任"], "avoid_repeating_points": ["不要重复泛化表态"],
               "outcome": "worsened"}
    response = _request("POST", "/api/case-memories", payload)
    assert response.status_code == 201
    assert response.json()["case_group_id"] == "crisis-group-1"
    assert response.json()["round_index"] == 2


def test_legacy_case_memory_without_lifecycle_fields_is_compatible(tmp_path):
    store = JsonCaseMemoryStore(tmp_path / "legacy.json")
    store.path.write_text(json.dumps({"memories": [{
        "memory_id": "legacy-1", "source_event_id": "event-1", "crisis_type": "service",
        "risk_level": "low", "fact_status": "verified", "event_status": "current",
        "final_statement_summary": "summary", "legal_risk_summary": "", "redteam_summary": "",
        "human_review_summary": "", "response_strategy": "", "tags": [], "created_from": "human_review",
        "created_by": "user", "owner_id": "user", "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00", "archived": False,
    }]}), encoding="utf-8")
    assert store.get("legacy-1")["memory_id"] == "legacy-1"
