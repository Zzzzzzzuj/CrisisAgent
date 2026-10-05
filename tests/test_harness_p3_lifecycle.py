from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.harness.service import (
    approve_harness_version,
    build_default_harness_spec,
    get_runtime_harness_spec,
    mark_harness_evaluated,
    rollback_harness_version,
    set_harness_enabled,
)
from backend.harness.store import JsonHarnessRepository
from backend.main import app


ROOT = Path(__file__).resolve().parents[1]
DRILL_PATH = ROOT / "evaluation" / "p3_harness_lifecycle_frozen.json"
DRILL_SHA256 = "575c7e007d460c6d9f9d8ca3096817a6bc83b25f8ccfb523527e2182d032ac98"
REPLAY_PATH = ROOT / "data" / "harness_replay_cases.json"
REPLAY_SHA256 = "841356517870b0b08beb36c1ef50cf987489ba1a9f9c5f67c90b6669b765b200"
REJECTED_VERSION = "1.0.1-rv004-writer-v2-policy"
REJECTED_COMPARISON = "writer-v2-0f59f9cb-0465-4685-9e4d-54e39ca4c586"


def _normalized_sha(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _frozen_drill() -> dict:
    assert _normalized_sha(DRILL_PATH) == DRILL_SHA256
    assert _normalized_sha(REPLAY_PATH) == REPLAY_SHA256
    return json.loads(DRILL_PATH.read_text(encoding="utf-8"))


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setenv("HARNESS_COMPARISON_STORE_PATH", str(tmp_path / "comparisons.json"))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    repository = JsonHarnessRepository()
    repository.save(build_default_harness_spec())

    persisted = json.loads((ROOT / "data" / "harness_specs.runtime.json").read_text(encoding="utf-8"))
    rejected = next(row for row in persisted["specs"]
                    if row.get("metadata", {}).get("version") == REJECTED_VERSION)
    repository.save(deepcopy(rejected))
    return TestClient(app)


def test_p3_frozen_drill_and_lifecycle_guards(tmp_path, monkeypatch):
    frozen = _frozen_drill()
    client = _client(tmp_path, monkeypatch)
    actor = {"X-User-Id": "p3-drill-operator", "X-User-Role": "admin"}
    harness_id = "crisisagent-default"
    base_version = frozen["base_version"]["version"]
    candidate_version = frozen["safe_candidate"]["version"]

    assert get_runtime_harness_spec()["metadata"]["version"] == base_version
    copied = client.post(f"/api/harnesses/{harness_id}/{base_version}/copy",
                         json={"new_version": candidate_version})
    assert copied.status_code == 201
    assert copied.json()["metadata"]["status"] == "draft"
    assert copied.json()["metadata"].get("comparison_id") is None

    patched = client.patch(f"/api/harnesses/{harness_id}/{candidate_version}/candidate", json={
        "changes": frozen["safe_candidate"]["change"],
        "change_summary": frozen["safe_candidate"]["change_summary"],
    })
    assert patched.status_code == 200
    assert patched.json()["metadata"]["changed_fields"] == ["retrieval_policy.max_context_pollution_rate"]

    # N1: draft and unevaluated candidates cannot activate through either boundary.
    assert client.post(f"/api/harnesses/{harness_id}/{candidate_version}/enable", headers=actor).status_code == 409
    with pytest.raises(ValueError, match="human-approved"):
        set_harness_enabled(harness_id, candidate_version)

    evaluated = client.post(f"/api/harnesses/{harness_id}/{candidate_version}/evaluate", headers=actor, json={
        "baseline_harness_id": harness_id,
        "baseline_version": base_version,
        "mode": frozen["safe_candidate"]["evaluation_mode"],
        "replay_case_ids": frozen["safe_candidate"]["replay_case_ids"],
    })
    assert evaluated.status_code == 200
    comparison = evaluated.json()["comparison"]
    comparison_id = comparison["comparison_id"]
    assert comparison["offline_only"] is True
    assert comparison["case_count"] == len(frozen["safe_candidate"]["replay_case_ids"])
    assert comparison["gate_result"]["passed"] is True
    assert comparison["policy_safety_gate"]["passed"] is True
    assert evaluated.json()["harness"]["metadata"]["status"] == "EVALUATED"
    assert get_runtime_harness_spec()["metadata"]["version"] == base_version

    # N4: evaluation and safety PASS still require an explicit approval action.
    assert client.post(f"/api/harnesses/{harness_id}/{candidate_version}/enable", headers=actor).status_code == 409
    approved = client.post(f"/api/harnesses/{harness_id}/{candidate_version}/approve", headers=actor, json={
        "comparison_id": comparison_id,
        "reason": "Human approval for deterministic P3 lifecycle drill.",
    })
    assert approved.status_code == 200
    approval = approved.json()["metadata"]["approval"]
    assert approval["comparison_id"] == comparison_id
    assert approval["reviewer"] == actor["X-User-Id"]
    assert approval["approved_at"]
    assert approval["gate_result"]["passed"] is True

    activated = client.post(f"/api/harnesses/{harness_id}/{candidate_version}/enable", headers=actor)
    assert activated.status_code == 200
    assert activated.json()["metadata"]["status"] == "active"
    assert get_runtime_harness_spec()["metadata"]["version"] == candidate_version

    # N8: repeated activation is safe; a new repository instance sees persisted V2.
    second_activation = client.post(f"/api/harnesses/{harness_id}/{candidate_version}/enable", headers=actor)
    assert second_activation.status_code == 200
    reloaded = JsonHarnessRepository().list_specs()
    assert next(row for row in reloaded if row["metadata"]["version"] == candidate_version)["metadata"]["status"] == "active"
    assert get_runtime_harness_spec()["metadata"]["version"] == candidate_version

    # The actual persisted RV-004 reject remains unchanged and cannot be activated or restored.
    assert client.post(f"/api/harnesses/{harness_id}/{REJECTED_VERSION}/enable", headers=actor).status_code == 409
    assert client.post(f"/api/harnesses/{harness_id}/{REJECTED_VERSION}/rollback", headers=actor).status_code == 409
    rejected_row = next(row for row in JsonHarnessRepository().list_specs()
                        if row["metadata"]["version"] == REJECTED_VERSION)
    assert rejected_row["metadata"]["status"] == "REJECTED"
    assert rejected_row["metadata"]["comparison_id"] == REJECTED_COMPARISON

    # N6: unknown rollback targets are denied without changing the active version.
    assert client.post(f"/api/harnesses/{harness_id}/unknown-version/rollback", headers=actor).status_code == 404
    assert get_runtime_harness_spec()["metadata"]["version"] == candidate_version

    rolled_back = client.post(f"/api/harnesses/{harness_id}/{base_version}/rollback", headers=actor)
    assert rolled_back.status_code == 200
    assert rolled_back.json()["metadata"]["status"] == "ACTIVE"
    assert get_runtime_harness_spec()["metadata"]["version"] == base_version

    # N9: repeated rollback is safe and the previous snapshot survives reload.
    second_rollback = client.post(f"/api/harnesses/{harness_id}/{base_version}/rollback", headers=actor)
    assert second_rollback.status_code == 200
    persisted_after = JsonHarnessRepository().list_specs()
    assert next(row for row in persisted_after if row["metadata"]["version"] == base_version)["metadata"]["status"] == "ACTIVE"
    assert next(row for row in persisted_after if row["metadata"]["version"] == candidate_version)["metadata"]["status"] == "ROLLED_BACK"


@pytest.mark.parametrize("failed_gate", [
    {"passed": False, "checks": {"evaluation": False}, "failure_reasons": ["evaluation_failed"]},
    {"passed": False, "checks": {"safety": False}, "failure_reasons": ["safety_failed"]},
])
def test_p3_failed_evaluation_or_safety_cannot_be_approved_or_activated(
    tmp_path, monkeypatch, failed_gate,
):
    from backend.harness.service import copy_harness_version

    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    JsonHarnessRepository().save(build_default_harness_spec())
    version = f"failed-{failed_gate['failure_reasons'][0]}"
    candidate = copy_harness_version("crisisagent-default", "1.0.0", version)
    harness_id = candidate["metadata"]["harness_id"]
    mark_harness_evaluated(harness_id, version, "failed-comparison", failed_gate)
    with pytest.raises(ValueError, match="passing evaluation gate"):
        approve_harness_version(harness_id, version, "failed-comparison", "p3-drill-operator", failed_gate)
    with pytest.raises(ValueError, match="human-approved"):
        set_harness_enabled(harness_id, version)
    with pytest.raises(ValueError, match="Only APPROVED or ACTIVE"):
        rollback_harness_version(harness_id, version)
    assert JsonHarnessRepository().list_specs()[0]["metadata"]["status"] == "active"


def test_p3_approval_rejects_caller_supplied_pass_without_persisted_comparison(tmp_path, monkeypatch):
    from backend.harness.service import copy_harness_version

    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setenv("HARNESS_COMPARISON_STORE_PATH", str(tmp_path / "comparisons.json"))
    JsonHarnessRepository().save(build_default_harness_spec())
    candidate = copy_harness_version("crisisagent-default", "1.0.0", "unbacked-approval")
    harness_id = candidate["metadata"]["harness_id"]
    mark_harness_evaluated(harness_id, "unbacked-approval", "missing-comparison", {"passed": True})
    with pytest.raises(ValueError, match="persisted evaluation comparison"):
        approve_harness_version(
            harness_id, "unbacked-approval", "missing-comparison", "p3-drill-operator", {"passed": True},
        )


def test_p3_historical_reject_record_is_unchanged():
    frozen = _frozen_drill()
    specs_path = ROOT / "data" / "harness_specs.runtime.json"
    comparisons_path = ROOT / "data" / "harness_comparisons.runtime.json"
    specs_before = specs_path.read_bytes()
    comparisons_before = comparisons_path.read_bytes()
    specs = json.loads(specs_before).get("specs", [])
    comparisons = json.loads(comparisons_before).get("comparisons", [])
    candidate = next(row for row in specs
                     if row.get("metadata", {}).get("version") == frozen["reject_candidate"]["version"])
    comparison = next(row for row in comparisons
                      if row.get("comparison_id") == frozen["reject_candidate"]["comparison_id"])
    assert candidate["metadata"]["status"] == "REJECTED"
    assert comparison.get("gate_result", {}).get("passed") is False
    assert candidate["metadata"]["comparison_id"] == comparison["comparison_id"]
    assert specs_path.read_bytes() == specs_before
    assert comparisons_path.read_bytes() == comparisons_before
