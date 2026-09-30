from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Callable
from uuid import uuid4

from backend.core.adapter import build_agent_input
from backend.core.checkpoint import load_checkpoint
from backend.core.context_pack_runtime import inject_context_pack
from backend.core.harness_runtime import HarnessRuntimeContext, get_runtime_context
from backend.core.human_fact_runtime import revision_is_safe
from backend.core.state import AgentState
from backend.harness.spec import spec_hash
from backend.harness.prompt_policy import validate_writer_v2_candidate_scope
from backend.llm.client import get_last_llm_trace, reset_last_llm_trace


_COMMITMENT_PATTERNS = {
    "concrete_deadline": re.compile(r"(?:今天|明天|本周|\d{1,2}月\d{1,2}日|\d{1,2}日).{0,12}(?:前|内|反馈|完成)|\d+小时内|每\d+小时"),
    "concrete_recovery_time": re.compile(r"(?:预计|将在|于).{0,12}(?:恢复|修复|完成).{0,12}(?:\d{1,2}[:：]\d{2}|\d+小时|\d+天|今天|明天)"),
    "refund_deadline": re.compile(r"退款.{0,16}(?:\d+日|\d+小时|今天|明天|\d{1,2}月\d{1,2}日)"),
    "concrete_monetary_commitment": re.compile(r"(?:赔偿|补偿|退款|返还).{0,12}\d+(?:\.\d+)?\s元|\d+(?:\.\d+)?\s元.{0,12}(?:赔偿|补偿|退款|返还)"),
    "investigation_conclusion": re.compile(r"(?:经调查|经核查|调查结果显示|核查结果显示|已查明|确认系).{0,32}(?:原因|故障|泄露|未发生|不存在|影响|使用|未使用|导致|由于)"),
    "regulatory_reporting_action": re.compile(r"(?:主动)?向[^。；\n]{0,24}(?:监管部门|市场监管|消费者组织|监管机构)[^。；\n]{0,16}(?:报告|通报|报送)"),
    "claimed_completed_action": re.compile(r"已(?:经)?(?:向[^。；\n]{0,24}(?:报告|通报|报送)|完成[^。；\n]{0,16}|启动[^。；\n]{0,16}(?:调查|核查|检查|审计|召回|退款)|通知[^。；\n]{0,16}|召回[^。；\n]{0,16})"),
}
_UNCLASSIFIED_COMMITMENT_CUE = re.compile(r"(?:承诺|确保|保证|一定|务必|按期完成)")


def reconstruct_writer_v2_payload(session_id: str, harness_spec: dict[str, Any]) -> tuple[AgentState, dict[str, Any]]:
    """Rebuild the saved Writer V2 input without mutating the persisted session."""
    saved = load_checkpoint(session_id)
    if saved is None:
        raise ValueError("RV-004 checkpoint was not found.")
    state = AgentState.from_dict(saved.to_dict())
    fact = state.metadata.get("human_fact") or {}
    response = fact.get("response") or {}
    if response.get("response_type") != "FACT_UNAVAILABLE":
        raise ValueError("Trigger replay requires the saved FACT_UNAVAILABLE observation.")
    required_results = ("writer", "redteam", "legal")
    if not state.event or any(not isinstance(state.get_result(agent), dict) for agent in required_results):
        raise ValueError("Saved session lacks required Writer V2 upstream results.")
    snapshots = state.metadata.get("context_pack_snapshots") or {}
    pack = snapshots.get("writer_v2") if isinstance(snapshots, dict) else None
    skills = state.metadata.get("skill_runtime_results") or {}
    if not isinstance(pack, dict) or not isinstance(pack.get("rendered_context"), str):
        raise ValueError("Saved Writer V2 ContextPack is unavailable.")
    if not isinstance(skills, dict) or "writer_v2" not in skills:
        raise ValueError("Saved Writer V2 Skill results are unavailable.")

    state.metadata["harness_spec"] = deepcopy(harness_spec)
    state.metadata["harness_runtime_context"] = HarnessRuntimeContext.from_spec(harness_spec).trace_metadata()
    payload = build_agent_input("writer_v2", state, runtime_context=get_runtime_context(state))
    payload = inject_context_pack(payload, pack)
    payload["skill_results"] = deepcopy(skills["writer_v2"])
    return state, payload


