from __future__ import annotations

import asyncio
import httpx

from backend.main import app


def request(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.request(method, path, json=body, headers=headers)
    return asyncio.run(send())


def test_auth_disabled_keeps_demo_access(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    assert request("GET", "/api/dashboard/overview").status_code == 200


def test_role_denial_and_audit_log(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    viewer = {"X-User-Id": "viewer-1", "X-User-Role": "viewer"}
    denied = request("POST", "/api/sources", {"source_id": "x", "source_name": "x", "source_type": "rss", "url": "https://example.com", "risk_keywords": ["risk"]}, viewer)
    assert denied.status_code == 403
    admin = {"X-User-Id": "admin-1", "X-User-Role": "admin"}
    logs = request("GET", "/api/audit/logs", headers=admin)
    assert logs.status_code == 200
    assert any(item["result"] == "denied" and item["action"] == "source.create" for item in logs.json()["logs"])

