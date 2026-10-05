"""Recommend, but never execute, a next action for each Legal claim."""

import re
from collections import Counter


CONTINUE = "CONTINUE"
TARGETED_LEGAL_SEARCH = "TARGETED_LEGAL_SEARCH"
REQUEST_HUMAN_FACT_VERIFICATION = "REQUEST_HUMAN_FACT_VERIFICATION"
STOP_UNRESOLVED = "STOP_UNRESOLVED"

RETRIEVE_LEGAL_EVIDENCE = "RETRIEVE_LEGAL_EVIDENCE"
REQUEST_HUMAN_FACT = "REQUEST_HUMAN_FACT"
USE_EXISTING_EVIDENCE = "USE_EXISTING_EVIDENCE"
STOP_RESOLVED = "STOP_RESOLVED"
LEGAL_RUNTIME_ACTIONS = frozenset({
    RETRIEVE_LEGAL_EVIDENCE,
    REQUEST_HUMAN_FACT,
    USE_EXISTING_EVIDENCE,
    STOP_RESOLVED,
    STOP_UNRESOLVED,
})

_NORMAL_RETRIEVAL = "executed_with_hits"
_NO_HIT = "executed_no_hit"
_NOT_COMPLETED = {"not_started", "disabled", "skipped_by_gate", "retrieval_error"}
_PAIR_REASONS = {"claim_context_insufficient", "semantic_relation_unclear"}
_CLAUSE_BREAK = re.compile(r"[，,；;。！？?!\n]+")
_CURRENT_FACT_MARKERS = ("公司", "我司", "本公司", "本企业", "该企业", "涉事", "本次", "当前", "该产品")
_FACT_STATE_MARKERS = ("是否", "已", "尚未", "正在", "有没有", "未确认")
_RULE_MARKERS = ("法律", "法规", "规定", "法定", "义务", "监管要求", "合规")
_DEPENDENT_REFERENCES = ("该类", "该类别", "上述", "这一", "该产品", "本次", "涉事", "具体类别", "哪类")
_GENERIC_RULE_PATTERNS = ("可能违反", "是否违反", "是否合法", "是否合规")
_NON_TOPIC_PAIRS = {"公司", "企业", "是否", "法律", "法规", "规定", "需要", "当前",
                    "已经", "尚未", "确认", "问题", "情况", "相关", "何时", "哪些"}


def classify_legal_query_dependency(claim: dict) -> dict:
    """Identify a separable rule question; ambiguity remains fact-dependent."""
    if not isinstance(claim, dict):
        return {"dependency_type": "FACT_DEPENDENT", "reason_code": "INVALID_CLAIM", "legal_rule_topic": None}
    legal = claim.get("requires_legal_rule") is True
    fact = claim.get("requires_case_fact") is True
    text = claim.get("claim")
    if not isinstance(text, str) or not text.strip():
        return {"dependency_type": "FACT_DEPENDENT", "reason_code": "INVALID_CLAIM", "legal_rule_topic": None}
    text = text.strip()
    if not (legal and fact):
        return {"dependency_type": "NOT_APPLICABLE", "reason_code": "SINGLE_GAP_TYPE",
                "legal_rule_topic": text if legal else None}

    clauses = [part.strip() for part in _CLAUSE_BREAK.split(text) if part.strip()]
    fact_clauses = [part for part in clauses if any(marker in part for marker in _CURRENT_FACT_MARKERS)
                    and any(marker in part for marker in _FACT_STATE_MARKERS)]
    for rule_clause in clauses:
        if (not any(marker in rule_clause for marker in _RULE_MARKERS)
                or any(marker in rule_clause for marker in _DEPENDENT_REFERENCES)
                or any(marker in rule_clause for marker in _CURRENT_FACT_MARKERS)):
            continue
        if any(_shares_topic(fact_clause, rule_clause) for fact_clause in fact_clauses
               if fact_clause != rule_clause):
            return {"dependency_type": "INDEPENDENT", "reason_code": "SEPARATE_RULE_CLAUSE",
                    "legal_rule_topic": rule_clause}

    if (len(clauses) == 1 and not any(marker in text for marker in _CURRENT_FACT_MARKERS)
            and any(pattern in text for pattern in _GENERIC_RULE_PATTERNS)):
        return {"dependency_type": "INDEPENDENT", "reason_code": "GENERAL_CONDITIONAL_RULE",
                "legal_rule_topic": text}
    return {"dependency_type": "FACT_DEPENDENT", "reason_code": "RULE_TOPIC_REQUIRES_CASE_FACT",
            "legal_rule_topic": None}