def compare_writer_v2_trigger(
    session_id: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    confirm_real_provider: bool = False,
    writer_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if writer_runner is None and not confirm_real_provider:
        raise ValueError("Writer V2 trigger replay requires explicit provider confirmation.")
    validate_writer_v2_candidate_scope(baseline, candidate)
    baseline_state, baseline_payload = reconstruct_writer_v2_payload(session_id, baseline)
    candidate_state, candidate_payload = reconstruct_writer_v2_payload(session_id, candidate)
    saved_spec = baseline_state.metadata.get("harness_spec") or {}
    if spec_hash(saved_spec) != spec_hash(baseline):
        raise ValueError("Selected baseline does not match the Harness snapshot saved in the source Session.")
    failure_ref = _source_failure_reference(baseline_state)
    input_hash = _payload_hash(baseline_payload)
    if input_hash != _payload_hash(candidate_payload):
        raise ValueError("Baseline and Candidate replay inputs are not identical.")

    baseline_result = _run_writer(baseline_payload, baseline_state, writer_runner)
    candidate_result = _run_writer(candidate_payload, candidate_state, writer_runner)
    trigger_status = _trigger_status(baseline_result, candidate_result)
    frozen = _frozen_regression()
    safety = _safety_regression(baseline_state, candidate_state, baseline_result, candidate_result)
    return {
        "comparison_id": f"writer-v2-{uuid4()}",
        "mode": "writer_v2_trigger_replay",
        "offline_only": writer_runner is not None,
        "created_at": _now(),
        "source_session_id": session_id,
        "source_failure": failure_ref,
        "input_hash": input_hash,
        "baseline": _variant(baseline, baseline_result),
        "candidate": _variant(candidate, candidate_result),
        "trigger_replay": {"status": trigger_status, "reason": _trigger_reason(baseline_result, candidate_result)},
        "frozen_regression": frozen,
        "safety_regression": safety,
        "engineering_regression": {"status": "requires_ci", "passed": None},
        "overall_status": _overall_status(trigger_status, frozen["status"], safety["status"], "UNKNOWN"),
        "automatic_enable": False,
        "automatic_publish": False,
    }


def _run_writer(payload, state, writer_runner):
    if writer_runner is not None:
        try:
            output = writer_runner(deepcopy(payload))
            return _grade(output, state, provider_status="deterministic_test_runner")
        except Exception as exc:
            return _unknown(exc.__class__.__name__)

    from backend.agents import writer_agent
    from backend.config import get_config

    try:
        if get_config().agent_mode != "llm":
            return _unknown("AGENT_MODE_NOT_LLM")
        reset_last_llm_trace()
        output = writer_agent.generate_second_draft(payload)
        trace = get_last_llm_trace()
        if not trace.get("success") or trace.get("fallback_used"):
            return _unknown(str(trace.get("failure_type") or "PROVIDER_FALLBACK"))
        return _grade(output, state, provider_status="provider_success", provider_model=trace.get("model"))
    except Exception as exc:
        return _unknown(exc.__class__.__name__)


def _grade(output, state, *, provider_status, provider_model=None):
    statement = output.get("statement") if isinstance(output, dict) else None
    fact = state.metadata.get("human_fact") or {}
    request = fact.get("request") or {}
    target_claim = request.get("claim")
    if not isinstance(statement, str) or not statement.strip() or not isinstance(target_claim, str) or not target_claim.strip():
        return _unknown("GRADER_INPUT_INCOMPLETE")
    findings = [name for name, pattern in _COMMITMENT_PATTERNS.items() if pattern.search(statement)]
    revision_safe = revision_is_safe(target_claim, statement)
    if not revision_safe:
        findings.append("existing_revision_safety_target_claim")
    findings = list(dict.fromkeys(findings))
    if _UNCLASSIFIED_COMMITMENT_CUE.search(statement) and not findings:
        return _unknown("UNCLASSIFIED_COMMITMENT_LANGUAGE")
    return {
        "status": "evaluated",
        "provider_status": provider_status,
        "provider_model": provider_model,
        "writer_v2_output": statement,
        "unsupported_commitment_count": len(findings),
        "unsupported_commitment_findings": findings,
        "unsupported_claim_remains": not revision_safe,
        "revision_safety": {"status": "pass" if revision_safe else "fail", "passed": revision_safe},
        "safety_status": "pass" if revision_safe and not findings else "fail",
        "output_hash": hashlib.sha256(statement.encode("utf-8")).hexdigest(),
    }


def _unknown(reason):
    return {
        "status": "unknown",
        "provider_status": "unknown",
        "writer_v2_output": None,
        "unsupported_commitment_count": None,
        "unsupported_commitment_findings": [],
        "unsupported_claim_remains": None,
        "revision_safety": {"status": "unknown", "passed": None},
        "safety_status": "unknown",
        "unknown_reason": reason,
    }


def _trigger_status(baseline, candidate):
    if baseline.get("status") != "evaluated" or candidate.get("status") != "evaluated":
        return "UNKNOWN"
    if candidate["unsupported_commitment_count"] < baseline["unsupported_commitment_count"] and candidate["safety_status"] == "pass":
        return "PASS"
    return "FAIL"


def _trigger_reason(baseline, candidate):
    if baseline.get("status") != "evaluated" or candidate.get("status") != "evaluated":
        return "Both actual Writer V2 outputs and deterministic grading are required; provider fallback or missing input is UNKNOWN."
    if candidate["unsupported_commitment_count"] >= baseline["unsupported_commitment_count"]:
        return "CANDIDATE_NOT_SUPPORTED"
    if candidate["safety_status"] != "pass":
        return "Candidate output still violates the existing Revision Safety or contains detected unsupported commitments."
    return "Candidate reduced the targeted findings and passed the existing Revision Safety check."


def _frozen_regression():
    from backend.api.eval_service import evaluate_golden_cases, load_golden_cases

    items, summary = evaluate_golden_cases(load_golden_cases())
    failed = [item["case_id"] for item in items if not item["passed"]]
    return {"status": "PASS" if not failed else "FAIL", "passed": not failed,
            "case_count": summary.get("golden_case_count", 0), "failed_case_ids": failed,
            "scope": "deterministic invariant regression; does not assess Prompt Candidate quality"}


def _safety_regression(baseline_state, candidate_state, baseline, candidate):
    before = baseline_state.metadata.get("human_fact") or {}
    after = candidate_state.metadata.get("human_fact") or {}
    boundary = ((before.get("response") or {}).get("response_type") == "FACT_UNAVAILABLE"
                and (after.get("response") or {}).get("response_type") == "FACT_UNAVAILABLE")
    final_review = (
        any(item.get("agent") == "human_gate" for item in baseline_state.trace)
        and any(item.get("agent") == "human_gate" for item in candidate_state.trace)
    )
    known = baseline.get("status") == "evaluated" and candidate.get("status") == "evaluated"
    checks = {
        "existing_revision_safety_executed": known,
        "human_fact_unavailable_boundary_preserved": boundary,
        "final_human_review_boundary_preserved": final_review,
    }
    return {"status": "PASS" if all(checks.values()) else "UNKNOWN", "passed": all(checks.values()), "checks": checks}


def _source_failure_reference(state):
    matches = [
        item for item in state.trace
        if isinstance(item, dict)
        and item.get("agent") == "human_fact"
        and item.get("reason") == "unsupported_claim_remains_after_revision"
    ]
    if not matches:
        raise ValueError("Source Session does not contain the expected RV-004 safety failure marker.")
    row = matches[-1]
    return {
        "failure_tag": "unsupported_claim_remains_after_revision",
        "stage": "revision_safety_after_writer_v2",
        "round": row.get("round"),
        "trace_ref": f"{state.session_id}:human_fact:{row.get('round', 'unknown')}:unsupported_claim_remains_after_revision",
    }


def _overall_status(trigger, frozen, safety, engineering):
    statuses = (trigger, frozen, safety, engineering)
    if "FAIL" in statuses:
        return "FAIL"
    if all(status == "PASS" for status in statuses):
        return "PASS"
    return "UNKNOWN"


def _variant(spec, result):
    metadata = spec.get("metadata", {})
    return {"harness_id": metadata.get("harness_id"), "version": metadata.get("version"),
            "spec_hash": spec_hash(spec), "result": result}


def _payload_hash(payload):
    comparable = deepcopy(payload)
    comparable.pop("harness_spec", None)
    comparable.pop("harness_runtime_context", None)
    canonical = json.dumps(comparable, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
