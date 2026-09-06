from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.core.state import REJECTED, RUNNING, WAITING_HUMAN, AgentState


def request_review(
    state: AgentState,
    reason: str,
    reviewer: str = "",
    comment: str = "",
    reviewer_id: int | None = None,
    reviewer_username: str = "",
    reviewer_role: str = "",
    policy_result: dict | None = None,
    evaluation: dict | None = None,
) -> dict:
    state.set_status(WAITING_HUMAN)
    review_scope = _build_review_scope(state, reason, policy_result, evaluation)
    _update_approval(
        state,
        required=True,
        decision="pending",
        reviewer=reviewer,
        comment=comment,
        reason=reason,
        reviewer_id=reviewer_id,
        reviewer_username=reviewer_username,
        reviewer_role=reviewer_role,
        pending_review_scope=review_scope,
        approved_review_scope=state.approval.get("approved_review_scope"),
    )
    trace = _build_human_trace("waiting_human", reason, state.approval)
    state.add_trace(trace)
    return trace


def approve(
    state: AgentState,
    reviewer: str = "human",
    comment: str = "",
    reviewer_id: int | None = None,
    reviewer_username: str = "",
    reviewer_role: str = "",
) -> dict:
    _ensure_waiting_human(state)
    state.set_status(RUNNING)
    pending_scope = state.approval.get("pending_review_scope")
    if not isinstance(pending_scope, dict):
        pending_scope = _build_review_scope(state, state.approval.get("reason", ""))
    approved_scope = deepcopy(pending_scope)
    approved_scope["approved_trace_count"] = len(state.trace) + 1
    approved_scope["approved_at"] = _now_iso()
    _update_approval(
        state,
        required=False,
        decision="approved",
        reviewer=reviewer,
        comment=comment,
        reason=state.approval.get("reason", ""),
        reviewer_id=reviewer_id,
        reviewer_username=reviewer_username,
        reviewer_role=reviewer_role,
        pending_review_scope=None,
        approved_review_scope=approved_scope,
    )
    trace = _build_human_trace("approved", "Human approved runtime continuation.", state.approval)
    state.add_trace(trace)
    return trace


def reject(
    state: AgentState,
    reviewer: str = "human",
    comment: str = "",
    reviewer_id: int | None = None,
    reviewer_username: str = "",
    reviewer_role: str = "",
) -> dict:
    _ensure_waiting_human(state)
    state.set_status(REJECTED)
    _update_approval(
        state,
        required=False,
        decision="rejected",
        reviewer=reviewer,
        comment=comment,
        reason=state.approval.get("reason", ""),
        reviewer_id=reviewer_id,
        reviewer_username=reviewer_username,
        reviewer_role=reviewer_role,
        pending_review_scope=None,
        approved_review_scope=state.approval.get("approved_review_scope"),
    )
    trace = _build_human_trace("rejected", "Human rejected runtime result.", state.approval)
    state.add_trace(trace)
    return trace


def _update_approval(
    state: AgentState,
    required: bool,
    decision: str,
    reviewer: str,
    comment: str,
    reason: str,
    reviewer_id: int | None = None,
    reviewer_username: str = "",
    reviewer_role: str = "",
    pending_review_scope: dict | None = None,
    approved_review_scope: dict | None = None,
) -> None:
    username = reviewer_username or reviewer
    state.approval.update(
        {
            "required": required,
            "decision": decision,
            "reviewer": username,
            "reviewer_id": reviewer_id,
            "reviewer_username": username,
            "reviewer_role": reviewer_role,
            "comment": comment,
            "reason": reason,
            "timestamp": _now_iso(),
        }
    )
    if pending_review_scope is None:
        state.approval.pop("pending_review_scope", None)
    else:
        state.approval["pending_review_scope"] = deepcopy(pending_review_scope)

    if approved_review_scope is None:
        state.approval.pop("approved_review_scope", None)
    else:
        state.approval["approved_review_scope"] = deepcopy(approved_review_scope)


def _build_human_trace(status: str, reason: str, approval: dict) -> dict:
    timestamp = _now_iso()
    return {
        "agent": "human_gate",
        "reason": reason,
        "start_time": timestamp,
        "end_time": timestamp,
        "status": status,
        "output": {"approval": deepcopy(approval)},
        "error": None,
    }


def _ensure_waiting_human(state: AgentState) -> None:
    if state.status != WAITING_HUMAN:
        raise ValueError("Human decision is only allowed when state is WAITING_HUMAN.")


def _build_review_scope(
    state: AgentState,
    reason: str,
    policy_result: dict | None = None,
    evaluation: dict | None = None,
) -> dict[str, Any]:
    triggers = []
    if isinstance(policy_result, dict):
        triggers = list(policy_result.get("triggers", []))
    if not triggers:
        triggers = _extract_triggers_from_reason(reason)

    scope: dict[str, Any] = {
        "trace_count": len(state.trace),
        "triggers": triggers,
        "reason": reason,
    }
    if isinstance(evaluation, dict):
        scope["evaluation_passed"] = evaluation.get("passed")
        scope["evaluation_issues"] = list(evaluation.get("issues", []))
    return scope


def _extract_triggers_from_reason(reason: str) -> list[str]:
    if not reason:
        return []

    marker = "Human review required:"
    if marker in reason:
        raw_triggers = reason.split(marker, 1)[1]
        return [item.strip() for item in raw_triggers.split(",") if item.strip()]

    inferred = []
    normalized = reason.lower()
    if "high risk" in normalized:
        inferred.append("high_risk")
    if "low-quality rag" in normalized or "rag_evidence_low_confidence" in normalized:
        inferred.append("rag_evidence_low_confidence")
    return inferred


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