def _shares_topic(fact_clause: str, rule_clause: str) -> bool:
    pairs = {fact_clause[index:index + 2] for index in range(len(fact_clause) - 1)}
    return any(pair not in _NON_TOPIC_PAIRS and pair in rule_clause for pair in pairs)


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


def compute_eligible_actions(
    claim_extraction: dict,
    claim_coverage: dict,
    recommendations: dict,
    *,
    requested_fact_gaps: list[int] | None = None,
    attempted_actions: dict[int, int] | None = None,
    remaining_rounds: int,
    remaining_tool_calls: int,
    max_same_action_per_gap: int,
    claim_relation: dict | None = None,
    rag_info: dict | None = None,
) -> list[dict]:
    """Return safe, meaningful runtime actions without choosing between them."""
    if remaining_rounds <= 0:
        return []
    claims = claim_extraction.get("legal_claims", []) if isinstance(claim_extraction, dict) else []
    coverage = claim_coverage.get("claim_coverage", []) if isinstance(claim_coverage, dict) else []
    rows = recommendations.get("claim_action_recommendations", []) if isinstance(recommendations, dict) else []
    if not isinstance(claims, list) or not isinstance(coverage, list) or not isinstance(rows, list):
        return []
    requested = set(requested_fact_gaps or [])
    attempted = attempted_actions or {}
    relation_rows = claim_relation.get("legal_claim_relations", []) if isinstance(claim_relation, dict) else []
    retrieval_status = rag_info.get("retrieval_status") if isinstance(rag_info, dict) else None
    options = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("claim_index")) is not int:
            continue
        index = row["claim_index"]
        if index < 0 or index >= len(claims):
            continue
        action = row.get("recommended_action")
        if action == REQUEST_HUMAN_FACT_VERIFICATION and index not in requested:
            options.append(_option(REQUEST_HUMAN_FACT, index, "CASE_FACT_GAP"))
        claim = claims[index]
        observed = next((item for item in coverage if isinstance(item, dict)
                         and item.get("claim_index") == index), None)
        if (not isinstance(claim, dict) or not isinstance(observed, dict)
                or remaining_tool_calls <= 0 or attempted.get(index, 0) >= max_same_action_per_gap):
            continue
        dependency = classify_legal_query_dependency(claim)
        mixed = claim.get("requires_case_fact") is True and claim.get("requires_legal_rule") is True
        if mixed and dependency["dependency_type"] != "INDEPENDENT":
            continue
        if mixed and (not isinstance(claim_relation, dict) or not isinstance(rag_info, dict)):
            continue
        rule_action = action
        if mixed:
            rule_claim = {**claim, "requires_case_fact": False}
            rule_coverage = {**observed, "case_fact_status": "not_required"}
            rule_action, _ = _decide(rule_claim, rule_coverage, claim_relation, relation_rows,
                                     rag_info, retrieval_status)
        if rule_action == TARGETED_LEGAL_SEARCH:
            options.append(_option(RETRIEVE_LEGAL_EVIDENCE, index, "LEGAL_RULE_GAP"))
    if options:
        return options

    legal_rows = [row for row in coverage
                  if isinstance(row, dict) and row.get("legal_rule_status") != "not_required"]
    if legal_rows and all(row.get("legal_rule_status") == "candidate_found" for row in legal_rows):
        index = min((row.get("claim_index") for row in legal_rows
                     if type(row.get("claim_index")) is int), default=0)
        return [_option(USE_EXISTING_EVIDENCE, index, "EXISTING_EVIDENCE_AVAILABLE")]

    valid_indices = [index for index, claim in enumerate(claims) if isinstance(claim, dict)]
    if valid_indices:
        return [_option(STOP_UNRESOLVED, valid_indices[0], "REQUIREMENTS_UNRESOLVED")]
    return []


