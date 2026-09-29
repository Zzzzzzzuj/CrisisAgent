"""Execute bounded, P32-governed Legal evidence actions for Dynamic Runtime."""

from copy import deepcopy
from time import perf_counter
from typing import Callable

from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_action_policy import (
    REQUEST_HUMAN_FACT_VERIFICATION,
    TARGETED_LEGAL_SEARCH,
    recommend_legal_actions,
)
from backend.agents.legal_claim_relation import build_legal_claim_relations, evidence_ref


MAX_TARGETED_ROUNDS = 1
LEGAL_LOOP_MAX_ROUNDS = 3
LEGAL_LOOP_MAX_TOOL_CALLS = 2
LEGAL_LOOP_CONTEXT_BUDGET = 6000
LEGAL_LOOP_MAX_SAME_ACTION_PER_GAP = 2
LEGAL_ACTION_WHITELIST = frozenset({
    "RETRIEVE_LEGAL_EVIDENCE", "REQUEST_HUMAN_FACT", "USE_EXISTING_EVIDENCE",
    "STOP_RESOLVED", "STOP_UNRESOLVED",
})


def execute_recommended_targeted_search(
    claim_extraction: dict,
    coverage: dict,
    relation: dict,
    recommendation: dict,
    rag_info: dict,
    *,
    retrieve_call: Callable,
    relation_call: Callable = build_legal_claim_relations,
    llm_call: Callable | None = None,
    mode: str = "mock",
) -> dict:
    """The only action allowed here is one targeted retrieve; no business output changes."""
    claims = claim_extraction.get("legal_claims", [])
    candidates = sorted(
        row["claim_index"] for row in recommendation.get("claim_action_recommendations", [])
        if isinstance(row, dict) and row.get("recommended_action") == TARGETED_LEGAL_SEARCH
        and type(row.get("claim_index")) is int and 0 <= row["claim_index"] < len(claims)
    )
    if not candidates:
        return {"targeted_search_executions": []}

    index = candidates[0]
    claim = claims[index]
    before = next((row.get("legal_rule_status") for row in coverage.get("claim_coverage", [])
                   if isinstance(row, dict) and row.get("claim_index") == index), "uncertain")
    query = _targeted_query(claim.get("claim"), rag_info.get("query", ""))
    if query is None:
        return {"targeted_search_executions": [], "targeted_search_stop_reason": "query_not_distinct"}

    action = {
        "claim_index": index,
        "executed_action": TARGETED_LEGAL_SEARCH,
        "round": MAX_TARGETED_ROUNDS,
        "query": query,
        "before_legal_rule_status": before,
        "after_legal_rule_status": "uncertain",
        "next_recommended_action": "STOP_UNRESOLVED",
        "status": "failed",
        "stop_reason": "action_failed",
        "targeted_evidence_refs": [],
        "observation_type": "tool_error",
    }
    try:
        result = retrieve_call(query, top_k=3)
        if not isinstance(result, dict):
            action["observation_type"] = "invalid_output"
            raise ValueError("Targeted retrieval returned an invalid result.")
        chunks = result.get("chunks", [])
        sources = result.get("sources", [])
        if (not isinstance(chunks, list) or any(not isinstance(chunk, dict) for chunk in chunks)
                or not isinstance(sources, list)):
            action["observation_type"] = "invalid_output"
            raise ValueError("Targeted retrieval returned invalid chunks.")
        action["targeted_evidence_refs"] = list(dict.fromkeys(
            ref for chunk in chunks if isinstance(chunk, dict)
            if (ref := evidence_ref(chunk)) is not None
        ))
        fallback_used = _fallback_used(result)
        if not chunks:
            action["status"] = "no_hit"
            action["observation_type"] = "retrieval_no_hit"
            targeted_relation = {"legal_claim_relations": [], "relation_status": "skipped"}
        else:
            action["observation_type"] = "retrieval_hit"
            targeted_relation = relation_call([claim], chunks, mode=mode, llm_call=llm_call)
            if not isinstance(targeted_relation, dict):
                action["observation_type"] = "invalid_output"
                raise ValueError("Targeted relation returned an invalid result.")
            action["status"] = "fallback" if fallback_used else (
                "relation_failed" if targeted_relation.get("relation_status") != "ok" else "completed"
            )
            if action["status"] == "relation_failed":
                action["observation_type"] = "tool_error"
        targeted_coverage = build_claim_coverage([claim], targeted_relation)
        after = targeted_coverage["claim_coverage"][0]["legal_rule_status"]
        if fallback_used:
            after = "uncertain"
        action["after_legal_rule_status"] = after
        action["targeted_relation"] = _global_relation(targeted_relation, index)
        action["next_recommended_action"] = _next_recommendation(
            claim_extraction, coverage, relation, rag_info, action["targeted_relation"],
            index, after, fallback_used, bool(chunks),
        )
        action["stop_reason"] = {
            "no_hit": "retrieval_no_hit",
            "fallback": "retrieval_fallback_used",
            "relation_failed": "relation_failure",
        }.get(action["status"], "round_limit_reached" if
              action["next_recommended_action"] == TARGETED_LEGAL_SEARCH else "action_completed")
    except Exception as exc:
        action["status"] = "failed"
        action["failure_type"] = exc.__class__.__name__
        if isinstance(exc, TimeoutError):
            action["observation_type"] = "tool_timeout"
    return {"targeted_search_executions": [action]}


