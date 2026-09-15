from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.harness.proposal import build_proposal, validate_allowed_patch
from backend.harness.spec import build_default_harness_spec
from backend.main import app


def test_failure_tags_map_to_safe_proposal_patch():
    proposal = build_proposal(
        {"failure_tags": ["tool_timeout", "evidence_conflict"], "diagnosis_summary": "deterministic failure"},
        build_default_harness_spec(), replay_case_id="replay-1",
    )
    assert proposal["status"] == "DRAFT"
    assert "skills_tools.execution_budget.max_runtime_ms" in proposal["allowed_patch"]
    assert proposal["allowed_patch"]["review_policy.triggers.evidence_conflict"] is True
    assert proposal["expected_validation"]["replay_case_ids"] == ["replay-1"]


def test_unsafe_or_unknown_patch_is_rejected():
    with pytest.raises(ValueError):
        validate_allowed_patch({"workflow.agent_order": []})
    with pytest.raises(ValueError):
        validate_allowed_patch({"review_policy.triggers.evidence_conflict": False})


def test_proposal_api_accept_apply_reaches_evaluated_not_active(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_PROPOSAL_STORE_PATH", str(tmp_path / "proposals.json"))
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setenv("HARNESS_COMPARISON_STORE_PATH", str(tmp_path / "comparisons.json"))
    monkeypatch.setattr("backend.api.proposal_routes.write_audit", lambda *args, **kwargs: None)
    client = TestClient(app)
    created = client.post("/api/harness-proposals", json={
        "baseline_harness_id": "crisisagent-default",
        "baseline_version": "1.0.0",
        "replay_case_id": "replay-1",
        "diagnosis": {"failure_tags": ["tool_retry_exhausted"], "diagnosis_summary": "retry exhausted", "recommended_harness_areas": ["tools_policy"]},
    })
    assert created.status_code == 201
    proposal_id = created.json()["proposal_id"]
    assert client.post(f"/api/harness-proposals/{proposal_id}/apply").status_code == 409
    assert client.post(f"/api/harness-proposals/{proposal_id}/accept", json={"reason": "reviewed"}).status_code == 200
    applied = client.post(f"/api/harness-proposals/{proposal_id}/apply")
    assert applied.status_code == 200
    assert applied.json()["proposal"]["status"] == "APPLIED"
    assert applied.json()["candidate"]["metadata"]["status"] == "EVALUATED"
    assert applied.json()["comparison"]["automatic_enable"] is False


def test_rejected_proposal_cannot_be_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_PROPOSAL_STORE_PATH", str(tmp_path / "proposals.json"))
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setattr("backend.api.proposal_routes.write_audit", lambda *args, **kwargs: None)
    client = TestClient(app)
    created = client.post("/api/harness-proposals", json={"baseline_harness_id": "crisisagent-default", "baseline_version": "1.0.0", "diagnosis": {"failure_tags": ["context_over_budget"]}})
    proposal_id = created.json()["proposal_id"]
    assert client.post(f"/api/harness-proposals/{proposal_id}/reject", json={"reason": "needs manual context review"}).status_code == 200
    assert client.post(f"/api/harness-proposals/{proposal_id}/apply").status_code == 409
