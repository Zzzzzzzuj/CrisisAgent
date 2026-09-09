from __future__ import annotations

import asyncio

import httpx

from backend.ingestion.schemas import RawSentimentItem
from backend.ingestion.source_adapters import FetchResult
from backend.main import app


def _request(method: str, url: str, json_body: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json_body)

    return asyncio.run(send_request())


def _source(source_id: str, *, enabled: bool = True, max_items: int = 3) -> dict:
    return {
        "source_id": source_id,
        "source_name": source_id,
        "source_type": "rss",
        "url": f"https://example.com/{source_id}.xml",
        "enabled": enabled,
        "company_keywords": ["示例公司"],
        "risk_keywords": ["投诉"],
        "respect_robots": True,
        "rate_limit_seconds": 0,
        "timeout_seconds": 10,
        "max_items": max_items,
    }


def _item(item_id: str = "item-1") -> RawSentimentItem:
    return RawSentimentItem(
        item_id=item_id,
        source_name="example",
        source_url="https://example.com/item",
        title="示例公司产品投诉",
        content="示例公司产品收到消费者投诉，相关事实尚待核实。",
        published_at="2026-09-08T00:00:00+00:00",
        company="示例公司",
        fact_status="unverified",
    )


def _post_source(monkeypatch, tmp_path, source_id: str, enabled: bool = True, max_items: int = 3):
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(tmp_path / "runs.json"))
    return _request("POST", "/api/sources", _source(source_id, enabled=enabled, max_items=max_items))


def test_default_run_is_non_live_and_saved_without_network(monkeypatch, tmp_path):
    _post_source(monkeypatch, tmp_path, "safe_source")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("non-live ingestion must not call a network adapter")

    monkeypatch.setattr("backend.api.ingestion_execution.RssSourceAdapter.fetch", fail_if_called)
    response = _request("POST", "/api/ingestion/run", {})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["live_fetch"] is False
    assert body["source_results"][0]["status"] == "disabled"
    assert body["source_results"][0]["failed_reason"] == "live_fetch_disabled"
    assert body["automatic_publish"] is False
    assert (tmp_path / "runs.json").exists()


def test_dry_run_never_fetches_or_writes(monkeypatch, tmp_path):
    _post_source(monkeypatch, tmp_path, "dry_source")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry run must not call a network adapter")

    monkeypatch.setattr("backend.api.ingestion_execution.RssSourceAdapter.fetch", fail_if_called)
    response = _request(
        "POST",
        "/api/ingestion/run",
        {"live_fetch": True, "dry_run": True},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "dry_run"
    assert response.json()["source_results"][0]["failed_reason"] == "dry_run"
    assert not (tmp_path / "runs.json").exists()


def test_source_ids_filter_and_override_cannot_exceed_source_limit(monkeypatch, tmp_path):
    _post_source(monkeypatch, tmp_path, "source_a", max_items=2)
    assert _request("POST", "/api/sources", _source("source_b")).status_code == 201

    response = _request(
        "POST",
        "/api/ingestion/run",
        {"source_ids": ["source_a"], "max_items_override": 3},
    )
    assert response.status_code == 422

    response = _request(
        "POST",
        "/api/ingestion/run",
        {"source_ids": ["source_a"]},
    )
    assert response.status_code == 201
    assert [item["source_id"] for item in response.json()["source_results"]] == ["source_a"]


def test_live_fetch_uses_existing_adapter_and_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "true")
    _post_source(monkeypatch, tmp_path, "live_source")

    def fake_fetch(self, source):
        return FetchResult(
            source_id=source.source_id,
            source_name=source.source_name,
            status="collected",
            fetched_count=1,
            matched_count=1,
            failed_reason=None,
            items=[_item()],
        )

    monkeypatch.setattr("backend.api.ingestion_execution.RssSourceAdapter.fetch", fake_fetch)
    response = _request("POST", "/api/ingestion/run", {"live_fetch": True})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["raw_count"] == 1
    assert body["deduped_count"] == 1
    assert body["cluster_count"] == 1
    assert body["source_results"][0]["status"] == "collected"


def test_partial_run_preserves_no_match_and_failed_distinction(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "true")
    _post_source(monkeypatch, tmp_path, "no_match")
    assert _request("POST", "/api/sources", _source("failed_source")).status_code == 201

    def fake_fetch(self, source):
        if source.source_id == "no_match":
            return FetchResult(source.source_id, source.source_name, "no_match", 2, 0, None, [])
        return FetchResult(source.source_id, source.source_name, "failed", 0, 0, "fake_error", [])

    monkeypatch.setattr("backend.api.ingestion_execution.RssSourceAdapter.fetch", fake_fetch)
    response = _request("POST", "/api/ingestion/run", {"live_fetch": True})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "partial"
    statuses = {item["source_id"]: item["status"] for item in body["source_results"]}
    assert statuses == {"no_match": "no_match", "failed_source": "failed"}


def test_list_detail_and_missing_run(monkeypatch, tmp_path):
    _post_source(monkeypatch, tmp_path, "list_source")
    created = _request("POST", "/api/ingestion/run", {}).json()

    response = _request("GET", "/api/ingestion/runs")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["runs"][0]["run_id"] == created["run_id"]

    response = _request("GET", f"/api/ingestion/runs/{created['run_id']}")
    assert response.status_code == 200
    assert response.json()["run_id"] == created["run_id"]

    assert _request("GET", "/api/ingestion/runs/missing").status_code == 404
    assert _request("POST", "/api/ingestion/run", {"source_ids": ["missing"]}).status_code == 404


def test_api_live_fetch_requires_explicit_server_enable(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "false")
    _post_source(monkeypatch, tmp_path, "protected_source", enabled=True)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("disabled API live fetch must not call an adapter")

    monkeypatch.setattr("backend.api.ingestion_execution.RssSourceAdapter.fetch", fail_if_called)
    response = _request("POST", "/api/ingestion/run", {"live_fetch": True})
    assert response.status_code == 403
    assert "live fetch is disabled by server config" in response.json()["detail"]


def test_dry_run_is_allowed_when_api_live_fetch_is_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "false")
    _post_source(monkeypatch, tmp_path, "dry_protected_source", enabled=True)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry run must not call an adapter")

    monkeypatch.setattr("backend.api.ingestion_execution.RssSourceAdapter.fetch", fail_if_called)
    response = _request("POST", "/api/ingestion/run", {"live_fetch": True, "dry_run": True})
    assert response.status_code == 201
    assert response.json()["status"] == "dry_run"


def test_api_live_fetch_can_use_existing_adapter_when_explicitly_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "true")
    _post_source(monkeypatch, tmp_path, "enabled_source", enabled=True)

    def fake_fetch(self, source):
        return FetchResult(source.source_id, source.source_name, "no_match", 1, 0, None, [])

    monkeypatch.setattr("backend.api.ingestion_execution.RssSourceAdapter.fetch", fake_fetch)
    response = _request("POST", "/api/ingestion/run", {"live_fetch": True})
    assert response.status_code == 201
    assert response.json()["source_results"][0]["status"] == "no_match"
