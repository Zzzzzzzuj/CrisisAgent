from backend.core import checkpoint
from backend.core.state import COMPLETED, FAILED, REJECTED, WAITING_HUMAN, AgentState


RUNTIME_METRIC_FIELDS = (
    "total_sessions",
    "completed_sessions",
    "failed_sessions",
    "waiting_human_sessions",
    "agent_failure_count",
    "llm_call_count",
    "llm_fallback_count",
    "guardrail_trigger_count",
    "rag_hit_count",
    "rag_fallback_count",
    "approval_count",
    "rejection_count",
    "average_runtime_latency_ms",
)


def collect_runtime_metrics() -> dict:
    states = _load_all_states()
    audit_logs = checkpoint.list_audit_logs()
    metrics = _empty_metrics()
    metrics["total_sessions"] = len(states)

    total_latency = 0
    latency_sessions = 0
    approval_sessions = set()
    rejection_sessions = set()

    for state in states:
        status = str(state.status or "").upper()
        if status == COMPLETED:
            metrics["completed_sessions"] += 1
        if status in {FAILED, REJECTED}:
            metrics["failed_sessions"] += 1
        if status == WAITING_HUMAN:
            metrics["waiting_human_sessions"] += 1

        metrics["agent_failure_count"] += len(state.failed_agents or [])
        trace_metrics = _collect_trace_metrics(state.trace)
        for key, value in trace_metrics.items():
            metrics[key] += value

        guardrail_count = _count_guardrail_hits(state)
        metrics["guardrail_trigger_count"] += guardrail_count

        decision = (state.approval or {}).get("decision")
        if decision == "approved":
            approval_sessions.add(state.session_id)
        if decision == "rejected":
            rejection_sessions.add(state.session_id)

        runtime_latency = _runtime_latency_ms(state.trace)
        if runtime_latency:
            total_latency += runtime_latency
            latency_sessions += 1

    for log in audit_logs:
        action = str(log.get("action", ""))
        session_id = str(log.get("session_id", ""))
        if action == "approved":
            approval_sessions.add(session_id)
        if action == "rejected":
            rejection_sessions.add(session_id)

    metrics["approval_count"] = len(approval_sessions)
    metrics["rejection_count"] = len(rejection_sessions)
    metrics["average_runtime_latency_ms"] = int(total_latency / latency_sessions) if latency_sessions else 0
    return metrics


def _empty_metrics() -> dict:
    return {field: 0 for field in RUNTIME_METRIC_FIELDS}


def _load_all_states() -> list[AgentState]:
    states = []
    for summary in checkpoint.list_checkpoints():
        session_id = summary.get("session_id")
        if not session_id:
            continue
        state = checkpoint.load_checkpoint(str(session_id))
        if state is not None:
            states.append(state)
    return states


def _collect_trace_metrics(trace: list) -> dict:
    metrics = {
        "agent_failure_count": 0,
        "llm_call_count": 0,
        "llm_fallback_count": 0,
        "rag_hit_count": 0,
        "rag_fallback_count": 0,
    }
    for item in trace or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "failed":
            metrics["agent_failure_count"] += 1
        llm = item.get("llm")
        if isinstance(llm, dict):
            metrics["llm_call_count"] += 1
            if llm.get("fallback_used"):
                metrics["llm_fallback_count"] += 1
        rag = item.get("rag")
        if isinstance(rag, dict):
            if rag.get("hit") or int(rag.get("count") or 0) > 0:
                metrics["rag_hit_count"] += 1
            if rag.get("fallback_used"):
                metrics["rag_fallback_count"] += 1
    return metrics


def _count_guardrail_hits(state: AgentState) -> int:
    guardrails = state.metadata.get("guardrails", {})
    if not isinstance(guardrails, dict):
        return 0
    return sum(
        1
        for result in guardrails.values()
        if isinstance(result, dict) and result.get("hit")
    )


def _runtime_latency_ms(trace: list) -> int:
    total = 0
    for item in trace or []:
        if not isinstance(item, dict):
            continue
        duration = item.get("duration_ms")
        if isinstance(duration, (int, float)):
            total += int(duration)
    return total
