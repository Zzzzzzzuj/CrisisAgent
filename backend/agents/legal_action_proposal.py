"""Request a bounded Legal action proposal without granting execution authority."""

import json
from collections.abc import Callable

from backend.llm.client import classify_failure_from_exception
from backend.llm.parser import parse_json_response
from backend.agents.legal_action_policy import classify_legal_query_dependency


ACTION_PROPOSAL_REASON_CODES = frozenset({
    "CASE_FACT_GAP",
    "LEGAL_RULE_GAP",
    "EXISTING_EVIDENCE_AVAILABLE",
    "REQUIREMENTS_RESOLVED",
    "REQUIREMENTS_UNRESOLVED",
    "OBSERVATION_CHANGED_PRIORITY",
    "RETRY_TRANSIENT_FAILURE",
})


def build_legal_decision_context(
    claim_extraction: dict,
    claim_coverage: dict,
    claim_relation: dict,
    rag_info: dict,
    eligible_actions: list[dict],
    *,
    previous_observation: dict | None,
    attempted_actions: dict[int, int],
    requested_fact_gaps: list[int],
    round_count: int,
    remaining_rounds: int,
    remaining_tool_calls: int,
    risk_level: str,
) -> dict:
    """Build a content-minimized context for action selection only."""
    claims = claim_extraction.get("legal_claims", []) if isinstance(claim_extraction, dict) else []
    coverage = claim_coverage.get("claim_coverage", []) if isinstance(claim_coverage, dict) else []
    relations = claim_relation.get("legal_claim_relations", []) if isinstance(claim_relation, dict) else []
    observation = previous_observation if isinstance(previous_observation, dict) else {}
    return {
        "goal_code": "RESOLVE_LEGAL_EVIDENCE_REQUIREMENTS",
        "claims": [
            {
                "claim_index": index,
                "requires_legal_rule": claim.get("requires_legal_rule") is True,
                "requires_case_fact": claim.get("requires_case_fact") is True,
                "dependency_type": classify_legal_query_dependency(claim)["dependency_type"],
                "claim_origin": (claim.get("claim_origin")
                                 if claim.get("claim_origin") in {"writer_draft", "event_fact_gap"}
                                 else "unknown"),
            }
            for index, claim in enumerate(claims) if isinstance(claim, dict)
        ],
        "coverage": [
            {
                "claim_index": row.get("claim_index"),
                "case_fact_status": row.get("case_fact_status"),
                "legal_rule_status": row.get("legal_rule_status"),
            }
            for row in coverage if isinstance(row, dict)
        ],
        "evidence": {
            "available_ref_count": len({row.get("evidence_ref") for row in relations
                                        if isinstance(row, dict) and row.get("evidence_ref")}),
            "relation_status": claim_relation.get("relation_status") if isinstance(claim_relation, dict) else None,
            "retrieval_completed": bool(isinstance(rag_info, dict) and rag_info.get("retrieval_executed")),
            "fallback_used": bool(isinstance(rag_info, dict) and rag_info.get("fallback_used")),
        },
        "previous_observation": {
            "type": observation.get("type", observation.get("observation_type")),
            "status": observation.get("status", observation.get("response_type")),
            "changed_claim_state": bool(
                observation.get("claim_state_changed", observation.get("whether_new_information", False))
            ),
        },
        "eligible_actions": [
            {"action": row.get("action"), "target_claim_index": row.get("target_claim_index")}
            for row in eligible_actions if isinstance(row, dict)
        ],
        "attempted_actions": [
            {"action": "RETRIEVE_LEGAL_EVIDENCE", "target_claim_index": index, "count": count}
            for index, count in sorted(attempted_actions.items())
        ] + [
            {"action": "REQUEST_HUMAN_FACT", "target_claim_index": index, "count": 1}
            for index in sorted(set(requested_fact_gaps))
        ],
        "round_count": round_count,
        "remaining_rounds": remaining_rounds,
        "remaining_tool_calls": remaining_tool_calls,
        "risk_level": risk_level if risk_level in {"low", "medium", "high", "unknown"} else "unknown",
        "risk_constraints": [
            "HUMAN_ASSERTED_IS_NOT_INDEPENDENTLY_VERIFIED",
            "LEGAL_RULE_CANNOT_VERIFY_CASE_FACT",
            "NO_REPEAT_HUMAN_FACT",
            "FAIL_CLOSED",
        ],
    }


def request_legal_action_proposal(
    decision_context: dict,
    *,
    llm_call: Callable[[str], str] | None,
) -> dict:
    """Return a strict proposal; callers must still validate it before execution."""
    if llm_call is None:
        return _failure("provider_error")
    try:
        raw = llm_call(_proposal_prompt(decision_context))
        parsed = parse_json_response(raw)
        if set(parsed) != {"action", "reason_code", "target_claim_index"}:
            raise ValueError("Unexpected Legal action proposal fields.")
        action = parsed["action"]
        reason_code = parsed["reason_code"]
        claim_index = parsed["target_claim_index"]
        if not isinstance(action, str) or not action:
            raise ValueError("Legal action proposal action must be a string.")
        if reason_code not in ACTION_PROPOSAL_REASON_CODES:
            raise ValueError("Unknown Legal action proposal reason code.")
        if type(claim_index) is not int or claim_index < 0:
            raise ValueError("Legal action proposal claim index is invalid.")
        return {
            "status": "ok",
            "proposal": {
                "action": action,
                "reason_code": reason_code,
                "target_claim_index": claim_index,
            },
        }
    except Exception as exc:
        return _failure(classify_failure_from_exception(exc))


def _proposal_prompt(decision_context: dict) -> str:
    return (
        "你是 Legal Agent 内部的受控动作提议器。只从 eligible_actions 中选择一个动作与目标 claim_index；"
        "不得生成查询、问题、工具参数、事实判断、详细推理或额外字段。"
        "reason_code 只能是 CASE_FACT_GAP、LEGAL_RULE_GAP、EXISTING_EVIDENCE_AVAILABLE、"
        "REQUIREMENTS_RESOLVED、REQUIREMENTS_UNRESOLVED、OBSERVATION_CHANGED_PRIORITY、"
        "RETRY_TRANSIENT_FAILURE。只返回 JSON："
        '{"action":"RETRIEVE_LEGAL_EVIDENCE","reason_code":"LEGAL_RULE_GAP",'
        '"target_claim_index":0}\n'
        + json.dumps(decision_context, ensure_ascii=False, separators=(",", ":"))
    )


def _failure(failure_type: str) -> dict:
    return {"status": "fallback", "failure_type": failure_type, "proposal": None}