def run_legal_action_loop(
    claim_extraction: dict,
    coverage: dict,
    relation: dict,
    rag_info: dict,
    *,
    retrieve_call: Callable,
    relation_call: Callable = build_legal_claim_relations,
    llm_call: Callable | None = None,
    mode: str = "mock",
    event: str = "",
    risk_level: str = "unknown",
    policy: dict | None = None,
) -> dict:
    """Execute a bounded Legal action loop over the P32 recommendation and P33 action."""
    policy = policy if isinstance(policy, dict) else {}
    max_rounds = _bounded_int(policy.get("max_rounds"), LEGAL_LOOP_MAX_ROUNDS, 1, LEGAL_LOOP_MAX_ROUNDS)
    max_calls = _bounded_int(policy.get("max_tool_calls"), LEGAL_LOOP_MAX_TOOL_CALLS, 0, LEGAL_LOOP_MAX_TOOL_CALLS)
    context_budget = _bounded_int(policy.get("context_budget"), LEGAL_LOOP_CONTEXT_BUDGET, 256, 12000)
    same_action_limit = _bounded_int(
        policy.get("max_same_action_per_gap"), LEGAL_LOOP_MAX_SAME_ACTION_PER_GAP,
        1, LEGAL_LOOP_MAX_SAME_ACTION_PER_GAP,
    )
    extraction = deepcopy(claim_extraction) if isinstance(claim_extraction, dict) else {}
    current_coverage = deepcopy(coverage) if isinstance(coverage, dict) else {"claim_coverage": []}
    current_relation = deepcopy(relation) if isinstance(relation, dict) else {"legal_claim_relations": [], "relation_status": "skipped"}
    claims = extraction.get("legal_claims", [])
    actions = []
    attempted: dict[int, int] = {}
    tool_calls_used = 0
    previous_observation = None
    current_gap = None
    stop_reason = "no_eligible_action"
    rounds_used = 0
    retry_gap_index = None

    for round_index in range(max_rounds):
        rounds_used = round_index + 1
        recommendations = recommend_legal_actions(extraction, current_coverage, current_relation, rag_info)
        rows = recommendations.get("claim_action_recommendations", [])
        fact_request = next((row for row in rows if row.get("recommended_action") == REQUEST_HUMAN_FACT_VERIFICATION), None)
        if fact_request:
            current_gap = {"claim_index": fact_request["claim_index"],
                           "claim": claims[fact_request["claim_index"]].get("claim")}
            context_chars = len(_minimal_decision_context(
                event, claims[fact_request["claim_index"]], current_relation,
                fact_request["claim_index"], previous_observation, risk_level,
                max_calls - tool_calls_used,
            ))
            action = _loop_action(round_index, "REQUEST_HUMAN_FACT", "case_fact_unresolved",
                                  "human_fact_required", context_chars, max_calls - tool_calls_used)
            action["claim_index"] = fact_request["claim_index"]
            action["tool_calls_used"] = tool_calls_used
            action["previous_observation"] = deepcopy(previous_observation)
            actions.append(action)
            stop_reason = "human_fact_required"
            break

        candidate = None
        if retry_gap_index is not None:
            candidate = {"claim_index": retry_gap_index,
                         "recommended_action": TARGETED_LEGAL_SEARCH,
                         "action_reason": "bounded_retry_after_transient_tool_failure"}
            retry_gap_index = None
        if candidate is None:
            candidate = next((row for row in rows
                              if row.get("recommended_action") == TARGETED_LEGAL_SEARCH
                              and type(row.get("claim_index")) is int
                              and attempted.get(row["claim_index"], 0) < same_action_limit), None)
        if candidate is None:
            legal_rows = [row for row in current_coverage.get("claim_coverage", [])
                          if isinstance(row, dict) and row.get("legal_rule_status") != "not_required"]
            if legal_rows and all(row.get("legal_rule_status") == "candidate_found" for row in legal_rows):
                use_existing = _loop_action(round_index, "USE_EXISTING_EVIDENCE", "candidate_rule_available",
                                            "evidence_sufficient_for_rule_requirement", 0,
                                            max_calls - tool_calls_used)
                use_existing["tool_calls_used"] = tool_calls_used
                actions.append(use_existing)
                stop = _loop_action(round_index, "STOP_RESOLVED", "all_rule_gaps_resolved",
                                    "task_evidence_requirements_resolved", 0,
                                    max_calls - tool_calls_used)
                stop["tool_calls_used"] = tool_calls_used
                actions.append(stop)
                stop_reason = "task_evidence_requirements_resolved"
            else:
                stop_reason = "no_eligible_action_after_observation" if actions else "no_eligible_action"
                actions.append(_loop_action(round_index, "STOP_UNRESOLVED", stop_reason, stop_reason,
                                            0, max_calls - tool_calls_used))
                actions[-1]["tool_calls_used"] = tool_calls_used
            break

        if tool_calls_used >= max_calls:
            stop_reason = "tool_budget_exhausted"
            actions.append(_loop_action(round_index, "STOP_UNRESOLVED", stop_reason, stop_reason,
                                        0, 0))
            actions[-1]["tool_calls_used"] = tool_calls_used
            break

        claim_index = candidate["claim_index"]
        claim = claims[claim_index]
        context = _minimal_decision_context(event, claim, current_relation, claim_index,
                                            previous_observation, risk_level,
                                            max_calls - tool_calls_used)
        context_chars = len(context) + len(str(claim.get("claim", ""))) + len("\n相关法律规定")
        if context_chars > context_budget:
            stop_reason = "context_budget_exhausted"
            actions.append(_loop_action(round_index, "STOP_UNRESOLVED", stop_reason, stop_reason,
                                        context_chars, max_calls - tool_calls_used))
            actions[-1]["tool_calls_used"] = tool_calls_used
            break

        one_action = {"claim_action_recommendations": [candidate]}
        relation_usage = {"chars": 0}

        def bounded_relation_call(claim_rows, chunks, **kwargs):
            evidence_budget = max(0, context_budget - context_chars)
            bounded_chunks = deepcopy(chunks)
            text_budget = evidence_budget // max(1, len(bounded_chunks))
            relation_usage["truncated_chars"] = 0
            for chunk in bounded_chunks:
                text = str(chunk.get("text") or "")
                allowed = min(1500, text_budget)
                relation_usage["chars"] += min(len(text), allowed)
                relation_usage["truncated_chars"] += max(0, len(text) - allowed)
                chunk["text"] = text[:allowed]
            return relation_call(claim_rows, bounded_chunks, **kwargs)

        started = perf_counter()
        result = execute_recommended_targeted_search(
            extraction, current_coverage, current_relation, one_action, rag_info,
            retrieve_call=retrieve_call, relation_call=bounded_relation_call,
            llm_call=llm_call, mode=mode,
        )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        execution = next(iter(result.get("targeted_search_executions", [])), None)
        attempted[claim_index] = attempted.get(claim_index, 0) + 1
        tool_calls_used += 1
        if execution is None:
            execution = {"claim_index": claim_index, "executed_action": TARGETED_LEGAL_SEARCH,
                         "status": "failed", "observation_type": "invalid_output",
                         "stop_reason": result.get("targeted_search_stop_reason", "action_not_executed"),
                         "targeted_evidence_refs": []}
        execution = deepcopy(execution)
        execution.update({
            "round_index": round_index,
            "selected_action": "RETRIEVE_LEGAL_EVIDENCE",
            "executed_action": "RETRIEVE_LEGAL_EVIDENCE",
            "context_chars": context_chars + relation_usage["chars"],
            "context_truncated_chars": relation_usage.get("truncated_chars", 0),
            "tool_calls_used": tool_calls_used,
            "remaining_budget": {"rounds": max(0, max_rounds - round_index - 1),
                                 "tool_calls": max(0, max_calls - tool_calls_used)},
            "latency_ms": latency_ms,
            "previous_observation": deepcopy(previous_observation),
        })
        actions.append(execution)
        previous_observation = {
            "claim_index": claim_index,
            "type": execution.get("observation_type", "tool_error"),
            "status": execution.get("status"),
            "legal_rule_status": execution.get("after_legal_rule_status", "uncertain"),
            "evidence_refs": deepcopy(execution.get("targeted_evidence_refs", [])),
        }
        _apply_targeted_observation(current_coverage, current_relation, execution)
        stop_reason = execution.get("stop_reason", "action_completed")
        if execution.get("status") in {"failed", "fallback", "relation_failed"}:
            transient = execution.get("observation_type") in {"tool_timeout", "tool_error"}
            if (transient and attempted[claim_index] < same_action_limit
                    and tool_calls_used < max_calls and round_index + 1 < max_rounds):
                retry_gap_index = claim_index
                stop_reason = "bounded_retry_pending"
                execution["stop_reason"] = stop_reason
                continue
            stop_reason = "tool_failure"
            execution["stop_reason"] = stop_reason
            break
    else:
        stop_reason = "max_rounds_reached"
        actions.append(_loop_action(max_rounds, "STOP_UNRESOLVED", stop_reason, stop_reason,
                                    0, max(0, max_calls - tool_calls_used)))

    if tool_calls_used >= max_calls and stop_reason not in {
        "task_evidence_requirements_resolved", "human_fact_required", "tool_failure",
    }:
        stop_reason = "tool_budget_exhausted"
        if actions:
            actions[-1]["stop_reason"] = stop_reason
    return {
        "status": "completed" if stop_reason == "task_evidence_requirements_resolved" else "stopped",
        "rounds": rounds_used,
        "actions": actions,
        "claim_coverage": current_coverage,
        "claim_evidence_relation": current_relation,
        "claim_action_recommendation": recommend_legal_actions(extraction, current_coverage,
                                                                 current_relation, rag_info),
        "tool_calls_used": tool_calls_used,
        "remaining_budget": {"rounds": max(0, max_rounds - rounds_used),
                             "tool_calls": max(0, max_calls - tool_calls_used)},
        "context_budget": context_budget,
        "context_chars_total": sum(item.get("context_chars", 0) for item in actions),
        "current_gap": current_gap,
        "phase": "WAITING_HUMAN" if stop_reason == "human_fact_required" else "STOPPED",
        "stop_reason": stop_reason,
    }


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _minimal_decision_context(event: str, claim: dict, relation: dict, index: int,
                              previous_observation: dict | None, risk_level: str,
                              remaining_calls: int) -> str:
    refs = [row.get("evidence_ref") for row in relation.get("legal_claim_relations", [])
            if isinstance(row, dict) and row.get("claim_index") == index]
    # P32 is deterministic; this bounded object records exactly the inputs used for the next action.
    import json
    return json.dumps({"claim": claim.get("claim"), "event": str(event)[:800],
                       "evidence_refs": refs[:3], "previous_observation": previous_observation,
                       "risk_level": risk_level, "remaining_tool_calls": remaining_calls},
                      ensure_ascii=False, separators=(",", ":"))


