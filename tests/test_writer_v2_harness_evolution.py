from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from backend.agents import writer_agent
from backend.core.harness_runtime import HarnessRuntimeContext
from backend.core.state import AgentState
from backend.evaluation.harness_comparison import evaluate_comparison_gate
from backend.evaluation.writer_v2_trigger_replay import _grade, compare_writer_v2_trigger, reconstruct_writer_v2_payload
from backend.harness.prompt_policy import POLICY_PATH
from backend.harness.prompt_policy import DEFAULT_WRITER_V2_POLICY, get_writer_v2_policy
from backend.harness.service import (
    build_default_harness_spec,
    copy_harness_version,
    update_candidate_harness,
)
from backend.harness.spec import spec_hash


def _candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SPEC_STORE_PATH", str(tmp_path / "harnesses.json"))
    candidate = copy_harness_version("crisisagent-default", "1.0.0", "rv004-v2")
    return update_candidate_harness(
        candidate["metadata"]["harness_id"],
        "rv004-v2",
        {POLICY_PATH: True},
        "Require verified case facts for concrete commitments",
    )


def _candidate_spec(base):
    candidate = deepcopy(base)
    candidate.setdefault("prompts", {}).setdefault("policies", {}).setdefault("writer_v2", {})[
        "unsupported_commitment_policy"
    ] = deepcopy(DEFAULT_WRITER_V2_POLICY)
    candidate["prompts"]["policies"]["writer_v2"]["unsupported_commitment_policy"][
        "require_case_fact_for_concrete_commitment"
    ] = True
    return candidate


def _saved_state():
    spec = build_default_harness_spec()
    state = AgentState(
        session_id="rv004-session",
        plan_id="fixed-workflow",
        event="健身品牌系统故障，原因和会员数据影响仍在核查。",
        results={
            "sentiment": {"risk_level": "high"},
            "writer": {"statement": "首稿摘要"},
            "redteam": {"issues": ["需核实承诺"], "suggestions": []},
            "legal": {"revision_advice": [], "integrated_revision_tasks": []},
        },
        metadata={
            "harness_spec": spec,
            "human_fact": {
                "request": {"claim": "会员数据是否受到影响"},
                "response": {"response_type": "FACT_UNAVAILABLE"},
            },
            "context_pack_snapshots": {
                "writer_v2": {"rendered_context": "redacted context fixture", "context_pack_hash": "pack-hash"}
            },
            "skill_runtime_results": {"writer_v2": {"results": [], "decisions": []}},
        },
        trace=[
            {
                "agent": "human_fact",
                "reason": "unsupported_claim_remains_after_revision",
                "action": "STOP",
            },
            {"agent": "human_gate", "action": "FINAL_REVIEW"},
        ],
    )
    return state


def test_baseline_prompt_is_unchanged_and_candidate_overlay_is_versioned():
    base = build_default_harness_spec()
    candidate = _candidate_spec(base)
    payload = {"event": "fixture", "harness_spec": base}
    base_prompt = writer_agent._build_writer_v2_prompt(payload)
    candidate_prompt = writer_agent._build_writer_v2_prompt({**payload, "harness_spec": candidate})
    assert "事实边界策略（高于上方通用写作要求）" not in base_prompt
    assert "事实边界策略（高于上方通用写作要求）" in candidate_prompt
    assert "human_asserted 信息不等于 independently_verified" in candidate_prompt
    assert spec_hash(base) != spec_hash(candidate)


def test_only_allowlisted_prompt_policy_can_be_patched(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path, monkeypatch)
    policy = candidate["prompts"]["policies"]["writer_v2"]["unsupported_commitment_policy"]
    assert policy["require_case_fact_for_concrete_commitment"] is True
    assert candidate["metadata"]["changed_fields"] == [POLICY_PATH]
    with pytest.raises(ValueError, match="only change"):
        update_candidate_harness(candidate["metadata"]["harness_id"], "rv004-v2", {
            "prompts.policies.writer_v2.arbitrary_prompt_text": "rewrite everything"
        }, "invalid arbitrary prompt")
    with pytest.raises(ValueError, match="only change"):
        update_candidate_harness(candidate["metadata"]["harness_id"], "rv004-v2", {
            "safety_gate.enabled": False
        }, "disable safety")


def test_reconstruction_uses_snapshot_and_does_not_mutate_saved_harness(monkeypatch):
    state = _saved_state()
    original_hash = spec_hash(state.metadata["harness_spec"])
    monkeypatch.setattr("backend.evaluation.writer_v2_trigger_replay.load_checkpoint", lambda _sid: state)
    baseline, payload = reconstruct_writer_v2_payload("rv004-session", state.metadata["harness_spec"])
    assert payload["event"] == state.event
    assert payload["human_fact_revision"]["fact_currently_unavailable"] is True
    assert payload["context_pack_text"] == "redacted context fixture"
    assert payload["skill_results"] == state.metadata["skill_runtime_results"]["writer_v2"]
    assert baseline.metadata["harness_spec"]["metadata"]["version"] == "1.0.0"
    assert spec_hash(state.metadata["harness_spec"]) == original_hash


