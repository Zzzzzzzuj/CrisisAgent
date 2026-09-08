from __future__ import annotations

from backend.api.event_store import JsonCrisisEventStore

from tests.test_event_agent_run_api import _request


def _seed_event(monkeypatch, tmp_path, *, create_run: bool = True) -> str:
    event_path = tmp_path / "events.json"
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(event_path))
    monkeypatch.setenv("EVENT_AGENT_RUN_STORE_PATH", str(tmp_path / "agent_runs.json"))
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setattr("backend.core.checkpoint.CHECKPOINT_PATH", tmp_path / "checkpoints.json")
    store = JsonCrisisEventStore(event_path)
    event, _ = store.create_from_cluster(
        source_run_id="run-report",
        cluster={
            "cluster_id": "cluster-report",
            "event": "示例公司产品质量投诉，相关事实尚待核实。",
            "company": "示例公司",
            "risk_level": "high",
            "public_emotion": "worried",
            "fact_status": "unverified",
            "event_status": "uncertain",
            "human_review_required": True,
            "source_count": 1,
            "source_items": ["source-report"],
            "first_published_at": "2026-09-08T00:00:00+00:00",
            "last_published_at": "2026-09-08T00:00:00+00:00",
            "event_fingerprint": "fingerprint-report",
        },
    )
    if create_run:
        assert _request("POST", f"/api/events/{event['event_id']}/run", {}).status_code == 201
    return event["event_id"]


def test_json_report_contains_event_run_trace_and_safety(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)

    response = _request("GET", f"/api/events/{event_id}/report?format=json")
    assert response.status_code == 200
    report = response.json()
    assert report["event"]["event_id"] == event_id
    assert report["sources"]["source_items"] == ["source-report"]
    assert report["risk_and_fact"]["risk_level"] == "high"
    assert report["risk_and_fact"]["fact_status"] == "unverified"
    assert report["agent_run"]["final_statement_preview"]
    assert report["trace"]["agent_order"]
    assert report["human_review"]["human_review_required"] is True
    assert report["safety"]["automatic_publish"] is False
    assert report["safety"]["report_generated_from_existing_run"] is True


def test_markdown_report_is_structured_and_does_not_claim_publish(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)

    response = _request("GET", f"/api/events/{event_id}/report?format=markdown")
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "markdown"
    assert "# CrisisAgent 危机处理报告" in body["markdown_content"]
    assert "## 5. Legal RAG 证据摘要" in body["markdown_content"]
    assert "以下内容是 Agent 生成的声明草稿，不代表已经发布" in body["markdown_content"]
    assert "automatic_publish：False" in body["markdown_content"]


def test_report_missing_event_or_run_returns_error(monkeypatch, tmp_path):
    assert _request("GET", "/api/events/missing/report").status_code == 404
    event_id = _seed_event(monkeypatch, tmp_path, create_run=False)
    response = _request("GET", f"/api/events/{event_id}/report")
    assert response.status_code == 400
    assert "Run the CrisisAgent" in response.json()["detail"]


def test_report_does_not_rerun_agent_and_handles_missing_evidence(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("report generation must not run the Agent")

    monkeypatch.setattr("backend.api.event_run_routes.run_dynamic_sync_with_metadata", fail_if_called)
    response = _request("GET", f"/api/events/{event_id}/report")
    assert response.status_code == 200
    report = response.json()
    assert report["trace"]["legal_rag_evidence"]["status"] == "not_available"
    assert isinstance(report["trace"]["redteam_issues"], list)


def test_invalid_report_format_returns_400(monkeypatch, tmp_path):
    event_id = _seed_event(monkeypatch, tmp_path)
    assert _request("GET", f"/api/events/{event_id}/report?format=pdf").status_code == 400
