from copy import deepcopy
from datetime import datetime, timezone

from backend.core.state import REJECTED, RUNNING, WAITING_HUMAN, AgentState


def request_review(
    state: AgentState,
    reason: str,
    reviewer: str = "",
    comment: str = "",
) -> dict:
    state.set_status(WAITING_HUMAN)
    _update_approval(
        state,
        required=True,
        decision="pending",
        reviewer=reviewer,
        comment=comment,
        reason=reason,
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
    _update_approval(
        state,
        required=False,
        decision="approved",
        reviewer=reviewer,
        reviewer_id=reviewer_id,
        reviewer_username=reviewer_username,
        reviewer_role=reviewer_role,
        comment=comment,
        reason=state.approval.get("reason", ""),
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
        reviewer_id=reviewer_id,
        reviewer_username=reviewer_username,
        reviewer_role=reviewer_role,
        comment=comment,
        reason=state.approval.get("reason", ""),
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
) -> None:
    state.approval.update(
        {
            "required": required,
            "decision": decision,
            "reviewer": reviewer,
            "reviewer_id": reviewer_id,
            "reviewer_username": reviewer_username or reviewer,
            "reviewer_role": reviewer_role,
            "comment": comment,
            "reason": reason,
            "timestamp": _now_iso(),
        }
    )


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
