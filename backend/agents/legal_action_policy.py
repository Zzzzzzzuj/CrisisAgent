"""Recommend, but never execute, a next action for each Legal claim."""

from collections import Counter


CONTINUE = "CONTINUE"
TARGETED_LEGAL_SEARCH = "TARGETED_LEGAL_SEARCH"
REQUEST_HUMAN_FACT_VERIFICATION = "REQUEST_HUMAN_FACT_VERIFICATION"
STOP_UNRESOLVED = "STOP_UNRESOLVED"

_NORMAL_RETRIEVAL = "executed_with_hits"
_NO_HIT = "executed_no_hit"
_NOT_COMPLETED = {"not_started", "disabled", "skipped_by_gate", "retrieval_error"}
_PAIR_REASONS = {"claim_context_insufficient", "semantic_relation_unclear"}


def recommend_legal_actions(
    claim_extraction: dict,
    claim_coverage: dict,
    claim_relation: dict,
    rag_info: dict,
) -> dict:
    """Use only frozen observations; no retrieval, model, tool, or review side effect."""
    claims = claim_extraction.get("legal_claims", []) if isinstance(claim_extraction, dict) else []
    coverage = claim_coverage.get("claim_coverage", []) if isinstance(claim_coverage, dict) else []
    relations = claim_relation.get("legal_claim_relations", []) if isinstance(claim_relation, dict) else []
    retrieval_status = rag_info.get("retrieval_status") if isinstance(rag_info, dict) else None
    if not isinstance(claims, list):
        claims = []
    if not isinstance(coverage, list):
        coverage = []
    if not isinstance(relations, list):
        relations = []

    counts = Counter(row["claim_index"] for row in coverage
                     if isinstance(row, dict) and type(row.get("claim_index")) is int)
    by_index = {row["claim_index"]: row for row in coverage
                if isinstance(row, dict) and type(row.get("claim_index")) is int}
    recommendations = []
    for index, claim in enumerate(claims):
        observed = by_index.get(index)
        if counts[index] != 1 or len(coverage) != len(claims):
            action, reason = STOP_UNRESOLVED, "observation_inconsistent"
        else:
            action, reason = _decide(claim, observed, claim_relation, relations, rag_info, retrieval_status)
        recommendations.append({"claim_index": index, "recommended_action": action, "action_reason": reason})
    return {"claim_action_recommendations": recommendations}


def _decide(claim: dict, coverage: dict, relation: dict, rows: list,
            rag_info: dict, retrieval_status: str | None) -> tuple[str, str]:
    if not isinstance(claim, dict) or not isinstance(coverage, dict):
        return STOP_UNRESOLVED, "observation_inconsistent"
    legal_required = claim.get("requires_legal_rule") is True
    fact_required = claim.get("requires_case_fact") is True
    legal_status = coverage.get("legal_rule_status")
    fact_status = coverage.get("case_fact_status")
    if not (legal_required or fact_required):
        return STOP_UNRESOLVED, "observation_inconsistent"
    if legal_status not in {"not_required", "candidate_found", "no_candidate", "uncertain"}:
        return STOP_UNRESOLVED, "observation_inconsistent"
    if (legal_required and legal_status == "not_required") or (not legal_required and legal_status != "not_required"):
        return STOP_UNRESOLVED, "observation_inconsistent"
    if fact_required:
        if fact_status != "unresolved" or coverage.get("case_fact_reason") != "trusted_case_fact_unavailable":
            return STOP_UNRESOLVED, "observation_inconsistent"
        return REQUEST_HUMAN_FACT_VERIFICATION, "trusted_case_fact_unavailable"
    if fact_status != "not_required":
        return STOP_UNRESOLVED, "observation_inconsistent"
    if not legal_required:
        return STOP_UNRESOLVED, "observation_inconsistent"

    if isinstance(relation, dict) and relation.get("relation_status") == "fallback":
        return STOP_UNRESOLVED, "relation_module_failure"
    if retrieval_status == _NO_HIT:
        return STOP_UNRESOLVED, "retrieval_no_hit"
    if retrieval_status in _NOT_COMPLETED or retrieval_status != _NORMAL_RETRIEVAL:
        return STOP_UNRESOLVED, "retrieval_not_completed"
    if not isinstance(relation, dict) or relation.get("relation_status") != "ok":
        return STOP_UNRESOLVED, "uncertainty_unexplained"

    matching = [row for row in rows if isinstance(row, dict)
                and row.get("claim_index") == coverage["claim_index"]]
    if legal_status == "candidate_found":
        if not any(row.get("relation") == "candidate_rule_relevant" for row in matching):
            return STOP_UNRESOLVED, "observation_inconsistent"
        return CONTINUE, "candidate_rule_available"
    if legal_status == "no_candidate":
        if not matching or any(row.get("relation") != "no_rule_match" for row in matching):
            return STOP_UNRESOLVED, "observation_inconsistent"
        if rag_info.get("retrieval_executed") is not True:
            return STOP_UNRESOLVED, "retrieval_not_completed"
        if rag_info.get("fallback_used") is True:
            return STOP_UNRESOLVED, "retrieval_fallback_used"
        return TARGETED_LEGAL_SEARCH, "targeted_legal_search_may_improve_coverage"
    if legal_status == "uncertain":
        reasons = {row.get("reason") for row in matching
                   if row.get("relation") == "uncertain" and row.get("reason") in _PAIR_REASONS}
        if "claim_context_insufficient" in reasons:
            return STOP_UNRESOLVED, "claim_context_insufficient"
        if "semantic_relation_unclear" in reasons:
            return STOP_UNRESOLVED, "semantic_relation_unclear"
    return STOP_UNRESOLVED, "uncertainty_unexplained"
