from backend.evaluation.harness_comparison import evaluate_comparison_gate
from backend.harness.service import (
    approve_harness_version,
    build_default_harness_spec,
    copy_harness_version,
    enable_approved_harness_version,
    mark_harness_evaluated,
    reject_harness_version,
    update_candidate_harness,
)


def _candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    return copy_harness_version("crisisagent-default", "1.0.0", "2.0.0")


def test_candidate_only_changes_allowed_runtime_policies(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path, monkeypatch)
    updated = update_candidate_harness(
        candidate["metadata"]["harness_id"], "2.0.0",
        {"retrieval_policy.min_score": 0.2, "skills_tools.execution_budget.max_steps": 4},
        "Tighten evidence and execution budgets",
    )
    assert updated["metadata"]["changed_fields"] == [
        "retrieval_policy.min_score", "skills_tools.execution_budget.max_steps"
    ]
    assert updated["retrieval_policy"]["min_score"] == 0.2


def test_candidate_rejects_workflow_and_prompt_changes(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path, monkeypatch)
    import pytest
    with pytest.raises(ValueError, match="only change"):
        update_candidate_harness(candidate["metadata"]["harness_id"], "2.0.0", {"workflow.agent_order": []}, "bad")


def test_only_approved_candidate_can_be_enabled(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path, monkeypatch)
    import pytest
    with pytest.raises(ValueError, match="APPROVED"):
        enable_approved_harness_version(candidate["metadata"]["harness_id"], "2.0.0")


def test_gate_pass_hold_and_reject_cases():
    base = build_default_harness_spec()
    base_result = {"metrics": {"task_completion_rate": 0.8, "evidence_quality_rate": 0.9, "tool_failure_rate": 0.1, "failure_tag_counts": {"tool_timeout": 1}, "human_review_trigger_rate": 0.4}}
    same = {"metrics": dict(base_result["metrics"])}
    assert evaluate_comparison_gate({"baseline": base_result, "candidate": same})["passed"] is True
    worse = {"metrics": {**base_result["metrics"], "task_completion_rate": 0.7}}
    assert evaluate_comparison_gate({"baseline": base_result, "candidate": worse})["passed"] is False
    severe = {"metrics": {**base_result["metrics"], "failure_tag_counts": {"tool_timeout": 2}}}
    assert evaluate_comparison_gate({"baseline": base_result, "candidate": severe})["passed"] is False


def test_evaluated_approved_active_and_rollback_records_are_scoped(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path, monkeypatch)
    harness_id = candidate["metadata"]["harness_id"]
    gate = {"passed": True, "failure_reasons": [], "checks": {"all": True}}
    evaluated = mark_harness_evaluated(harness_id, "2.0.0", "comparison-1", gate)
    assert evaluated["metadata"]["status"] == "EVALUATED"
    approved = approve_harness_version(harness_id, "2.0.0", "comparison-1", "admin", gate)
    assert approved["metadata"]["status"] == "APPROVED"
    active = enable_approved_harness_version(harness_id, "2.0.0")
    assert active["metadata"]["status"] == "active"


def test_reject_requires_reason_and_preserves_rejection_record(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path, monkeypatch)
    result = reject_harness_version(candidate["metadata"]["harness_id"], "2.0.0", "admin", "Evidence quality regressed")
    assert result["metadata"]["status"] == "REJECTED"
    assert result["metadata"]["rejection"]["reason"] == "Evidence quality regressed"


def test_candidate_api_requires_evaluation_and_approval_before_enable(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    monkeypatch.setenv("HARNESS_COMPARISON_STORE_PATH", str(tmp_path / "comparisons.json"))
    monkeypatch.setattr("backend.api.harness_routes.write_audit", lambda *args, **kwargs: None)
    client = TestClient(app)
    copied = client.post("/api/harnesses/crisisagent-default/1.0.0/copy", json={"new_version": "3.0.0"})
    assert copied.status_code == 201
    harness_id = copied.json()["metadata"]["harness_id"]
    patched = client.patch(f"/api/harnesses/{harness_id}/3.0.0/candidate", json={"changes": {"retrieval_policy.min_score": 0.2}, "change_summary": "raise minimum evidence score"})
    assert patched.status_code == 200
    assert client.post(f"/api/harnesses/{harness_id}/3.0.0/enable").status_code == 409
    evaluated = client.post(f"/api/harnesses/{harness_id}/3.0.0/evaluate", json={"baseline_harness_id": "crisisagent-default", "baseline_version": "1.0.0"})
    assert evaluated.status_code == 200
    comparison_id = evaluated.json()["comparison"]["comparison_id"]
    approved = client.post(f"/api/harnesses/{harness_id}/3.0.0/approve", json={"comparison_id": comparison_id, "reason": "Offline gates passed"})
    assert approved.status_code == 200
    assert client.post(f"/api/harnesses/{harness_id}/3.0.0/enable").status_code == 200


def test_candidate_budget_is_read_by_tool_runner():
    from backend.skills.registry import SkillRegistry
    from backend.skills.skill_schema import AgentSkill
    from backend.skills.tool_runner import ToolRunner, TOOL_LOOP_DETECTED

    skill = AgentSkill(
        name="demo", description="demo", input_schema={"type": "object"},
        output_schema={"type": "object"}, category="test", owner_agent="test",
        safety_level="low", enabled=True, version="1", handler=lambda payload: {"ok": True},
    )
    spec = build_default_harness_spec()
    spec["skills_tools"]["execution_budget"]["max_same_call"] = 1
    runner = ToolRunner(SkillRegistry([skill]), harness_spec=spec)
    assert runner.run("demo", {}).success is True
    blocked = runner.run("demo", {})
    assert blocked.error_code == TOOL_LOOP_DETECTED
    assert blocked.human_review_required is True
