from __future__ import annotations

from fastapi.testclient import TestClient

from backend.harness.spec import build_default_harness_spec, spec_hash
from backend.main import app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setenv("HARNESS_PROPOSAL_STORE_PATH", str(tmp_path / "proposals.json"))
    monkeypatch.setenv("HARNESS_COMPARISON_STORE_PATH", str(tmp_path / "comparisons.json"))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    return TestClient(app)


def test_bad_case_to_enable_and_rollback_is_scoped_and_audited(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    diagnosis = {
        "failure_tags": ["tool_timeout"],
        "diagnosis_summary": "tool execution exceeded the configured timeout",
        "evidence_refs": ["trace-17", "tool-4"],
        "recommended_harness_areas": ["tools_policy"],
    }
    created = client.post(
        "/api/harness-proposals",
        json={
            "baseline_harness_id": "crisisagent-default",
            "baseline_version": "1.0.0",
            "source_run_id": "run-17",
            "comparison_id": "comparison-source-1",
            "replay_case_id": "replay-tool-timeout-1",
            "diagnosis": diagnosis,
        },
    )
    assert created.status_code == 201
    proposal = created.json()
    assert proposal["status"] == "DRAFT"
    assert proposal["baseline_harness_id"] == "crisisagent-default"
    assert proposal["spec_hash"] == spec_hash(build_default_harness_spec())

    assert client.post(f"/api/harness-proposals/{proposal['proposal_id']}/apply").status_code == 409
    assert client.post(f"/api/harness-proposals/{proposal['proposal_id']}/accept", json={"reason": "reviewed bad case"}).status_code == 200
    applied = client.post(f"/api/harness-proposals/{proposal['proposal_id']}/apply")
    assert applied.status_code == 200
    body = applied.json()
    candidate = body["candidate"]
    comparison = body["comparison"]
    candidate_id = candidate["metadata"]["harness_id"]
    candidate_version = candidate["metadata"]["version"]
    assert body["proposal"]["status"] == "APPLIED"
    assert candidate["metadata"]["status"] == "EVALUATED"
    assert comparison["comparison_id"] == body["proposal"]["comparison_id"]
    assert comparison["baseline"]["spec_hash"] == proposal["spec_hash"]
    assert comparison["candidate"]["spec_hash"] == spec_hash(candidate)

    assert client.post(f"/api/harnesses/{candidate_id}/{candidate_version}/enable").status_code == 409
    approved = client.post(
        f"/api/harnesses/{candidate_id}/{candidate_version}/approve",
        json={"comparison_id": comparison["comparison_id"], "reason": "offline gates passed"},
    )
    assert approved.status_code == 200
    assert approved.json()["metadata"]["approval"]["comparison_id"] == comparison["comparison_id"]
    assert client.post(f"/api/harnesses/{candidate_id}/{candidate_version}/approve", json={"comparison_id": comparison["comparison_id"], "reason": "same approval"}).status_code == 200
    enabled = client.post(f"/api/harnesses/{candidate_id}/{candidate_version}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["metadata"]["status"] == "active"
    assert client.post(f"/api/harnesses/{candidate_id}/{candidate_version}/enable").status_code == 200

    # A second approved version makes rollback observable: it restores the first one.
    copied = client.post(f"/api/harnesses/{candidate_id}/{candidate_version}/copy", json={"new_version": "proposal-second"})
    assert copied.status_code == 201
    second_id = copied.json()["metadata"]["harness_id"]
    evaluated = client.post(f"/api/harnesses/{second_id}/proposal-second/evaluate", json={"baseline_harness_id": "crisisagent-default", "baseline_version": "1.0.0"})
    assert evaluated.status_code == 200
    second_comparison_id = evaluated.json()["comparison"]["comparison_id"]
    assert client.post(f"/api/harnesses/{second_id}/proposal-second/approve", json={"comparison_id": second_comparison_id, "reason": "second offline approval"}).status_code == 200
    assert client.post(f"/api/harnesses/{second_id}/proposal-second/enable").status_code == 200
    rolled_back = client.post(f"/api/harnesses/{candidate_id}/{candidate_version}/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["metadata"]["status"] == "ACTIVE"
    assert client.post(f"/api/harnesses/{candidate_id}/{candidate_version}/rollback").status_code == 200

    logs = client.get("/api/audit/logs")
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json().get("logs", [])]
    assert "harness_proposal.accept" in actions
    assert "harness_proposal.apply" in actions
    assert "harness.approve" in actions
    assert "harness.enable" in actions
    assert "harness.rollback" in actions


def test_proposal_apply_rejects_stale_baseline_hash(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    custom = build_default_harness_spec()
    custom["metadata"].update({"harness_id": "baseline-x", "version": "1.0.0", "status": "active"})
    assert client.post("/api/harnesses", json={"spec": custom}).status_code == 201
    proposal = client.post("/api/harness-proposals", json={
        "baseline_harness_id": "baseline-x",
        "baseline_version": "1.0.0",
        "diagnosis": {"failure_tags": ["tool_timeout"]},
    }).json()
    assert client.post(f"/api/harness-proposals/{proposal['proposal_id']}/accept", json={"reason": "review"}).status_code == 200
    stored = client.get("/api/harnesses/baseline-x/1.0.0").json()
    stored["skills_tools"]["execution_budget"]["max_runtime_ms"] = 9999
    # Recreate the persisted baseline through the repository, simulating a later version change.
    from backend.harness.store import get_harness_repository
    repository = get_harness_repository()
    repository.replace([stored])
    applied = client.post(f"/api/harness-proposals/{proposal['proposal_id']}/apply")
    assert applied.status_code == 409
    assert "changed since proposal creation" in applied.json()["detail"]


def test_viewer_cannot_accept_or_enable_harness_iteration(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/harness-proposals", json={"baseline_harness_id": "crisisagent-default", "baseline_version": "1.0.0", "diagnosis": {"failure_tags": ["tool_timeout"]}})
    proposal_id = created.json()["proposal_id"]
    viewer = {"X-User-Id": "viewer-1", "X-User-Role": "viewer"}
    assert client.post(f"/api/harness-proposals/{proposal_id}/accept", headers=viewer, json={"reason": "not allowed"}).status_code == 403