def validate_action_proposal(
    proposal: dict,
    eligible_actions: list[dict],
    claim_extraction: dict,
    claim_coverage: dict,
    *,
    requested_fact_gaps: list[int] | None = None,
    consumed_request_ids: list[str] | None = None,
    attempted_actions: dict[int, int] | None = None,
    remaining_rounds: int,
    remaining_tool_calls: int,
    max_same_action_per_gap: int,
    previous_observation: dict | None = None,
) -> dict:
    """Validate a model proposal against current state and safety invariants."""
    if not isinstance(proposal, dict):
        return _validation(False, "invalid_proposal")
    action = proposal.get("action")
    index = proposal.get("target_claim_index")
    if action not in LEGAL_RUNTIME_ACTIONS:
        return _validation(False, "action_not_allowed")
    claims = claim_extraction.get("legal_claims", []) if isinstance(claim_extraction, dict) else []
    if type(index) is not int or index < 0 or index >= len(claims):
        return _validation(False, "invalid_claim_index")
    if remaining_rounds <= 0:
        return _validation(False, "round_budget_exhausted", safety_violation=True)
    if action == RETRIEVE_LEGAL_EVIDENCE and remaining_tool_calls <= 0:
        return _validation(False, "tool_budget_exhausted", safety_violation=True)

    requested = set(requested_fact_gaps or [])
    if action == REQUEST_HUMAN_FACT and index in requested:
        return _validation(False, "human_fact_already_consumed", safety_violation=True)
    if (action == RETRIEVE_LEGAL_EVIDENCE
            and (attempted_actions or {}).get(index, 0) >= max_same_action_per_gap):
        return _validation(False, "duplicate_action_without_information_gain", safety_violation=True)

    coverage_rows = claim_coverage.get("claim_coverage", []) if isinstance(claim_coverage, dict) else []
    observed = next((row for row in coverage_rows
                     if isinstance(row, dict) and row.get("claim_index") == index), None)
    claim = claims[index]
    if not isinstance(claim, dict) or not isinstance(observed, dict):
        return _validation(False, "observation_inconsistent")
    if action == RETRIEVE_LEGAL_EVIDENCE and not (
        claim.get("requires_legal_rule") is True
        and observed.get("legal_rule_status") in {"no_candidate", "uncertain"}
    ):
        return _validation(False, "retrieval_prerequisite_missing", safety_violation=True)
    if (action == RETRIEVE_LEGAL_EVIDENCE and claim.get("requires_case_fact") is True
            and classify_legal_query_dependency(claim)["dependency_type"] != "INDEPENDENT"):
        return _validation(False, "fact_dependent_legal_query", safety_violation=True)
    if action == USE_EXISTING_EVIDENCE and observed.get("legal_rule_status") != "candidate_found":
        return _validation(False, "evidence_not_available", safety_violation=True)
    if action == STOP_RESOLVED and _has_unresolved_requirement(claim_extraction, claim_coverage):
        return _validation(False, "unresolved_requirement", safety_violation=True)
    if (action == STOP_RESOLVED and isinstance(previous_observation, dict)
            and previous_observation.get("verification_status") == "human_asserted"):
        return _validation(False, "human_asserted_not_verified", safety_violation=True)

    eligible = next((row for row in eligible_actions if isinstance(row, dict)
                     and row.get("action") == action
                     and row.get("target_claim_index") == index), None)
    if eligible is None:
        return _validation(False, "action_not_eligible")
    if proposal.get("reason_code") not in {
        eligible.get("reason_code"), "OBSERVATION_CHANGED_PRIORITY",
    }:
        return _validation(False, "reason_code_not_eligible")
    return _validation(True, "allowed")


def _has_unresolved_requirement(claim_extraction: dict, claim_coverage: dict) -> bool:
    claims = claim_extraction.get("legal_claims", []) if isinstance(claim_extraction, dict) else []
    coverage = claim_coverage.get("claim_coverage", []) if isinstance(claim_coverage, dict) else []
    by_index = {row.get("claim_index"): row for row in coverage if isinstance(row, dict)}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            return True
        observed = by_index.get(index)
        if not isinstance(observed, dict):
            return True
        if claim.get("requires_case_fact") is True and observed.get("case_fact_status") != "resolved":
            return True
        if claim.get("requires_legal_rule") is True and observed.get("legal_rule_status") != "candidate_found":
            return True
    return False


def _option(action: str, claim_index: int, reason_code: str) -> dict:
    return {"action": action, "target_claim_index": claim_index, "reason_code": reason_code}


def _validation(allowed: bool, reason_code: str, *, safety_violation: bool = False) -> dict:
    return {"allowed": allowed, "reason_code": reason_code, "safety_violation": safety_violation}


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