def test_trigger_replay_runs_same_input_against_isolated_baseline_and_candidate(monkeypatch):
    base = build_default_harness_spec()
    candidate = _candidate_spec(base)
    candidate["metadata"]["version"] = "rv004-candidate"
    state = _saved_state()
    monkeypatch.setattr(
        "backend.evaluation.writer_v2_trigger_replay.reconstruct_writer_v2_payload",
        lambda _session, spec: (
            AgentState.from_dict(state.to_dict()),
            {"event": state.event, "harness_spec": deepcopy(spec), "test_input": "same"},
        ),
    )
    seen = []

    def writer_runner(payload):
        policy_enabled = get_writer_v2_policy(payload["harness_spec"])["require_case_fact_for_concrete_commitment"]
        seen.append(policy_enabled)
        if policy_enabled:
            return {"statement": "公司正在核查，目前相关事实仍在进一步确认。"}
        return {"statement": "会员数据没有受到影响，今天18:00前向属地市场监管部门报告，每2小时滚动更新一次。"}

    result = compare_writer_v2_trigger("rv004-session", base, candidate, writer_runner=writer_runner)
    assert seen == [False, True]
    assert result["input_hash"]
    assert result["baseline"]["result"]["unsupported_commitment_count"] >= 3
    assert result["candidate"]["result"]["unsupported_commitment_count"] == 0
    assert result["trigger_replay"]["status"] == "PASS"
    assert result["frozen_regression"]["status"] in {"PASS", "FAIL"}
    assert result["safety_regression"]["status"] == "PASS"
    assert result["engineering_regression"]["status"] == "requires_ci"
    gate = evaluate_comparison_gate(result)
    assert gate["passed"] is False
    assert gate["checks"]["engineering_regression_passed"] is False


def test_trigger_replay_uses_real_writer_v2_entrypoint_with_fake_provider(monkeypatch):
    base = build_default_harness_spec()
    candidate = _candidate_spec(base)
    candidate["metadata"]["version"] = "rv004-candidate"
    state = _saved_state()
    monkeypatch.setattr(
        "backend.evaluation.writer_v2_trigger_replay.reconstruct_writer_v2_payload",
        lambda _session, spec: (
            AgentState.from_dict(state.to_dict()),
            {"event": state.event, "first_draft": state.results["writer"],
             "redteam_review": state.results["redteam"], "legal_review": state.results["legal"],
             "human_fact_revision": {"fact_currently_unavailable": True}, "harness_spec": deepcopy(spec)},
        ),
    )
    monkeypatch.setattr("backend.agents.writer_agent.get_config", lambda: SimpleNamespace(agent_mode="llm"))
    monkeypatch.setattr("backend.config.get_config", lambda: SimpleNamespace(agent_mode="llm"))

    def fake_llm(prompt):
        if "事实边界策略（高于上方通用写作要求）" in prompt:
                statement = "公司正在核查，目前相关事实仍在进一步确认。"
        else:
            statement = "会员数据没有受到影响，今天18:00前向属地市场监管部门报告，每2小时滚动更新一次。"
        return json.dumps({"statement": statement, "strategy": "fixture", "tone": "谨慎", "revisions": []}, ensure_ascii=False)

    monkeypatch.setattr(writer_agent, "call_llm", fake_llm)
    monkeypatch.setattr("backend.evaluation.writer_v2_trigger_replay.reset_last_llm_trace", lambda: None)
    monkeypatch.setattr("backend.evaluation.writer_v2_trigger_replay.get_last_llm_trace", lambda: {
        "success": True, "fallback_used": False, "model": "deterministic-fake"
    })
    result = compare_writer_v2_trigger("rv004-session", base, candidate, confirm_real_provider=True)
    assert result["baseline"]["result"]["provider_status"] == "provider_success"
    assert result["candidate"]["result"]["provider_status"] == "provider_success"
    assert result["trigger_replay"]["status"] == "PASS"


def test_provider_fallback_or_mock_mode_is_unknown_and_fails_closed():
    from backend.evaluation.writer_v2_trigger_replay import _unknown

    result = {
        "mode": "writer_v2_trigger_replay",
        "trigger_replay": {"status": "UNKNOWN"},
        "frozen_regression": {"status": "PASS"},
        "safety_regression": {"status": "UNKNOWN"},
        "engineering_regression": {"status": "requires_ci"},
    }
    assert _unknown("PROVIDER_FALLBACK")["status"] == "unknown"
    assert evaluate_comparison_gate(result)["passed"] is False


def test_grader_detects_investigation_conclusions_and_fails_closed_on_unknown_commitments(monkeypatch):
    state = _saved_state()
    monkeypatch.setattr("backend.evaluation.writer_v2_trigger_replay.revision_is_safe", lambda *_: True)
    conclusion = _grade(
        {"statement": "经调查，故障原因为会员数据迁移异常。"},
        state,
        provider_status="deterministic_test_runner",
    )
    unknown = _grade(
        {"statement": "我们承诺持续向公众说明进展。"},
        state,
        provider_status="deterministic_test_runner",
    )
    assert "investigation_conclusion" in conclusion["unsupported_commitment_findings"]
    assert unknown["status"] == "unknown"
    assert unknown["unknown_reason"] == "UNCLASSIFIED_COMMITMENT_LANGUAGE"


def test_prompt_policy_trace_metadata_is_compact_and_version_bound():
    spec = build_default_harness_spec()
    context = HarnessRuntimeContext.from_spec(spec).trace_metadata()
    assert context["harness"]["harness_version"] == "1.0.0"
    assert context["harness_policy"]["writer_v2_prompt_policy"] == {
        "policy_id": "unsupported_commitment_v1",
        "require_case_fact_for_concrete_commitment": False,
    }
