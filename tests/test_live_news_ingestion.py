from __future__ import annotations

import asyncio

import httpx

from backend.api.ingestion_execution import fetch_source
from backend.ingestion.schemas import RawSentimentItem
from backend.ingestion.source_adapters import FetchResult, GdeltDocSourceAdapter, NewsApiSourceAdapter
from backend.ingestion.source_registry import SourceDefinition
from backend.main import app


def request(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.request(method, path, json=body, headers=headers)

    return asyncio.run(send())


def admin_headers():
    return {"X-User-Id": "admin-1", "X-User-Role": "admin"}


def source_payload(source_id: str, source_type: str, **extra):
    base = {
        "source_id": source_id,
        "source_name": source_id,
        "source_type": source_type,
        "url": "https://news.example.test/api",
        "risk_keywords": ["投诉"],
        "query": "示例公司 投诉",
        "enabled": True,
    }
    return {**base, **extra}


def configure_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(tmp_path / "runs.json"))
    monkeypatch.setenv("COLLECTED_ITEM_STORE_PATH", str(tmp_path / "items.json"))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://news.example.test")
            raise httpx.HTTPStatusError("bad status", request=request, response=httpx.Response(self.status_code, request=request))

    def json(self):
        return self.payload


def test_gdelt_and_newsapi_sources_can_be_created_without_secret(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    gdelt = request("POST", "/api/sources", source_payload("gdelt", "gdelt_doc"), admin_headers())
    news = request("POST", "/api/sources", source_payload("news", "news_api", api_key_env="NEWSAPI_KEY"), admin_headers())

    assert gdelt.status_code == 201
    assert news.status_code == 201
    assert news.json()["api_key_env"] == "NEWSAPI_KEY"
    assert "NEWSAPI_KEY" not in str(news.json().get("query", ""))


def test_newsapi_missing_key_is_a_controlled_failure(monkeypatch):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    source = SourceDefinition("news", "News", "news_api", "https://news.example.test/api", True, risk_keywords=("投诉",), query="示例公司 投诉", api_key_env="NEWSAPI_KEY")
    result = NewsApiSourceAdapter(http_get=lambda **_: (_ for _ in ()).throw(AssertionError("must not call"))).fetch(source)

    assert result.status == "failed"
    assert result.failed_reason == "missing_api_key"
    assert result.error_type == "missing_api_key"


def test_live_news_adapters_use_fake_http_and_return_preview_items():
    gdelt_source = SourceDefinition("gdelt", "GDELT", "gdelt_doc", "https://news.example.test/gdelt", True, risk_keywords=("投诉",), query="示例公司 投诉")
    news_source = SourceDefinition("news", "News", "news_api", "https://news.example.test/news", True, risk_keywords=("投诉",), query="示例公司 投诉", api_key_env="TEST_NEWS_KEY")
    gdelt_response = FakeResponse({"articles": [{"title": "示例公司投诉事件", "url": "https://example.test/a", "summary": "投诉升级", "seendate": "2026-01-01T00:00:00Z"}]})
    news_response = FakeResponse({"articles": [{"title": "示例公司投诉事件", "url": "https://example.test/b", "description": "投诉升级", "publishedAt": "2026-01-01T00:00:00Z"}]})

    gdelt = GdeltDocSourceAdapter(http_get=lambda *args, **kwargs: gdelt_response).fetch(gdelt_source)
    import os
    os.environ["TEST_NEWS_KEY"] = "not-stored-in-source"
    news = NewsApiSourceAdapter(http_get=lambda *args, **kwargs: news_response).fetch(news_source)
    del os.environ["TEST_NEWS_KEY"]

    assert gdelt.status == "collected" and gdelt.adapter_type == "gdelt_doc" and gdelt.items[0].content == "投诉升级"
    assert news.status == "collected" and news.adapter_type == "news_api" and news.items[0].source_url.endswith("/b")


def test_adapter_timeout_and_rate_limit_are_controlled_failures():
    source = SourceDefinition("gdelt", "GDELT", "gdelt_doc", "https://news.example.test/gdelt", True, risk_keywords=("投诉",), query="示例公司 投诉")
    timeout = GdeltDocSourceAdapter(http_get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.TimeoutException("timeout"))).fetch(source)
    limited = GdeltDocSourceAdapter(http_get=lambda *args, **kwargs: FakeResponse({}, status_code=429)).fetch(source)

    assert timeout.status == "failed" and timeout.error_type == "timeout"
    assert limited.status == "failed" and limited.error_type == "rate_limited"


def test_live_fetch_guard_preview_and_collected_item_store(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    created = request("POST", "/api/sources", source_payload("gdelt", "gdelt_doc"), admin_headers())
    assert created.status_code == 201

    monkeypatch.setattr("backend.api.ingestion_execution.fetch_source", lambda source: (_ for _ in ()).throw(AssertionError("no network when disabled")))
    disabled = request("POST", "/api/ingestion/run", {"source_ids": ["gdelt"], "live_fetch": False}, admin_headers())
    assert disabled.status_code == 201
    assert disabled.json()["source_results"][0]["failed_reason"] == "live_fetch_disabled"
    assert request("POST", "/api/sources/gdelt/fetch-preview", {"live_fetch": True}, admin_headers()).status_code == 403

    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "true")
    item = RawSentimentItem("raw-1", "GDELT", "https://example.test/article", "示例公司投诉事件", "投诉升级，监管关注。", "2026-01-01T00:00:00Z", "示例公司")
    fake_result = FetchResult("gdelt", "gdelt", "collected", 1, 1, None, [item], "gdelt_doc", 4, None, None)
    monkeypatch.setattr("backend.api.ingestion_execution.fetch_source", lambda source: fake_result)

    preview = request("POST", "/api/sources/gdelt/fetch-preview", {"live_fetch": True}, admin_headers())
    assert preview.status_code == 200
    assert request("GET", "/api/ingestion/runs", headers=admin_headers()).json()["count"] == 1
    assert request("GET", "/api/collected-items", headers=admin_headers()).json()["count"] == 0

    formal = request("POST", "/api/ingestion/run", {"source_ids": ["gdelt"], "live_fetch": True}, admin_headers())
    assert formal.status_code == 201
    items = request("GET", "/api/collected-items", headers=admin_headers()).json()["items"]
    assert len(items) == 1
    assert items[0]["content_preview"]
    assert "content" not in items[0]
    filtered = request("GET", "/api/collected-items?source_id=gdelt", headers=admin_headers())
    assert filtered.status_code == 200 and filtered.json()["count"] == 1


def test_background_ingestion_keeps_redis_queue_path(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    request("POST", "/api/sources", source_payload("gdelt", "gdelt_doc"), admin_headers())
    monkeypatch.setenv("ENABLE_API_LIVE_FETCH", "true")
    monkeypatch.setattr("backend.api.ingestion_routes.submit_ingestion_job", lambda run_id, payload, user: f"job-{run_id}")
    response = request("POST", "/api/ingestion/run", {"source_ids": ["gdelt"], "live_fetch": True, "background": True}, admin_headers())

    assert response.status_code == 201
    assert response.json()["execution_mode"] == "background"
    assert response.json()["queue_backend"] == "redis"


def test_collected_items_are_read_only_for_workspace_roles(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    for role in ("admin", "operator", "legal_reviewer", "viewer"):
        headers = {"X-User-Id": role, "X-User-Role": role}
        assert request("GET", "/api/collected-items", headers=headers).status_code == 200
    assert request("POST", "/api/collected-items", {}, admin_headers()).status_code == 405
