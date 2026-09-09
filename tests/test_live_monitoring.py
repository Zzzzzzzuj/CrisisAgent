from __future__ import annotations

import asyncio

import httpx

from backend.ingestion.schemas import RawSentimentItem
from backend.ingestion.source_adapters import FetchResult
from backend.main import app
from backend.ingestion.query_builder import build_monitor_query


def request(method: str, path: str, body: dict | None = None):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=body)
    return asyncio.run(send())


def source(source_id="gdelt-source", source_type="gdelt_doc"):
    return {"source_id": source_id, "source_name": source_id, "source_type": source_type, "url": "https://example.com/api", "enabled": True, "query": "placeholder", "company_keywords": ["Acme"], "risk_keywords": ["召回"], "respect_robots": True, "rate_limit_seconds": 0, "timeout_seconds": 2, "max_items": 10}


def test_watchlist_permissions_and_query_builder(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHLIST_STORE_PATH", str(tmp_path / "watchlists.json"))
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    created = request("POST", "/api/watchlists", {"entity_name": "Acme", "aliases": ["Acme Corp"], "risk_keywords": ["召回"], "exclude_keywords": ["招聘"]})
    assert created.status_code == 201
    assert request("POST", "/api/watchlists", {"entity_name": "Denied"},).status_code == 201
    listed = request("GET", "/api/watchlists")
    assert listed.json()["count"] == 2
    assert request("GET", "/api/watchlists",).status_code == 200


def test_viewer_cannot_create_watchlist_and_exclude_terms_are_bounded(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHLIST_STORE_PATH", str(tmp_path / "watchlists.json"))
    denied = request("POST", "/api/watchlists", {"entity_name": "Acme"})
    # The default test client is admin; explicit role exercises the existing RBAC seam.
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", headers={"X-User-Role": "viewer"}) as client:
            return await client.post("/api/watchlists", json={"entity_name": "Viewer"})
    denied = asyncio.run(send())
    assert denied.status_code == 403
    query = build_monitor_query({"entity_name": "Acme", "risk_keywords": [], "exclude_keywords": ["招聘"]}, "gdelt_doc")
    assert "招聘" in query.query and "Acme" in query.query


def test_monitor_offline_does_not_call_adapter(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHLIST_STORE_PATH", str(tmp_path / "watchlists.json"))
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    monkeypatch.setenv("LIVE_MONITOR_RUN_STORE_PATH", str(tmp_path / "runs.json"))
    assert request("POST", "/api/watchlists", {"entity_name": "Acme", "enabled": True}).status_code == 201
    assert request("POST", "/api/sources", source()).status_code == 201
    called = []
    monkeypatch.setattr("backend.api.live_monitor_execution.fetch_source", lambda *_args: called.append(True))
    result = request("POST", "/api/live-monitor/run", {"background": False})
    assert result.status_code == 201
    assert result.json()["live_fetch"] is False
    assert not called
    assert result.json()["source_results"][0]["status"] == "disabled"


def test_monitor_live_fetch_is_server_guarded(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHLIST_STORE_PATH", str(tmp_path / "watchlists.json"))
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    assert request("POST", "/api/watchlists", {"entity_name": "Acme", "enabled": True}).status_code == 201
    assert request("POST", "/api/sources", source()).status_code == 201
    response = request("POST", "/api/live-monitor/run", {"background": False, "live_fetch": True})
    assert response.status_code == 403


def test_monitor_collects_entity_signal_and_creates_alert(monkeypatch, tmp_path):
    for key, filename in {"WATCHLIST_STORE_PATH": "watchlists.json", "SOURCE_REGISTRY_RUNTIME_PATH": "sources.json", "LIVE_MONITOR_RUN_STORE_PATH": "runs.json", "COLLECTED_ITEM_STORE_PATH": "items.json", "ALERT_STORE_PATH": "alerts.json"}.items():
        monkeypatch.setenv(key, str(tmp_path / filename))
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "true")
    assert request("POST", "/api/watchlists", {"entity_name": "Acme", "company_keywords": ["Acme"], "risk_keywords": ["召回"], "enabled": True, "priority": "high"}).status_code == 201
    assert request("POST", "/api/sources", source()).status_code == 201
    item = RawSentimentItem("item-1", "Acme RSS", "https://example.com/1", "Acme 召回公告", "Acme 召回公告", "2026-01-01", "Acme", "unverified")
    fake = FetchResult("gdelt-source", "gdelt-source", "collected", 1, 1, None, [item], "gdelt_doc")
    monkeypatch.setattr("backend.api.live_monitor_execution.fetch_source", lambda *_args: fake)
    response = request("POST", "/api/live-monitor/run", {"background": False, "live_fetch": True, "providers": ["gdelt_doc"]})
    assert response.status_code == 201
    assert response.json()["item_count"] == 1
    items = request("GET", "/api/collected-items").json()["items"]
    assert items[0]["entity_name"] == "Acme"
    assert items[0]["provider"] == "gdelt_doc"
    assert request("GET", "/api/alerts").json()["count"] == 1


def test_no_match_does_not_create_alert(monkeypatch, tmp_path):
    for key, filename in {"WATCHLIST_STORE_PATH": "watchlists.json", "SOURCE_REGISTRY_RUNTIME_PATH": "sources.json", "LIVE_MONITOR_RUN_STORE_PATH": "runs.json", "ALERT_STORE_PATH": "alerts.json"}.items():
        monkeypatch.setenv(key, str(tmp_path / filename))
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "true")
    assert request("POST", "/api/watchlists", {"entity_name": "Acme", "enabled": True}).status_code == 201
    assert request("POST", "/api/sources", source()).status_code == 201
    fake = FetchResult("gdelt-source", "gdelt-source", "no_match", 1, 0, "keyword_not_matched", [], "gdelt_doc")
    monkeypatch.setattr("backend.api.live_monitor_execution.fetch_source", lambda *_args: fake)
    assert request("POST", "/api/live-monitor/run", {"background": False, "live_fetch": True, "providers": ["gdelt_doc"]}).json()["alert_count"] == 0
    assert request("GET", "/api/alerts").json()["count"] == 0


def test_background_monitor_reuses_queue_client_without_running_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHLIST_STORE_PATH", str(tmp_path / "watchlists.json"))
    monkeypatch.setenv("LIVE_MONITOR_RUN_STORE_PATH", str(tmp_path / "runs.json"))
    assert request("POST", "/api/watchlists", {"entity_name": "Acme", "enabled": True}).status_code == 201
    monkeypatch.setattr("backend.api.live_monitor_routes.submit_live_monitor_job", lambda *_args: "monitor-job")
    response = request("POST", "/api/live-monitor/run", {"background": True, "live_fetch": False})
    assert response.status_code == 201
    assert response.json()["status"] == "queued"
    assert response.json()["automatic_publish"] is False
    assert request("GET", f"/api/live-monitor/runs/{response.json()['monitor_run_id']}").status_code == 200
