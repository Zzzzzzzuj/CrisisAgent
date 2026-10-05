import json

import pytest
from fastapi.testclient import TestClient

from backend.harness.service import build_default_harness_spec, get_effective_harness_spec
from backend.main import app


def test_default_harness_preserves_existing_workflow_and_is_json_safe():
    spec = build_default_harness_spec()
    assert spec["workflow"]["agent_order"] == ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]
    assert spec["metadata"]["harness_id"] == "crisisagent-default"
    json.dumps(spec)


def test_dynamic_runtime_result_contains_default_harness_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setattr("backend.core.runtime_tasks.save_checkpoint", lambda state: None)
    from backend.core.runtime_tasks import run_dynamic_sync_with_metadata

    result = run_dynamic_sync_with_metadata("产品质量受到消费者投诉", metadata={})
    assert result["harness_spec"]["metadata"]["harness_id"] == "crisisagent-default"
    assert all(set(item["harness"]) == {"harness_id", "harness_version", "spec_hash"} for item in result["execution_trace"])


def test_harness_repository_can_copy_and_enable_version(tmp_path, monkeypatch):
    path = tmp_path / "harnesses.json"
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(path))
    monkeypatch.setenv("HARNESS_COMPARISON_STORE_PATH", str(tmp_path / "comparisons.json"))
    from backend.harness.service import (
        approve_harness_version,
        copy_harness_version,
        mark_harness_evaluated,
        set_harness_enabled,
    )
    from backend.evaluation.harness_comparison_store import get_harness_comparison_store

    copied = copy_harness_version("crisisagent-default", "1.0.0", "1.1.0")
    assert copied["metadata"]["status"] == "draft"
    with pytest.raises(ValueError, match="human-approved"):
        set_harness_enabled(copied["metadata"]["harness_id"], "1.1.0")
    gate = {"passed": True, "reason": "deterministic test gate"}
    mark_harness_evaluated(copied["metadata"]["harness_id"], "1.1.0", "comparison-1", gate)
    get_harness_comparison_store().save({
        "comparison_id": "comparison-1",
        "mode": "main_workflow_replay",
        "baseline": {"harness_id": "crisisagent-default", "version": "1.0.0", "metrics": {}, "cases": []},
        "candidate": {"harness_id": copied["metadata"]["harness_id"], "version": "1.1.0", "metrics": {}, "cases": []},
        "policy_diff": {},
    })
    approve_harness_version(copied["metadata"]["harness_id"], "1.1.0", "comparison-1", "test-reviewer", gate)
    enabled = set_harness_enabled(copied["metadata"]["harness_id"], "1.1.0")
    assert enabled["metadata"]["status"] == "active"
    assert get_effective_harness_spec(copied["metadata"]["harness_id"], "1.1.0")["metadata"]["version"] == "1.1.0"


def test_invalid_harness_cannot_change_agent_order():
    spec = build_default_harness_spec()
    spec["workflow"]["agent_order"] = ["legal"]
    with pytest.raises(ValueError, match="Agent order"):
        from backend.harness.spec import validate_harness_spec
        validate_harness_spec(spec)


def test_harness_api_lists_default_and_supports_offline_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setattr("backend.api.harness_routes.write_audit", lambda *args, **kwargs: None)
    client = TestClient(app)
    listed = client.get("/api/harnesses")
    assert listed.status_code == 200
    assert listed.json()["harnesses"][0]["metadata"]["harness_id"] == "crisisagent-default"

    spec = build_default_harness_spec()
    spec["metadata"].update({"harness_id": "candidate", "version": "1.0.1", "status": "draft"})
    created = client.post("/api/harnesses", json={"spec": spec})
    assert created.status_code == 201
    assert created.json()["metadata"]["status"] == "draft"
