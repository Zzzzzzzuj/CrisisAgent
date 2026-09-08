from __future__ import annotations

import asyncio
import json

import httpx

from backend.main import app


def _request(method: str, url: str, json_body: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json_body)

    return asyncio.run(send_request())


def _source(source_id: str = "example_rss") -> dict:
    return {
        "source_id": source_id,
        "source_name": "Example RSS",
        "source_type": "rss",
        "url": "https://example.com/feed.xml",
        "enabled": False,
        "company_keywords": ["示例公司"],
        "risk_keywords": ["投诉"],
        "respect_robots": True,
        "rate_limit_seconds": 3,
        "timeout_seconds": 10,
        "max_items": 3,
    }


def test_source_registry_api_uses_isolated_json_store(monkeypatch, tmp_path):
    path = tmp_path / "source_registry.runtime.json"
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(path))

    response = _request("GET", "/api/sources")
    assert response.status_code == 200
    assert response.json() == {"sources": [], "count": 0}

    response = _request("POST", "/api/sources", _source())
    assert response.status_code == 201
    assert response.json()["enabled"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["sources"][0]["source_id"] == "example_rss"

    response = _request("GET", "/api/sources")
    assert response.json()["count"] == 1


def test_source_registry_rejects_duplicate_https_type_and_empty_keywords(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "registry.json"))
    assert _request("POST", "/api/sources", _source()).status_code == 201
    assert _request("POST", "/api/sources", _source()).status_code == 409

    invalid_url = _source("bad_url")
    invalid_url["url"] = "http://example.com/feed.xml"
    assert _request("POST", "/api/sources", invalid_url).status_code == 422

    invalid_type = _source("bad_type")
    invalid_type["source_type"] = "crawler"
    assert _request("POST", "/api/sources", invalid_type).status_code == 422

    empty_keywords = _source("empty_keywords")
    empty_keywords["company_keywords"] = []
    empty_keywords["risk_keywords"] = []
    assert _request("POST", "/api/sources", empty_keywords).status_code == 422


def test_source_registry_patch_and_offline_test(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "registry.json"))
    assert _request("POST", "/api/sources", _source()).status_code == 201

    response = _request(
        "PATCH",
        "/api/sources/example_rss",
        {"enabled": True, "risk_keywords": ["召回", "监管"]},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["risk_keywords"] == ["召回", "监管"]

    response = _request("POST", "/api/sources/example_rss/test")
    assert response.status_code == 200
    assert response.json()["test_status"] == "config_valid"
    assert response.json()["live_fetch_triggered"] is False

    assert _request("PATCH", "/api/sources/missing", {"enabled": True}).status_code == 404


def test_source_registry_does_not_change_existing_api_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("AGENT_MODE", "mock")
    response = _request("POST", "/api/crisis/run", {"event": "测试事件"})
    assert response.status_code == 200
    assert "final_statement" in response.json()
