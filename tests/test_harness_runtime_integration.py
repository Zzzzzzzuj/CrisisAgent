from __future__ import annotations

import pytest

from backend.core.dynamic_runtime import execute_dynamic_state, initialize_dynamic_state, run_dynamic_agent
from backend.harness.service import (
    approve_harness_version,
    copy_harness_version,
    enable_approved_harness_version,
    mark_harness_evaluated,
    update_candidate_harness,
)
from backend.harness.spec import build_default_harness_spec, spec_hash


def _approved_candidate(tmp_path, monkeypatch, version="2.0.0"):
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    candidate = copy_harness_version("crisisagent-default", "1.0.0", version)
    candidate_id = candidate["metadata"]["harness_id"]
    candidate = update_candidate_harness(
        candidate_id,
        version,
        {"skills_tools.execution_budget.max_retries": 2},
        "increase bounded retry budget",
    )
    gate = {"passed": True, "checks": {}, "failure_reasons": []}
    mark_harness_evaluated(candidate_id, version, f"comparison-{version}", gate)
    approved = approve_harness_version(candidate_id, version, f"comparison-{version}", "admin", gate)
    return approved, candidate_id


def test_unapproved_candidate_cannot_enter_dynamic_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    candidate = copy_harness_version("crisisagent-default", "1.0.0", "2.0.0")
    with pytest.raises(ValueError, match="not active"):
        run_dynamic_agent("产品质量投诉正在传播。", harness_id=candidate["metadata"]["harness_id"], harness_version="2.0.0")


def test_active_harness_is_fixed_in_dynamic_state_and_trace(tmp_path, monkeypatch):
    approved, candidate_id = _approved_candidate(tmp_path, monkeypatch)
    enabled = enable_approved_harness_version(candidate_id, "2.0.0")
    state = initialize_dynamic_state("食品安全投诉正在传播。", harness_id=candidate_id, harness_version="2.0.0")
    assert state.metadata["harness_spec"]["metadata"]["version"] == "2.0.0"
    assert spec_hash(state.metadata["harness_spec"]) == spec_hash(enabled)

    result = execute_dynamic_state(state)
    assert result["executed_agents"] == ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]
    assert all(item["harness"]["harness_version"] == "2.0.0" for item in state.trace if item.get("agent") != "agent_loop")
    assert state.metadata["harness_runtime_context"]["harness"]["harness_version"] == "2.0.0"


def test_checkpoint_snapshot_is_used_even_if_active_selection_changes(tmp_path, monkeypatch):
    first, first_id = _approved_candidate(tmp_path, monkeypatch, "2.0.0")
    enable_approved_harness_version(first_id, "2.0.0")
    state = initialize_dynamic_state("数据隐私投诉。", harness_id=first_id, harness_version="2.0.0")
    snapshot_hash = spec_hash(state.metadata["harness_spec"])

    second, second_id = _approved_candidate(tmp_path, monkeypatch, "3.0.0")
    enable_approved_harness_version(second_id, "3.0.0")
    assert spec_hash(state.metadata["harness_spec"]) == snapshot_hash
    assert state.metadata["harness_spec"]["metadata"]["version"] == "2.0.0"


def test_harness_retrieval_policy_and_review_trigger_are_read_in_main_components():
    from backend.agents import legal_agent
    from backend.core.policy import evaluate_human_policy
    from backend.core.state import AgentState

    spec = build_default_harness_spec()
    spec["retrieval_policy"].update({"min_score": 0.8, "min_rerank_score": 0.7, "max_context_pollution_rate": 0.2})
    spec["review_policy"]["triggers"]["evidence_low_confidence"] = False
    assert legal_agent._evidence_gate_policy({"harness_spec": spec}) == {
        "min_score": 0.8,
        "min_rerank_score": 0.7,
        "max_context_pollution_rate": 0.2,
    }
    state = AgentState("session-1", "plan-1", "事件", metadata={"harness_spec": spec})
    state.add_trace({"agent": "legal", "rag": {"evidence_quality": {"should_trigger_human_review": True}}})
    assert "rag_evidence_low_confidence" not in evaluate_human_policy(state, {"passed": True})["triggers"]
    spec["review_policy"]["triggers"]["evidence_low_confidence"] = True
    state.metadata["harness_spec"] = spec
    assert "rag_evidence_low_confidence" in evaluate_human_policy(state, {"passed": True})["triggers"]
