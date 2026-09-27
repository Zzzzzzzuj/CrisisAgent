"""Describe legal-rule candidate coverage and the case-fact capability boundary."""

from backend.agents.legal_claim_relation import RELATIONS


_CASE_FACT_REASON = "trusted_case_fact_unavailable"


def build_claim_coverage(claims: list[dict], relation_result: dict) -> dict:
    """Summarize P31A relations without verifying any claim or case fact."""
    claims = claims if isinstance(claims, list) else []
    relation_result = relation_result if isinstance(relation_result, dict) else {}
    rows = relation_result.get("legal_claim_relations", [])
    grouped: dict[int, list[str]] = {}
    valid = isinstance(rows, list)
    if valid:
        for row in rows:
            if not isinstance(row, dict):
                valid = False
                break
            index, ref, relation = row.get("claim_index"), row.get("evidence_ref"), row.get("relation")
            if (type(index) is not int or index < 0 or index >= len(claims)
                    or not isinstance(ref, str) or not ref
                    or not isinstance(relation, str) or relation not in RELATIONS
                    or not isinstance(claims[index], dict)
                    or claims[index].get("requires_legal_rule") is not True):
                valid = False
                break
            grouped.setdefault(index, []).append(relation)

    coverage = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        legal_required = claim.get("requires_legal_rule") is True
        case_fact_required = claim.get("requires_case_fact") is True
        if not legal_required:
            legal_status = "not_required"
        elif not valid or relation_result.get("relation_status") != "ok":
            legal_status = "uncertain"
        else:
            relations = grouped.get(index, [])
            if "candidate_rule_relevant" in relations:
                legal_status = "candidate_found"
            elif relations and all(relation == "no_rule_match" for relation in relations):
                legal_status = "no_candidate"
            else:
                legal_status = "uncertain"
        item = {
            "claim_index": index,
            "legal_rule_status": legal_status,
            "case_fact_status": "unresolved" if case_fact_required else "not_required",
        }
        if case_fact_required:
            item["case_fact_reason"] = _CASE_FACT_REASON
        coverage.append(item)
    return {"claim_coverage": coverage}
