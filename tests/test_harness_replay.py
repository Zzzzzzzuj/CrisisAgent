import copy

from backend.evaluation.harness_replay import HarnessReplayRunner, compare_harness_replay, load_replay_cases
from backend.harness.spec import build_default_harness_spec


def test_replay_is_deterministic_and_keeps_same_cases():
    spec = build_default_harness_spec()
    cases = load_replay_cases()
    left = HarnessReplayRunner(spec).run_case(cases[0])
    right = HarnessReplayRunner(copy.deepcopy(spec)).run_case(cases[0])
    assert left["case_id"] == right["case_id"]
    assert left["failure_tags"] == right["failure_tags"]
    assert left["human_review_required"] == right["human_review_required"]
    assert left["checkpoint_written"] is False
    assert left["session_store_written"] is False


def test_replay_candidate_policy_changes_evidence_review():
    baseline = build_default_harness_spec()
    candidate = copy.deepcopy(baseline)
    candidate["retrieval_policy"]["min_score"] = 0.95
    cases = [next(case for case in load_replay_cases() if case["case_id"] == "replay-evidence-low")]
    comparison = compare_harness_replay(baseline, candidate, cases)
    assert comparison["mode"] == "main_workflow_replay"
    assert comparison["same_case_ids"] == ["replay-evidence-low"]
    assert comparison["baseline"]["spec_hash"] != comparison["candidate"]["spec_hash"]
    assert comparison["candidate"]["cases"][0]["human_review_required"] is True


def test_replay_evidence_threshold_and_review_trigger_change_behavior():
    baseline = build_default_harness_spec()
    candidate = copy.deepcopy(baseline)
    candidate["retrieval_policy"]["min_score"] = 0.01
    candidate["review_policy"]["triggers"]["evidence_low_confidence"] = False
    case = {"case_id": "threshold-change", "fixture": {"event": "普通信息", "category": "general", "risk_level": "low", "evidence": [{"score": 0.05, "rerank_score": 0.9, "source_category": "general"}]}, "expected": {"failure_tags": [], "human_review_required": False}}
    result = compare_harness_replay(baseline, candidate, [case])
    assert result["baseline"]["cases"][0]["human_review_required"] is True
    assert result["candidate"]["cases"][0]["human_review_required"] is False


def test_replay_tool_timeout_and_retry_are_harness_driven():
    baseline = build_default_harness_spec()
    baseline["skills_tools"]["timeout_ms"] = 1
    baseline["skills_tools"]["max_retries"] = 0
    candidate = copy.deepcopy(baseline)
    candidate["skills_tools"]["timeout_ms"] = 100
    candidate["skills_tools"]["max_retries"] = 1
    case = next(case for case in load_replay_cases() if case["case_id"] == "replay-tool-timeout")
    result = compare_harness_replay(baseline, candidate, [case])
    assert result["baseline"]["cases"][0]["tool_result"]["success"] is False
    assert result["candidate"]["cases"][0]["tool_result"]["success"] is True
    assert result["candidate"]["cases"][0]["tool_result"]["retry_count"] == 1


def test_replay_runs_fixed_six_agent_order():
    result = HarnessReplayRunner(build_default_harness_spec()).run_case(load_replay_cases()[-1])
    assert result["execution"]["executed_agents"] == ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]
    assert result["resume_harness_preserved"] is True


def test_comparison_api_can_select_main_workflow_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_COMPARISON_STORE_PATH", str(tmp_path / "comparisons.json"))
    from fastapi.testclient import TestClient
    from backend.main import app

    response = TestClient(app).post(
        "/api/harness-comparisons",
        json={
            "baseline_harness_id": "crisisagent-default",
            "baseline_version": "1.0.0",
            "candidate_harness_id": "crisisagent-default",
            "candidate_version": "1.0.0",
            "mode": "main_workflow_replay",
            "replay_case_ids": ["replay-evidence-low"],
        },
    )
    assert response.status_code == 201
    assert response.json()["mode"] == "main_workflow_replay"
    assert response.json()["same_case_ids"] == ["replay-evidence-low"]
