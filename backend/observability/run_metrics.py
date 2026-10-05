"""Safe, per-session observability derived only from structured Trace metadata."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

_LEGAL_OPERATION_TYPES = {
    "legal.claim_extraction", "legal.action_proposal", "legal.relation_check", "legal.review",
}


def build_run_metrics(session_id: str, trace: list, state_status: str, approval: dict | None = None) -> dict:
    agents: dict[str, dict] = defaultdict(_empty_agent_metrics)
    metrics = {
        "run_id": session_id,
        "session_id": session_id,
        "started_at": None,
        "finished_at": None,
        "total_latency_ms": 0.0,
        "agent_metrics": [],
        "operation_metrics": [],
        "llm_call_count": 0,
        "llm_latency_ms": 0.0,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "estimated_total_tokens": None,
        "token_source": "unavailable",
        "retrieval_call_count": 0,
        "retrieval_latency_ms": None,
        "retrieval_latency_status": "unavailable",
        "retrieval_status_counts": {},
        "tool_call_count": 0,
        "tool_latency_ms": 0.0,
        "tool_status_counts": {},
        "fallback_count": 0,
        "fallback_categories": [],
        "context_chars_before": 0,
        "context_chars_after": 0,
        "context_budget_chars": None,
        "context_truncated": False,
        "human_intervention_count": 0,
        "human_fact_request_count": 0,
        "human_fact_response_count": 0,
        "final_review_count": 0,
        "approval_count": 0,
        "rejection_count": 0,
        "estimated_cost": None,
        "cost_estimation_status": "unavailable",
        "state_status": state_status,
    }
    timestamps = []
    token_sources = []
    provider_input_tokens = provider_output_tokens = provider_total_tokens = 0
    estimated_total_tokens = 0
    retrieval_latency_total = 0.0
    retrieval_latency_count = 0
    agent_retrieval_latency_counts: dict[str, int] = defaultdict(int)
    operation_calls: dict[str, list[dict]] = defaultdict(list)

    for row in trace or []:
        if not isinstance(row, dict):
            continue
        agent_name = str(row.get("agent") or "unknown")
        agent = agents[agent_name]
        duration = _number(row.get("duration_ms"))
        if duration is not None:
            agent["execution_count"] += 1
            agent["latency_ms"] += duration
            metrics["total_latency_ms"] += duration
        if row.get("start_time"):
            timestamps.append(str(row["start_time"]))
        if row.get("end_time"):
            timestamps.append(str(row["end_time"]))

        calls = row.get("llm_calls")
        if not isinstance(calls, list):
            calls = [row["llm"]] if isinstance(row.get("llm"), dict) else []
        for call in calls:
            if not isinstance(call, dict):
                continue
            operation_type = call.get("operation_type")
            if operation_type not in _LEGAL_OPERATION_TYPES:
                operation_type = "unknown"
            operation_calls[operation_type].append(call)
            latency = _number(call.get("latency_ms")) or 0.0
            agent["llm_call_count"] += 1
            agent["llm_latency_ms"] += latency
            metrics["llm_call_count"] += 1
            metrics["llm_latency_ms"] += latency
            source = call.get("token_source")
            if source in {"provider", "estimated"}:
                token_sources.append(source)
            if source == "estimated":
                estimated_total_tokens += int(_number(call.get("estimated_tokens")) or 0)
            if call.get("fallback_used"):
                _record_fallback(metrics, call.get("failure_type") or "llm_fallback")
            if source == "provider":
                provider_input_tokens += _number(call.get("input_tokens")) or 0
                provider_output_tokens += _number(call.get("output_tokens")) or 0
                provider_total_tokens += _number(call.get("total_tokens")) or 0

        rag = row.get("rag") if isinstance(row.get("rag"), dict) else {}
        retrieval_calls = row.get("retrieval_calls")
        if isinstance(retrieval_calls, list):
            for retrieval_call in retrieval_calls:
                if not isinstance(retrieval_call, dict):
                    continue
                metrics["retrieval_call_count"] += 1
                _increment(metrics["retrieval_status_counts"], _retrieval_status(retrieval_call))
                latency = _number(retrieval_call.get("latency_ms"))
                agent["retrieval_call_count"] += 1
                if latency is not None:
                    retrieval_latency_total += latency
                    retrieval_latency_count += 1
                    agent["retrieval_latency_ms"] = (agent["retrieval_latency_ms"] or 0.0) + latency
                    agent_retrieval_latency_counts[agent_name] += 1
                if retrieval_call.get("status") == "FALLBACK":
                    _record_fallback(metrics, "retrieval_fallback")
        else:
            if rag.get("retrieval_executed"):
                metrics["retrieval_call_count"] += 1
                _increment(metrics["retrieval_status_counts"], _retrieval_status(rag))
                agent["retrieval_call_count"] += 1
                latency = _number(rag.get("retrieval_latency_ms"))
                if latency is not None:
                    retrieval_latency_total += latency
                    retrieval_latency_count += 1
                    agent["retrieval_latency_ms"] = (agent["retrieval_latency_ms"] or 0.0) + latency
                    agent_retrieval_latency_counts[agent_name] += 1
            if rag.get("fallback_used"):
                _record_fallback(metrics, "retrieval_fallback")

        targeted = rag.get("targeted_legal_search")
        actions = targeted.get("actions", []) if isinstance(targeted, dict) else rag.get("actions", [])
        if not actions and isinstance(rag.get("targeted_search_executions"), list):
            actions = rag["targeted_search_executions"]
        if not actions and isinstance(row.get("legal_action_loop"), dict):
            actions = row["legal_action_loop"].get("actions", [])
        if not isinstance(retrieval_calls, list):
            for action in actions if isinstance(actions, list) else []:
                if not isinstance(action, dict) or (
                    action.get("executed_action") or action.get("selected_action") or action.get("action")
                ) != "RETRIEVE_LEGAL_EVIDENCE":
                    continue
                metrics["retrieval_call_count"] += 1
                _increment(metrics["retrieval_status_counts"], _retrieval_status(action))
                agent["retrieval_call_count"] += 1
                if action.get("fallback_used"):
                    _record_fallback(metrics, "targeted_retrieval_fallback")

        skills = row.get("skills")
        results = skills.get("results", []) if isinstance(skills, dict) else []
        for result in results if isinstance(results, list) else []:
            if not isinstance(result, dict):
                continue
            skill_trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
            metrics["tool_call_count"] += 1
            _increment(metrics["tool_status_counts"], _tool_status(result, skill_trace))
            latency = _number(skill_trace.get("duration_ms")) or 0.0
            metrics["tool_latency_ms"] += latency
            agent["tool_call_count"] += 1
            agent["tool_latency_ms"] += latency
            if result.get("fallback_used") or skill_trace.get("fallback_used"):
                _record_fallback(metrics, "tool_fallback")

        context = row.get("context_pack")
        if isinstance(context, dict):
            before = _number(context.get("chars_before"))
            after = _number(context.get("chars_after"))
            if before is not None:
                metrics["context_chars_before"] += before
            if after is not None:
                metrics["context_chars_after"] += after
            budget = _number(context.get("budget_chars"))
            if budget is not None:
                metrics["context_budget_chars"] = budget
            metrics["context_truncated"] = metrics["context_truncated"] or bool(context.get("truncated"))

        action = str(row.get("action") or "")
        if action == "REQUEST_HUMAN_FACT_VERIFICATION":
            metrics["human_fact_request_count"] += 1
            metrics["human_intervention_count"] += 1
        elif action == "HUMAN_FACT_RESPONSE":
            metrics["human_fact_response_count"] += 1
            metrics["human_intervention_count"] += 1
        if agent_name == "human_gate":
            if row.get("status") == "waiting_human":
                metrics["final_review_count"] += 1
                metrics["human_intervention_count"] += 1
            elif row.get("status") == "approved":
                metrics["approval_count"] += 1
                metrics["human_intervention_count"] += 1
            elif row.get("status") == "rejected":
                metrics["rejection_count"] += 1
                metrics["human_intervention_count"] += 1

    if timestamps:
        metrics["started_at"] = min(timestamps)
        metrics["finished_at"] = max(timestamps)
    if retrieval_latency_count:
        metrics["retrieval_latency_ms"] = retrieval_latency_total
        metrics["retrieval_latency_status"] = (
            "available" if retrieval_latency_count == metrics["retrieval_call_count"] else "partial"
        )
    if token_sources and all(source == "provider" for source in token_sources):
        metrics.update({"input_tokens": provider_input_tokens, "output_tokens": provider_output_tokens,
                        "total_tokens": provider_total_tokens, "token_source": "provider"})
    elif token_sources and all(source == "estimated" for source in token_sources):
        metrics["token_source"] = "estimated"
        metrics["estimated_total_tokens"] = estimated_total_tokens
    metrics["fallback_categories"] = sorted(set(metrics["fallback_categories"]))
    metrics["agent_metrics"] = []
    for name, values in sorted(agents.items()):
        observed_retrieval_latencies = agent_retrieval_latency_counts[name]
        values["retrieval_latency_status"] = (
            "available" if observed_retrieval_latencies and observed_retrieval_latencies == values["retrieval_call_count"]
            else "partial" if observed_retrieval_latencies else "unavailable"
        )
        metrics["agent_metrics"].append({"agent_name": name, **deepcopy(values)})
    metrics["operation_metrics"] = [
        _operation_metrics(name, calls) for name, calls in sorted(operation_calls.items())
    ]
    return metrics


def _operation_metrics(operation_type: str, calls: list[dict]) -> dict:
    attempts = [attempt for call in calls for attempt in call.get("attempts", [])
                if isinstance(attempt, dict)]
    usage_calls = [call for call in calls if call.get("token_source") == "provider"
                   and _number(call.get("total_tokens")) is not None]
    token_source = "provider" if usage_calls and len(usage_calls) == len(calls) else (
        "mixed" if usage_calls else "unavailable"
    )
    return {
        "operation_type": operation_type,
        "operation_span_count": len({call.get("operation_span_id") for call in calls
                                      if isinstance(call.get("operation_span_id"), str)}),
        "logical_call_count": len(calls),
        "http_attempt_count": sum(int(_number(call.get("http_attempt_count")) or 0) for call in calls),
        "technical_retry_count": sum(int(_number(call.get("retry_count")) or 0) for call in calls),
        "success_count": sum(call.get("success") is True for call in calls),
        "failure_count": sum(call.get("success") is False for call in calls),
        "latency_ms": sum(_number(call.get("latency_ms")) or 0.0 for call in calls),
        "attempt_status_counts": _attempt_status_counts(attempts),
        "provider_input_tokens": (sum(int(_number(call.get("input_tokens")) or 0) for call in usage_calls)
                                  if usage_calls else None),
        "provider_output_tokens": (sum(int(_number(call.get("output_tokens")) or 0) for call in usage_calls)
                                   if usage_calls else None),
        "provider_total_tokens": (sum(int(_number(call.get("total_tokens")) or 0) for call in usage_calls)
                                  if usage_calls else None),
        "token_source": token_source,
    }


def _attempt_status_counts(attempts: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    allowed = {"SUCCESS", "TIMEOUT", "HTTP_ERROR", "CONNECTION_ERROR", "UNKNOWN"}
    for attempt in attempts:
        status = attempt.get("attempt_status")
        if status in allowed:
            counts[status] = counts.get(status, 0) + 1
    return counts


def _empty_agent_metrics() -> dict:
    return {"execution_count": 0, "latency_ms": 0.0, "llm_call_count": 0, "llm_latency_ms": 0.0,
            "retrieval_call_count": 0, "retrieval_latency_ms": None, "retrieval_latency_status": "unavailable",
            "tool_call_count": 0, "tool_latency_ms": 0.0}


def _record_fallback(metrics: dict, category: str) -> None:
    metrics["fallback_count"] += 1
    metrics["fallback_categories"].append(str(category))


def _increment(counter: dict, status: str) -> None:
    counter[status] = counter.get(status, 0) + 1


def _retrieval_status(value: dict) -> str:
    status = str(value.get("retrieval_status") or value.get("status") or value.get("observation_type") or "").lower()
    if value.get("fallback_used") or status == "fallback":
        return "FALLBACK"
    if status == "retrieval_error":
        return "ERROR"
    if "no_hit" in status:
        return "NO_HIT"
    if status in {"failed", "error", "retrieval_error", "tool_error"}:
        return "ERROR"
    return "SUCCESS"


def _tool_status(result: dict, trace: dict) -> str:
    if result.get("fallback_used") or trace.get("fallback_used"):
        return "FALLBACK"
    return "SUCCESS" if result.get("success") else "ERROR"


def _number(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, float(value))
    return None
