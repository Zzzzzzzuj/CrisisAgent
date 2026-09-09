from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from backend.api.audit_store import JsonAuditStore
from backend.product_storage.factory import get_audit_log_repository


def _entry(index: int) -> dict:
    return {
        "actor_id": "tester",
        "actor_role": "admin",
        "action": "test.write",
        "resource_type": "test",
        "resource_id": str(index),
        "result": "success",
        "reason": "",
        "metadata": {},
    }


def test_audit_append_is_atomic_and_thread_safe(tmp_path):
    path = tmp_path / "audit.json"
    store = JsonAuditStore(path)
    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(lambda index: store.append(_entry(index)), range(24)))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["logs"]) == 24
    assert len(store.list_logs(limit=100)) == 24


def test_audit_corruption_is_quarantined_without_breaking_future_api_writes(tmp_path):
    path = tmp_path / "audit.json"
    path.write_text('{"logs": []}\n{"extra": true}', encoding="utf-8")
    store = JsonAuditStore(path)

    assert store.list_logs() == []
    assert not path.exists()
    assert len(list(tmp_path.glob("audit.corrupt.*.json"))) == 1

    store.append(_entry(1))
    assert json.loads(path.read_text(encoding="utf-8"))["logs"][0]["resource_id"] == "1"


def test_audit_store_handles_empty_and_legacy_list_payloads(tmp_path):
    path = tmp_path / "audit.json"
    path.write_text("", encoding="utf-8")
    assert JsonAuditStore(path).list_logs() == []

    path.write_text(json.dumps([_entry(2)]), encoding="utf-8")
    assert JsonAuditStore(path).list_logs()[0]["resource_id"] == "2"


def test_repository_factory_resolves_the_current_env_path(monkeypatch, tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(first))
    get_audit_log_repository().append(_entry(1))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(second))
    get_audit_log_repository().append(_entry(2))

    assert JsonAuditStore(first).list_logs()[0]["resource_id"] == "1"
    assert JsonAuditStore(second).list_logs()[0]["resource_id"] == "2"
