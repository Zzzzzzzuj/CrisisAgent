"""Offline deterministic regression baseline for one targeted Legal search."""

from backend.agents.legal_action_policy import recommend_legal_actions
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_claim_relation import build_legal_claim_relations
from backend.agents.legal_targeted_search import execute_recommended_targeted_search


_CLAIM = "使用过期食品原料可能违反食品安全规定"
_CASES = (
    ("rule_found", "食品生产经营者不得使用超过保质期的食品原料。", False),
    ("rule_found_second", "食品生产经营者禁止使用超过保质期的食品原料。", False),
    ("guidance_only", "建议企业及时回应公众关切。", False),
    ("generic_rule", "企业必须遵守相关监管要求。", False),
    ("empty", "", False),
    ("fallback", "食品生产经营者不得使用超过保质期的食品原料。", True),
)


def run_legal_targeted_loop_eval() -> dict:
    """Fake retrieval fixtures measure coverage transitions, not legal accuracy."""
    rows = []
    for case_id, text, fallback in _CASES:
        claim = {"claim": _CLAIM, "requires_legal_rule": True, "requires_case_fact": False}
        extraction = {"legal_claims": [claim], "claim_extraction_status": "ok"}
        original_relation = {"legal_claim_relations": [
            {"claim_index": 0, "evidence_ref": "broad", "relation": "no_rule_match"}],
            "relation_status": "ok"}
        coverage = build_claim_coverage([claim], original_relation)
        rag = {"query": "事件：食品投诉；草稿：完整声明；红队：批评文本",
               "retrieval_status": "executed_with_hits", "retrieval_executed": True, "fallback_used": False}
        recommendation = recommend_legal_actions(extraction, coverage, original_relation, rag)
        chunks = [{"chunk_id": case_id, "source": "frozen", "text": text}] if text else []
        retrieval = {"chunks": chunks, "fallback_used": fallback}
        action = execute_recommended_targeted_search(
            extraction, coverage, original_relation, recommendation, rag,
            retrieve_call=lambda _query, top_k: retrieval,
            relation_call=build_legal_claim_relations,
        )["targeted_search_executions"][0]
        rows.append({"case_id": case_id, "before_coverage": action["before_legal_rule_status"],
                     "after_coverage": action["after_legal_rule_status"], "status": action["status"]})
    return {
        "dataset_kind": "fixed_fake_retriever_regression",
        "eligible_targeted_search_cases": len(_CASES),
        "targeted_searches_executed": len(rows),
        "coverage_improved_count": sum(row["after_coverage"] == "candidate_found" for row in rows),
        "unchanged_count": sum(row["after_coverage"] == row["before_coverage"] for row in rows),
        "degraded_or_uncertain_count": sum(row["after_coverage"] == "uncertain" for row in rows),
        "cases": rows,
    }
