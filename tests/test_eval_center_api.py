from __future__ import annotations

import asyncio

import httpx

from backend.api.event_run_store import JsonEventAgentRunStore
from backend.api.event_store import JsonCrisisEventStore
from backend.api.ingestion_run_store import JsonIngestionRunStore
from backend.main import app


def _request(method: str, url: str, json_body: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json_body)

    return asyncio.run(send_request())


def _seed_runtime_records(monkeypatch, tmp_path) -> dict[str, str]:
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(tmp_path / "events.json"))
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(tmp_path / "ingestion_runs.json"))
    monkeypatch.setenv("EVENT_AGENT_RUN_STORE_PATH", str(tmp_path / "agent_runs.json"))
    monkeypatch.setenv("EVAL_RUN_STORE_PATH", str(tmp_path / "eval_runs.json"))

    event_store = JsonCrisisEventStore(tmp_path / "events.json")
    event, _ = event_store.create_from_cluster(
        source_run_id="ingestion-1",
        cluster={
            "cluster_id": "cluster-1",
            "event": "示例食品公司被投诉使用过期原料，事实尚待核实。",
            "company": "示例食品公司",
            "risk_level": "high",
            "public_emotion": "angry",
            "fact_status": "unverified",
            "event_status": "uncertain",
            "human_review_required": True,
            "source_count": 2,
            "source_items": ["rss-a", "rss-b"],
            "event_fingerprint": "event-fingerprint-1",
        },
    )
    event_store.update(event["event_id"], {"status": "waiting_human"})

    JsonIngestionRunStore(tmp_path / "ingestion_runs.json").save(
        {
            "run_id": "ingestion-1",
            "source_results": [
                {"source_id": "rss-a", "status": "no_match"},
                {"source_id": "rss-b", "status": "failed", "failed_reason": "fake_timeout"},
                {"source_id": "rss-c", "status": "skipped_by_robots"},
            ],
        }
    )
    run = JsonEventAgentRunStore(tmp_path / "agent_runs.json").create(
        {
            "event_id": event["event_id"],
            "session_id": "session-eval-1",
            "status": "waiting_human",
            "mode": "mock",
            "started_at": "2026-09-08T00:00:00+00:00",
            "finished_at": "2026-09-08T00:00:01+00:00",
            "final_statement_preview": "我们正在核实相关情况，并将持续更新。",
            "scores": {"safety": 0.9},
            "human_review_required": True,
            "policy_triggers": ["ingestion_review_required"],
            "trace": [{"agent": "sentiment", "status": "completed", "output": {"risk_level": "high"}}],
            "metadata": {"ingestion": {"fact_status": "unverified"}},
            "error": None,
            "automatic_publish": False,
        }
    )
    return {"event_id": event["event_id"], "agent_run_id": run["agent_run_id"]}


def test_eval_run_saves_all_dimensions_and_preserves_safety(monkeypatch, tmp_path):
    _seed_runtime_records(monkeypatch, tmp_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Eval Center must not call network adapters or Agent runtime")

    monkeypatch.setattr("backend.api.ingestion_routes.RssSourceAdapter.fetch", fail_if_called)
    monkeypatch.setattr("backend.api.event_run_routes.run_dynamic_sync_with_metadata", fail_if_called)
    response = _request("POST", "/api/evals/run", {})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_cases"] > 0
    assert body["passed_cases"] == body["total_cases"]
    assert body["pass_rate"] == 1.0
    assert set(body["dimensions"]) == {"ingestion", "event", "urgency", "agent_run", "report", "tool", "golden_case"}
    assert body["summary"]["no_live_fetch"] is True
    assert body["summary"]["no_real_llm_call"] is True
    assert body["summary"]["agent_replayed"] is False
    assert body["automatic_publish"] is False
    assert body["dimensions"]["tool"]["tool_success_rate"] >= 0
    assert body["dimensions"]["tool"]["loop_detected_rate"] > 0
    assert (tmp_path / "eval_runs.json").exists()


def test_eval_dry_run_does_not_write_store(monkeypatch, tmp_path):
    _seed_runtime_records(monkeypatch, tmp_path)
    response = _request("POST", "/api/evals/run", {"dimensions": ["urgency"], "dry_run": True})
    assert response.status_code == 201
    assert response.json()["dry_run"] is True
    assert response.json()["dimensions"].keys() == {"urgency"}
    assert not (tmp_path / "eval_runs.json").exists()


def test_eval_list_detail_overview_and_regression(monkeypatch, tmp_path):
    _seed_runtime_records(monkeypatch, tmp_path)
    first = _request("POST", "/api/evals/run", {"dimensions": ["urgency"]})
    assert first.status_code == 201
    first_id = first.json()["eval_run_id"]

    list_response = _request("GET", "/api/evals/runs")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert list_response.json()["runs"][0]["eval_run_id"] == first_id
    assert _request("GET", f"/api/evals/runs/{first_id}").status_code == 200
    assert _request("GET", "/api/evals/runs/missing").status_code == 404

    overview = _request("GET", "/api/evals/overview").json()
    assert overview["latest_eval_run_id"] == first_id
    assert overview["latest_pass_rate"] == 1.0
    assert overview["automatic_publish"] is False
    assert _request("GET", "/api/evals/regression").json()["not_enough_runs"] is True

    second = _request("POST", "/api/evals/run", {"dimensions": ["ingestion", "tool"]})
    assert second.status_code == 201
    regression = _request("GET", "/api/evals/regression").json()
    assert regression["not_enough_runs"] is False
    assert regression["current_eval_run_id"] == second.json()["eval_run_id"]
    assert regression["previous_eval_run_id"] == first_id
    assert regression["delta"] == 0.0


def test_eval_items_cover_runtime_dimensions(monkeypatch, tmp_path):
    ids = _seed_runtime_records(monkeypatch, tmp_path)
    body = _request("POST", "/api/evals/run", {}).json()
    items = {item["case_id"]: item for item in body["items"]}
    assert items["ingestion.ingestion-1.no_match.0"]["passed"] is True
    assert items[f"event.{ids['event_id']}.source_items"]["passed"] is True
    assert items["urgency.high_conflicting_sev1"]["passed"] is True
    assert items[f"agent_run.{ids['agent_run_id']}.automatic_publish"]["passed"] is True
    assert items[f"report.{ids['agent_run_id']}.generated_from_existing_run"]["passed"] is True
    assert items["tool.offline_reliability_suite"]["passed"] is True