def _loop_action(round_index: int, selected_action: str, observation_type: str, stop_reason: str,
                 context_chars: int, remaining_calls: int) -> dict:
    if selected_action not in LEGAL_ACTION_WHITELIST:
        selected_action = "STOP_UNRESOLVED"
    return {"round_index": round_index, "selected_action": selected_action,
            "observation_type": observation_type, "context_chars": context_chars,
            "tool_calls_used": 0, "remaining_budget": {"tool_calls": max(0, remaining_calls)},
            "stop_reason": stop_reason, "latency_ms": 0.0}


def _apply_targeted_observation(coverage: dict, relation: dict, execution: dict) -> None:
    index = execution.get("claim_index")
    status = execution.get("after_legal_rule_status")
    if type(index) is not int:
        return
    for row in coverage.get("claim_coverage", []):
        if isinstance(row, dict) and row.get("claim_index") == index and status in {
            "candidate_found", "no_candidate", "uncertain",
        }:
            row["legal_rule_status"] = status
    targeted = execution.get("targeted_relation")
    if isinstance(targeted, dict):
        relation.setdefault("legal_claim_relations", [])
        relation["legal_claim_relations"] = [
            row for row in relation["legal_claim_relations"]
            if not (isinstance(row, dict) and row.get("claim_index") == index)
        ] + deepcopy(targeted.get("legal_claim_relations", []))
        if targeted.get("legal_claim_relations") or targeted.get("relation_status") == "fallback":
            relation["relation_status"] = targeted.get("relation_status", relation.get("relation_status"))
    execution["after_observation_applied"] = status


