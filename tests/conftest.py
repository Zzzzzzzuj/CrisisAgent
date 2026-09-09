from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_product_runtime_stores(monkeypatch, tmp_path):
    """Keep every test away from user runtime JSON files and cached state."""
    paths = {
        "SOURCE_REGISTRY_RUNTIME_PATH": "source_registry.runtime.json",
        "INGESTION_RUN_STORE_PATH": "ingestion_runs.runtime.json",
        "CRISIS_EVENT_STORE_PATH": "crisis_events.runtime.json",
        "EVENT_AGENT_RUN_STORE_PATH": "event_agent_runs.runtime.json",
        "EVAL_RUN_STORE_PATH": "eval_runs.runtime.json",
        "AUDIT_LOG_STORE_PATH": "audit_logs.runtime.json",
    }
    for variable, filename in paths.items():
        monkeypatch.setenv(variable, str(tmp_path / filename))
