"""Run at most one P32-recommended claim-level search as a shadow observation."""

from copy import deepcopy
from typing import Callable

from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_action_policy import recommend_legal_actions, TARGETED_LEGAL_SEARCH
from backend.agents.legal_claim_relation import build_legal_claim_relations, evidence_ref


MAX_TARGETED_ROUNDS = 1


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
    }
    try:
        result = retrieve_call(query, top_k=3)
        if not isinstance(result, dict):
            raise ValueError("Targeted retrieval returned an invalid result.")
        chunks = result.get("chunks", [])
        if not isinstance(chunks, list):
            raise ValueError("Targeted retrieval returned invalid chunks.")
        action["targeted_evidence_refs"] = list(dict.fromkeys(
            ref for chunk in chunks if isinstance(chunk, dict)
            if (ref := evidence_ref(chunk)) is not None
        ))
        fallback_used = _fallback_used(result)
        if not chunks:
            action["status"] = "no_hit"
            targeted_relation = {"legal_claim_relations": [], "relation_status": "skipped"}
        else:
            targeted_relation = relation_call([claim], chunks, mode=mode, llm_call=llm_call)
            if not isinstance(targeted_relation, dict):
                raise ValueError("Targeted relation returned an invalid result.")
            action["status"] = "fallback" if fallback_used else (
                "relation_failed" if targeted_relation.get("relation_status") != "ok" else "completed"
            )
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
    return {"targeted_search_executions": [action]}


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
