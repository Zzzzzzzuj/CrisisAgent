"""Execute bounded, P32-governed Legal evidence actions for Dynamic Runtime."""

from copy import deepcopy
from time import perf_counter
from typing import Callable

from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_action_policy import (
    RETRIEVE_LEGAL_EVIDENCE,
    REQUEST_HUMAN_FACT,
    REQUEST_HUMAN_FACT_VERIFICATION,
    STOP_RESOLVED,
    STOP_UNRESOLVED,
    TARGETED_LEGAL_SEARCH,
    USE_EXISTING_EVIDENCE,
    classify_legal_query_dependency,
    compute_eligible_actions,
    recommend_legal_actions,
    validate_action_proposal,
)
from backend.agents.legal_action_proposal import (
    build_legal_decision_context,
    request_legal_action_proposal,
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


def _proposal_failure_status(failure_type: object) -> str:
    if failure_type == "timeout":
        return "PROVIDER_TIMEOUT"
    if failure_type in {"provider_error", "rate_limit", "empty_response"}:
        return "PROVIDER_ERROR"
    if failure_type in {"invalid_json", "schema_validation_failed"}:
        return "INVALID_JSON"
    return "PROVIDER_ERROR"


def _fallback_reason(reason: object) -> str | None:
    mapping = {
        "timeout": "PROVIDER_FAILURE",
        "provider_error": "PROVIDER_FAILURE",
        "rate_limit": "PROVIDER_FAILURE",
        "empty_response": "PROVIDER_FAILURE",
        "invalid_json": "PARSE_FAILURE",
        "schema_validation_failed": "PARSE_FAILURE",
        "action_not_allowed": "UNKNOWN_ACTION",
        "invalid_claim_index": "INVALID_TARGET",
        "observation_inconsistent": "STATE_MISMATCH",
    }
    return mapping.get(reason)


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
    query = _targeted_query(classify_legal_query_dependency(claim)["legal_rule_topic"],
                            rag_info.get("query", ""))
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
    cursor: dict | None = None,
    human_observation: dict | None = None,
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
    dependencies = _information_dependencies(claims)
    resume = isinstance(cursor, dict)
    if resume:
        rag_info = deepcopy(cursor.get("rag_info", rag_info))
        mode = cursor.get("mode", "mock")
    actions = deepcopy(cursor.get("actions", [])) if resume else []
    attempted = {int(key): int(value) for key, value in cursor.get("attempted_actions", {}).items()} if resume else {}
    tool_calls_used = int(cursor.get("tool_calls_used", 0)) if resume else 0
    previous_observation = deepcopy(cursor.get("previous_observation")) if resume else None
    requested_gaps = list(cursor.get("requested_fact_gaps", [])) if resume else []
    consumed_requests = list(cursor.get("consumed_request_ids", [])) if resume else []
    rounds_used = int(cursor.get("round_count", 0)) if resume else 0
    human_response_type = cursor.get("human_response_type") if resume else None
    if resume:
        if not isinstance(human_observation, dict) or human_observation.get("request_id") in consumed_requests:
            return _stopped_resume(cursor, "human_fact_already_consumed")
        if human_observation.get("claim_index") not in requested_gaps:
            return _stopped_resume(cursor, "observation_inconsistent")
        if (cursor.get("information_dependencies", dependencies) != dependencies
                or cursor.get("claim_gap_state", _gap_state(current_coverage)) != _gap_state(current_coverage)):
            return _stopped_resume(cursor, "dependency_or_gap_state_mismatch")
        human_observation = deepcopy(human_observation)
        if not _apply_human_input_observation(current_coverage, human_observation):
            return _stopped_resume(cursor, "observation_inconsistent")
        consumed_requests.append(human_observation["request_id"])
        human_response_type = human_observation.get("observation_type")
        previous_observation = deepcopy(human_observation)
        actions.append({"round_index": rounds_used - 1, "selected_action": "HUMAN_FACT_RESPONSE",
                        "observation_type": human_observation.get("observation_type"),
                        "source": human_observation.get("source"),
                        "verification_status": human_observation.get("verification_status"),
                        "request_id": human_observation["request_id"],
                        "claim_index": human_observation["claim_index"],
                        "whether_new_information": human_observation.get("whether_new_information", False),
                        "consumed": True, "tool_calls_used": tool_calls_used})
    current_gap = None
    stop_reason = "no_eligible_action"
    retry_gap_index = None

    for round_index in range(rounds_used, max_rounds):
        rounds_used = round_index + 1
        recommendations = _recommend_after_human(extraction, current_coverage, current_relation,
                                                  rag_info, requested_gaps)
        rows = recommendations.get("claim_action_recommendations", [])
        eligible_actions = compute_eligible_actions(
            extraction, current_coverage, recommendations,
            requested_fact_gaps=requested_gaps,
            attempted_actions=attempted,
            remaining_rounds=max_rounds - round_index,
            remaining_tool_calls=max_calls - tool_calls_used,
            max_same_action_per_gap=same_action_limit,
            claim_relation=current_relation, rag_info=rag_info,
        )
        if (retry_gap_index is not None and tool_calls_used < max_calls
                and attempted.get(retry_gap_index, 0) < same_action_limit):
            retry_option = {"action": RETRIEVE_LEGAL_EVIDENCE,
                            "target_claim_index": retry_gap_index,
                            "reason_code": "RETRY_TRANSIENT_FAILURE"}
            eligible_actions = [retry_option] + [
                row for row in eligible_actions
                if not (row.get("action") == STOP_UNRESOLVED
                        or (row.get("action") == RETRIEVE_LEGAL_EVIDENCE
                            and row.get("target_claim_index") == retry_gap_index))
            ]
        selected, decision = _select_legal_action(
            eligible_actions, extraction, current_coverage,
            mode=mode, llm_call=llm_call, previous_observation=previous_observation,
            relation=current_relation, rag_info=rag_info, attempted=attempted,
            requested_gaps=requested_gaps, consumed_requests=consumed_requests,
            round_index=round_index, max_rounds=max_rounds,
            tool_calls_used=tool_calls_used, max_calls=max_calls,
            same_action_limit=same_action_limit, risk_level=risk_level,
        )
        if selected is None:
            stop_reason = "no_eligible_action_after_observation" if actions else "no_eligible_action"
            action = _loop_action(round_index, STOP_UNRESOLVED, stop_reason, stop_reason,
                                  0, max_calls - tool_calls_used)
            _annotate_decision(action, decision)
            actions.append(action)
            break

        selected_action = selected["action"]
        selected_index = selected["target_claim_index"]
        decision["dependency_type"] = dependencies[selected_index]["dependency_type"]
        decision["dependency_reason_code"] = dependencies[selected_index]["reason_code"]
        if decision.get("safety_stop"):
            stop_reason = decision["validator_reason_code"]
            action = _loop_action(round_index, STOP_UNRESOLVED, "proposal_rejected", stop_reason,
                                  0, max_calls - tool_calls_used)
            action["claim_index"] = selected_index
            _annotate_decision(action, decision)
            actions.append(action)
            break

        if selected_action == REQUEST_HUMAN_FACT:
            current_gap = {"claim_index": selected_index,
                           "claim": claims[selected_index].get("claim")}
            requested_gaps.append(selected_index)
            context_chars = len(_minimal_decision_context(
                event, claims[selected_index], current_relation,
                selected_index, previous_observation, risk_level,
                max_calls - tool_calls_used,
            ))
            action = _loop_action(round_index, REQUEST_HUMAN_FACT, "case_fact_unresolved",
                                  "human_fact_required", context_chars, max_calls - tool_calls_used)
            action["claim_index"] = selected_index
            action["tool_calls_used"] = tool_calls_used
            action["previous_observation"] = deepcopy(previous_observation)
            _annotate_decision(action, decision)
            actions.append(action)
            stop_reason = "human_fact_required"
            break

        if selected_action in {USE_EXISTING_EVIDENCE, STOP_RESOLVED, STOP_UNRESOLVED}:
            legal_rows = [row for row in current_coverage.get("claim_coverage", [])
                          if isinstance(row, dict) and row.get("legal_rule_status") != "not_required"]
            if selected_action == USE_EXISTING_EVIDENCE and legal_rows:
                use_existing = _loop_action(round_index, USE_EXISTING_EVIDENCE, "candidate_rule_available",
                                            "evidence_sufficient_for_rule_requirement", 0,
                                            max_calls - tool_calls_used)
                use_existing["tool_calls_used"] = tool_calls_used
                use_existing["claim_index"] = selected_index
                _annotate_decision(use_existing, decision)
                actions.append(use_existing)
                unresolved_fact = bool(requested_gaps)
                final_reason = ("fact_unavailable_requires_safe_revision" if unresolved_fact and
                                human_response_type == "fact_unavailable" else
                                _human_stop_reason(human_response_type) if unresolved_fact else
                                "task_evidence_requirements_resolved")
                stop = _loop_action(round_index, STOP_UNRESOLVED if unresolved_fact else STOP_RESOLVED,
                                    "case_fact_unresolved" if unresolved_fact else "all_rule_gaps_resolved",
                                    final_reason, 0,
                                    max_calls - tool_calls_used)
                stop["tool_calls_used"] = tool_calls_used
                actions.append(stop)
                stop_reason = final_reason
            else:
                stop_reason = ("tool_budget_exhausted" if tool_calls_used >= max_calls and
                               any(row.get("recommended_action") == TARGETED_LEGAL_SEARCH
                                   for row in rows if isinstance(row, dict)) else
                               _terminal_stop_reason(actions, requested_gaps, human_response_type))
                stop = _loop_action(round_index, STOP_UNRESOLVED, stop_reason, stop_reason,
                                    0, max_calls - tool_calls_used)
                stop["tool_calls_used"] = tool_calls_used
                stop["claim_index"] = selected_index
                _annotate_decision(stop, decision)
                actions.append(stop)
            break

        if selected_action != RETRIEVE_LEGAL_EVIDENCE:
            stop_reason = "action_not_allowed"
            actions.append(_loop_action(round_index, STOP_UNRESOLVED, stop_reason, stop_reason,
                                        0, max_calls - tool_calls_used))
            break

        if tool_calls_used >= max_calls:
            stop_reason = "tool_budget_exhausted"
            actions.append(_loop_action(round_index, STOP_UNRESOLVED, stop_reason, stop_reason,
                                        0, 0))
            actions[-1]["tool_calls_used"] = tool_calls_used
            break

        claim_index = selected_index
        candidate = {"claim_index": claim_index, "recommended_action": TARGETED_LEGAL_SEARCH,
                     "action_reason": selected.get("reason_code", "LEGAL_RULE_GAP")}
        retry_gap_index = None
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
        _annotate_decision(execution, decision)
        actions.append(execution)
        previous_observation = {
            "claim_index": claim_index,
            "type": execution.get("observation_type", "tool_error"),
            "status": execution.get("status"),
            "legal_rule_status": execution.get("after_legal_rule_status", "uncertain"),
            "evidence_refs": deepcopy(execution.get("targeted_evidence_refs", [])),
            "claim_state_changed": execution.get("before_legal_rule_status") != execution.get("after_legal_rule_status"),
        }
        _apply_targeted_observation(current_coverage, current_relation, execution)
        stop_reason = execution.get("stop_reason", "action_completed")
        if execution.get("status") == "completed" and execution.get("after_legal_rule_status") == execution.get("before_legal_rule_status"):
            stop_reason = "unresolved_after_observation" if requested_gaps else "no_information_gain"
            execution["stop_reason"] = stop_reason
            break
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
        stop_reason = "round_budget_exhausted" if resume else "max_rounds_reached"
        actions.append(_loop_action(max_rounds, "STOP_UNRESOLVED", stop_reason, stop_reason,
                                    0, max(0, max_calls - tool_calls_used)))

    if tool_calls_used >= max_calls and stop_reason not in {
        "task_evidence_requirements_resolved", "human_fact_required", "tool_failure",
        "fact_unavailable_requires_safe_revision", "human_asserted_fact_requires_review",
        "no_information_gain",
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
        "claim_action_recommendation": _recommend_after_human(extraction, current_coverage,
                                                                 current_relation, rag_info,
                                                                 requested_gaps if resume else []),
        "tool_calls_used": tool_calls_used,
        "remaining_budget": {"rounds": max(0, max_rounds - rounds_used),
                             "tool_calls": max(0, max_calls - tool_calls_used)},
        "context_budget": context_budget,
        "context_chars_total": sum(item.get("context_chars", 0) for item in actions),
        "current_gap": current_gap,
        "claim_progress": _claim_progress(claims, current_coverage, requested_gaps, attempted),
        "information_dependencies": dependencies,
        "phase": "WAITING_HUMAN" if stop_reason == "human_fact_required" else "STOPPED",
        "stop_reason": stop_reason,
        "cursor": {"round_count": rounds_used, "tool_calls_used": tool_calls_used,
                   "current_claim_index": (current_gap or {}).get("claim_index") if current_gap else
                                          _latest_claim_index(actions, previous_observation),
                   "claim_progress": _claim_progress(claims, current_coverage, requested_gaps, attempted),
                   "information_dependencies": dependencies, "claim_gap_state": _gap_state(current_coverage),
                   "attempted_actions": attempted, "requested_fact_gaps": requested_gaps,
                   "consumed_request_ids": consumed_requests, "previous_observation": previous_observation,
                   "human_response_type": human_response_type,
                   "mode": mode,
                   "rag_info": {key: rag_info.get(key) for key in (
                       "query", "retrieval_status", "retrieval_executed", "fallback_used")},
                   "actions": deepcopy(actions), "remaining_rounds": max(0, max_rounds - rounds_used),
                   "remaining_tool_calls": max(0, max_calls - tool_calls_used),
                   "stop_reason": stop_reason},
    }


def _recommend_after_human(extraction: dict, coverage: dict, relation: dict, rag: dict,
                           requested_gaps: list[int]) -> dict:
    if not requested_gaps:
        return recommend_legal_actions(extraction, coverage, relation, rag)
    adjusted_extraction, adjusted_coverage = deepcopy(extraction), deepcopy(coverage)
    for index in requested_gaps:
        claim = adjusted_extraction.get("legal_claims", [])[index]
        if claim.get("requires_legal_rule"):
            claim["requires_case_fact"] = False
            row = next((row for row in adjusted_coverage.get("claim_coverage", [])
                        if row.get("claim_index") == index), None)
            if row is not None:
                row["case_fact_status"] = "not_required"
                row.pop("case_fact_reason", None)
    recommendations = recommend_legal_actions(adjusted_extraction, adjusted_coverage, relation, rag)
    for row in recommendations["claim_action_recommendations"]:
        if row["claim_index"] in requested_gaps and row["recommended_action"] == REQUEST_HUMAN_FACT_VERIFICATION:
            row.update(recommended_action="STOP_UNRESOLVED", action_reason="human_fact_already_consumed")
    return recommendations


def _information_dependencies(claims: list) -> list[dict]:
    return [{"claim_index": index,
             "dependency_type": result["dependency_type"], "reason_code": result["reason_code"]}
            for index, claim in enumerate(claims if isinstance(claims, list) else [])
            for result in [classify_legal_query_dependency(claim)]]


def _gap_state(coverage: dict) -> list[dict]:
    return [{key: row.get(key) for key in ("claim_index", "case_fact_status", "case_fact_input_status",
                                           "legal_rule_status", "verification_status")}
            for row in coverage.get("claim_coverage", []) if isinstance(row, dict)]


def _apply_human_input_observation(coverage: dict, observation: dict) -> bool:
    kind = observation.get("observation_type")
    if kind not in {"fact_provided", "fact_unavailable"}:
        return False
    provided = kind == "fact_provided"
    if (observation.get("response_type") != ("FACT_PROVIDED" if provided else "FACT_UNAVAILABLE")
            or observation.get("verification_status") != ("human_asserted" if provided else "unresolved")):
        return False
    index = observation.get("claim_index")
    row = next((item for item in coverage.get("claim_coverage", [])
                if isinstance(item, dict) and item.get("claim_index") == index), None)
    if not isinstance(row, dict) or row.get("case_fact_status") != "unresolved":
        return False
    new_status = "human_asserted" if provided else "unavailable"
    observation["claim_state_changed"] = row.get("case_fact_input_status") != new_status
    row["case_fact_input_status"] = new_status
    row["verification_status"] = "human_asserted" if provided else "unresolved"
    return True


def _human_stop_reason(observation_type: str | None) -> str:
    if observation_type == "fact_provided":
        return "human_asserted_fact_requires_review"
    return "no_information_gain"


def _claim_progress(claims: list, coverage: dict, requested_gaps: list[int],
                    attempted_actions: dict[int, int] | None = None) -> list[dict]:
    """Summarize bounded progression without copying claim or evidence text."""
    requested = set(requested_gaps)
    attempted = attempted_actions or {}
    by_index = {
        row.get("claim_index"): row
        for row in coverage.get("claim_coverage", [])
        if isinstance(row, dict) and type(row.get("claim_index")) is int
    }
    progress = []
    for index, claim in enumerate(claims if isinstance(claims, list) else []):
        if not isinstance(claim, dict):
            progress.append({"claim_index": index, "status": "ATTEMPTED_UNRESOLVED"})
            continue
        observed = by_index.get(index, {})
        needs_case_fact = claim.get("requires_case_fact") is True
        needs_legal_rule = claim.get("requires_legal_rule") is True
        has_requirement = needs_case_fact or needs_legal_rule
        case_covered = not needs_case_fact or observed.get("case_fact_status") == "resolved"
        rule_covered = not needs_legal_rule or observed.get("legal_rule_status") == "candidate_found"
        if has_requirement and case_covered and rule_covered:
            status = "COVERED"
        elif index in requested or attempted.get(index, 0) > 0:
            status = "ATTEMPTED_UNRESOLVED"
        else:
            status = "UNTOUCHED"
        progress.append({"claim_index": index, "status": status})
    return progress


def _latest_claim_index(actions: list[dict], previous_observation: dict | None) -> int | None:
    for action in reversed(actions):
        index = action.get("claim_index") if isinstance(action, dict) else None
        if type(index) is int:
            return index
    index = previous_observation.get("claim_index") if isinstance(previous_observation, dict) else None
    return index if type(index) is int else None


def _stopped_resume(cursor: dict, reason: str) -> dict:
    result = {"status": "stopped", "phase": "STOPPED", "stop_reason": reason,
              "actions": deepcopy(cursor.get("actions", [])),
              "tool_calls_used": cursor.get("tool_calls_used", 0),
              "rounds": cursor.get("round_count", 0),
              "remaining_budget": {"rounds": cursor.get("remaining_rounds", 0),
                                   "tool_calls": cursor.get("remaining_tool_calls", 0)}}
    result["cursor"] = deepcopy(cursor)
    return result


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _select_legal_action(
    eligible_actions: list[dict],
    extraction: dict,
    coverage: dict,
    *,
    mode: str,
    llm_call: Callable | None,
    previous_observation: dict | None,
    relation: dict,
    rag_info: dict,
    attempted: dict[int, int],
    requested_gaps: list[int],
    consumed_requests: list[str],
    round_index: int,
    max_rounds: int,
    tool_calls_used: int,
    max_calls: int,
    same_action_limit: int,
    risk_level: str,
) -> tuple[dict | None, dict]:
    observation = previous_observation if isinstance(previous_observation, dict) else {}
    decision = {
        "round": round_index,
        "previous_observation_type": observation.get("type", observation.get("observation_type")),
        "previous_observation_changed_state": bool(
            observation.get("claim_state_changed", observation.get("whether_new_information", False))
        ),
        "eligible_action_count": len(eligible_actions),
        "proposal_status": "NOT_CALLED",
        "proposal_called": False,
        "validator_called": False,
        "proposal_action": None,
        "proposal_reason_code": None,
        "proposal_target_claim_index": None,
        "validator_allowed": None,
        "validator_reason_code": "proposal_not_required",
        "proposal_fallback_used": False,
        "fallback_reason_code": None,
        "safety_stop": False,
        "deterministic_baseline_action": None,
        "deterministic_baseline_target_claim_index": None,
        "eligible_actions": [
            {"action": row.get("action"), "target_claim_index": row.get("target_claim_index")}
            for row in eligible_actions if isinstance(row, dict)
        ],
        "eligible_target_claim_indices": [
            row.get("target_claim_index") for row in eligible_actions
            if isinstance(row, dict) and type(row.get("target_claim_index")) is int
        ],
        "remaining_rounds": max(0, max_rounds - round_index),
        "remaining_tool_calls": max(0, max_calls - tool_calls_used),
    }
    if not eligible_actions:
        decision["validator_allowed"] = None
        decision["validator_reason_code"] = "no_eligible_action"
        return None, decision

    deterministic = _deterministic_choice(eligible_actions)
    decision["deterministic_baseline_action"] = deterministic.get("action")
    decision["deterministic_baseline_target_claim_index"] = deterministic.get("target_claim_index")
    if mode != "llm" or len(eligible_actions) < 2:
        decision["validator_allowed"] = None
        decision["validator_reason_code"] = (
            "offline_deterministic_path" if mode != "llm" else "single_eligible_action"
        )
        return deterministic, decision

    context = build_legal_decision_context(
        extraction, coverage, relation, rag_info, eligible_actions,
        previous_observation=previous_observation,
        attempted_actions=attempted,
        requested_fact_gaps=requested_gaps,
        round_count=round_index,
        remaining_rounds=max(0, max_rounds - round_index),
        remaining_tool_calls=max(0, max_calls - tool_calls_used),
        risk_level=risk_level,
    )
    decision["proposal_context_chars"] = len(str(context))
    result = request_legal_action_proposal(context, llm_call=llm_call)
    decision["proposal_called"] = True
    proposal = result.get("proposal")
    if not isinstance(proposal, dict):
        decision["proposal_status"] = _proposal_failure_status(result.get("failure_type"))
        decision["proposal_fallback_used"] = True
        decision["fallback_reason_code"] = _fallback_reason(result.get("failure_type"))
        decision["validator_allowed"] = False
        decision["validator_reason_code"] = result.get("failure_type", "proposal_failure")
        return deterministic, decision

    decision["proposal_status"] = "VALID"
    raw_action = proposal.get("action")
    decision["proposal_action"] = raw_action if raw_action in LEGAL_ACTION_WHITELIST else "UNKNOWN_ACTION"
    decision["proposal_reason_code"] = proposal.get("reason_code")
    decision["proposal_target_claim_index"] = proposal.get("target_claim_index")
    decision["validator_called"] = True
    validation = validate_action_proposal(
        proposal, eligible_actions, extraction, coverage,
        requested_fact_gaps=requested_gaps,
        consumed_request_ids=consumed_requests,
        attempted_actions=attempted,
        remaining_rounds=max_rounds - round_index,
        remaining_tool_calls=max_calls - tool_calls_used,
        max_same_action_per_gap=same_action_limit,
        previous_observation=previous_observation,
    )
    decision["validator_allowed"] = validation["allowed"]
    decision["validator_reason_code"] = validation["reason_code"]
    if validation["reason_code"] == "action_not_allowed":
        decision["proposal_status"] = "UNKNOWN_ACTION"
    elif validation["reason_code"] in {"invalid_claim_index", "invalid_target"}:
        decision["proposal_status"] = "INVALID_TARGET"
    elif not validation["allowed"]:
        decision["proposal_status"] = "REJECTED"
    if validation["allowed"]:
        return next(row for row in eligible_actions
                    if row["action"] == proposal["action"]
                    and row["target_claim_index"] == proposal["target_claim_index"]), decision
    if validation.get("safety_violation"):
        decision["safety_stop"] = True
        return {"action": STOP_UNRESOLVED,
                "target_claim_index": proposal.get("target_claim_index", 0),
                "reason_code": "REQUIREMENTS_UNRESOLVED"}, decision
    decision["proposal_fallback_used"] = True
    decision["fallback_reason_code"] = _fallback_reason(validation["reason_code"])
    return deterministic, decision


def _deterministic_choice(eligible_actions: list[dict]) -> dict:
    priority = {
        REQUEST_HUMAN_FACT: 0,
        RETRIEVE_LEGAL_EVIDENCE: 1,
        USE_EXISTING_EVIDENCE: 2,
        STOP_RESOLVED: 3,
        STOP_UNRESOLVED: 4,
    }
    return min(eligible_actions, key=lambda row: (
        priority.get(row.get("action"), 99), row.get("target_claim_index", 0)
    ))


def _annotate_decision(action: dict, decision: dict) -> None:
    decision["fallback_used"] = bool(decision.get("proposal_fallback_used"))
    decision["executed_action"] = action.get("selected_action")
    decision["executed_target_claim_index"] = action.get("claim_index")
    decision["result_observation_type"] = action.get("observation_type")
    decision["result_observation_status"] = action.get("status") or action.get("stop_reason")
    for key in (
        "round", "previous_observation_type", "previous_observation_changed_state",
        "eligible_action_count", "eligible_actions", "eligible_target_claim_indices",
        "deterministic_baseline_action", "deterministic_baseline_target_claim_index",
        "proposal_called", "proposal_status", "proposal_action", "proposal_reason_code",
        "proposal_target_claim_index", "validator_called", "validator_allowed",
        "validator_reason_code", "proposal_fallback_used", "fallback_used",
        "fallback_reason_code",
        "safety_stop",
        "executed_action", "executed_target_claim_index", "result_observation_type",
        "result_observation_status", "remaining_rounds", "remaining_tool_calls",
        "proposal_context_chars",
        "dependency_type", "dependency_reason_code",
    ):
        if key in decision:
            action[key] = decision[key]


def _terminal_stop_reason(actions: list[dict], requested_gaps: list[int],
                          human_response_type: str | None) -> str:
    if requested_gaps and any(item.get("selected_action") == RETRIEVE_LEGAL_EVIDENCE
                              for item in actions):
        return "unresolved_after_observation"
    if requested_gaps:
        return _human_stop_reason(human_response_type)
    return "no_eligible_action_after_observation" if actions else "no_eligible_action"


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