def _targeted_query(claim: object, broad_query: str) -> str | None:
    if not isinstance(claim, str) or not claim.strip() or len(claim.strip()) > 240:
        return None
    query = f"{claim.strip()}\n相关法律规定"
    return query if query != str(broad_query).strip() else None


def _fallback_used(result: dict) -> bool:
    if result.get("fallback_used") is True:
        return True
    for row in [*(result.get("chunks") or []), *(result.get("sources") or [])]:
        if isinstance(row, dict) and (row.get("retrieval_fallback") is True
                                      or (isinstance(row.get("metadata"), dict)
                                          and row["metadata"].get("retrieval_fallback") is True)):
            return True
    return False


def _global_relation(relation: dict, index: int) -> dict:
    copied = deepcopy(relation)
    for row in copied.get("legal_claim_relations", []):
        row["claim_index"] = index
    return copied


def _next_recommendation(extraction: dict, coverage: dict, original_relation: dict, rag_info: dict,
                         targeted_relation: dict, index: int, after: str, fallback_used: bool,
                         has_chunks: bool) -> str:
    updated_coverage = deepcopy(coverage)
    for row in updated_coverage.get("claim_coverage", []):
        if row.get("claim_index") == index:
            row["legal_rule_status"] = after
    updated_relation = deepcopy(original_relation)
    updated_relation["legal_claim_relations"] = [
        row for row in original_relation.get("legal_claim_relations", []) if row.get("claim_index") != index
    ] + targeted_relation.get("legal_claim_relations", [])
    updated_relation["relation_status"] = targeted_relation.get("relation_status")
    updated_rag = {**rag_info, "retrieval_status": "executed_with_hits" if has_chunks else "executed_no_hit",
                   "retrieval_executed": True, "fallback_used": fallback_used}
    recommendations = recommend_legal_actions(extraction, updated_coverage, updated_relation, updated_rag)
    return next((row["recommended_action"] for row in recommendations["claim_action_recommendations"]
                 if row["claim_index"] == index), "STOP_UNRESOLVED")
