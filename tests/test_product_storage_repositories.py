from __future__ import annotations

import importlib.util
from pathlib import Path

from backend.product_storage.config import ProductStorageConfigurationError, get_product_storage_backend
from backend.product_storage.factory import get_audit_log_repository, get_crisis_event_repository, get_eval_run_repository


ROOT = Path(__file__).resolve().parents[1]


def _load_export_module():
    spec = importlib.util.spec_from_file_location("product_storage_export", ROOT / "scripts" / "export_product_storage.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_product_storage_is_json(monkeypatch):
    monkeypatch.delenv("PRODUCT_STORAGE", raising=False)
    assert get_product_storage_backend() == "json"


def test_json_repositories_use_existing_temp_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("PRODUCT_STORAGE", "json")
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    monkeypatch.setenv("EVAL_RUN_STORE_PATH", str(tmp_path / "eval.json"))
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(tmp_path / "events.json"))
    audit = get_audit_log_repository()
    audit.append({"actor_id": "tester", "actor_role": "admin", "action": "test", "resource_type": "test", "resource_id": "1", "result": "success", "reason": "", "metadata": {}})
    assert audit.list_logs()[0]["actor_id"] == "tester"
    evals = get_eval_run_repository()
    evals.save({"eval_run_id": "eval-1"})
    assert evals.list_runs()[0]["eval_run_id"] == "eval-1"
    assert get_crisis_event_repository().list_events() == []


def test_postgres_without_url_is_explicit(monkeypatch):
    monkeypatch.setenv("PRODUCT_STORAGE", "postgres")
    monkeypatch.delenv("PRODUCT_DATABASE_URL", raising=False)
    repository = get_audit_log_repository()
    try:
        repository.list_logs()
    except ProductStorageConfigurationError as exc:
        assert "PRODUCT_DATABASE_URL" in str(exc)
    else:
        raise AssertionError("Postgres repository should require explicit configuration")


def test_export_payload_handles_empty_and_existing_json_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_REGISTRY_RUNTIME_PATH", str(tmp_path / "sources.json"))
    monkeypatch.setenv("INGESTION_RUN_STORE_PATH", str(tmp_path / "ingestion.json"))
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(tmp_path / "events.json"))
    monkeypatch.setenv("EVENT_AGENT_RUN_STORE_PATH", str(tmp_path / "agent-runs.json"))
    monkeypatch.setenv("EVAL_RUN_STORE_PATH", str(tmp_path / "evals.json"))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    export_module = _load_export_module()

    empty_payload = export_module.export_payload()
    assert empty_payload["sources"] == []
    assert empty_payload["audit_logs"] == []

    get_audit_log_repository().append(
        {
            "actor_id": "tester",
            "actor_role": "admin",
            "action": "export.test",
            "resource_type": "test",
            "resource_id": "record-1",
            "result": "success",
            "reason": "",
            "metadata": {},
        }
    )
    existing_payload = export_module.export_payload()
    assert existing_payload["audit_logs"][0]["resource_id"] == "record-1"
