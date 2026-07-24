from copy import deepcopy
from datetime import datetime, timezone

from backend.core.state import FAILED, RUNNING, WAITING_HUMAN, AgentState


def request_review(
    state: AgentState,
    reason: str,
    reviewer: str = "",
    comment: str = "",
) -> dict:
    state.status = WAITING_HUMAN
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


def approve(state: AgentState, reviewer: str = "human", comment: str = "") -> dict:
    _ensure_waiting_human(state)
    state.status = RUNNING
    _update_approval(
        state,
        required=False,
        decision="approved",
        reviewer=reviewer,
        comment=comment,
        reason=state.approval.get("reason", ""),
    )
    trace = _build_human_trace("approved", "Human approved runtime continuation.", state.approval)
    state.add_trace(trace)
    return trace


def reject(state: AgentState, reviewer: str = "human", comment: str = "") -> dict:
    _ensure_waiting_human(state)
    state.status = FAILED
    _update_approval(
        state,
        required=False,
        decision="rejected",
        reviewer=reviewer,
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
) -> None:
    state.approval.update(
        {
            "required": required,
            "decision": decision,
            "reviewer": reviewer,
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
