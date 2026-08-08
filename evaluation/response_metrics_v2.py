from evaluation.response_metrics import evaluate_response_quality


def evaluate_response_quality_v2(final_statement: str, event: str, case: dict | None = None) -> dict:
    case = case or {}
    base_evaluation = evaluate_response_quality(
        final_statement=final_statement,
        event=event,
        case={
            "must_include": _flatten_concept_groups(case.get("required_concepts", [])),
            "must_avoid": case.get("forbidden_domain_terms", []),
            "supported_facts": case.get("supported_facts", []),
        },
    )
    domain_relevance = score_domain_relevance(final_statement, case)

    scores = dict(base_evaluation["scores"])
    scores["domain_relevance"] = domain_relevance["score"]

    issues = list(base_evaluation["issues"]) + domain_relevance["issues"]
    passed = _is_pass_v2(scores)

    details = dict(base_evaluation["details"])
    details["domain_relevance"] = domain_relevance

    return {
        "scores": scores,
        "pass": passed,
        "issues": issues,
        "details": details,
        "strong_fail": domain_relevance["score"] <= 3,
    }


def score_domain_relevance(statement: str, case: dict) -> dict:
    required_concepts = case.get("required_concepts", [])
    expected_actions = case.get("expected_actions", [])
    forbidden_terms = case.get("forbidden_domain_terms", [])

    concept_result = _score_concept_groups(statement, required_concepts)
    action_result = _score_terms(statement, expected_actions)
    forbidden_hits = _find_hits(statement, forbidden_terms)

    concept_weight = 0.65
    action_weight = 0.35
    score = round(
        10
        * (
            concept_weight * concept_result["coverage"]
            + action_weight * action_result["coverage"]
        )
    )

    if forbidden_hits:
        score -= min(7, len(forbidden_hits) * 2)

    obvious_cross_domain_template = len(forbidden_hits) >= 3
    if obvious_cross_domain_template:
        score = min(score, 3)

    if concept_result["coverage"] < 0.25:
        score = min(score, 4)

    score = _clamp_score(score)
    issues = []
    if concept_result["missing_groups"]:
        issues.append(
            "缺少领域核心概念: "
            + "; ".join("/".join(group) for group in concept_result["missing_groups"])
        )
    if action_result["missing_terms"]:
        issues.append("缺少领域动作: " + ", ".join(action_result["missing_terms"]))
    if forbidden_hits:
        issues.append("命中跨领域污染词: " + ", ".join(forbidden_hits))
    if obvious_cross_domain_template:
        issues.append("疑似使用其他领域模板")

    return {
        "score": score,
        "issues": issues,
        "concept_coverage": concept_result["coverage"],
        "action_coverage": action_result["coverage"],
        "matched_concept_groups": concept_result["matched_groups"],
        "missing_concept_groups": concept_result["missing_groups"],
        "matched_actions": action_result["matched_terms"],
        "missing_actions": action_result["missing_terms"],
        "forbidden_domain_term_hits": forbidden_hits,
        "obvious_cross_domain_template": obvious_cross_domain_template,
    }


def summarize_response_results_v2(case_results: list[dict]) -> dict:
    if not case_results:
        return {
            "total_cases": 0,
            "pass_rate": 0.0,
            "fallback_rate": 0.0,
            "llm_case_count": 0,
            "mock_or_fallback_case_count": 0,
            "average_scores": _empty_average_scores_v2(),
            "split_summary": {},
            "category_summary": {},
        }

    total_cases = len(case_results)
    return {
        "total_cases": total_cases,
        "pass_rate": round(
            sum(1 for item in case_results if item["response_evaluation_v2"]["pass"])
            / total_cases,
            4,
        ),
        "fallback_rate": round(
            sum(1 for item in case_results if item.get("fallback")) / total_cases,
            4,
        ),
        "llm_case_count": sum(
            1
            for item in case_results
            if item.get("agent_mode") == "llm" and not item.get("fallback")
        ),
        "mock_or_fallback_case_count": sum(
            1
            for item in case_results
            if item.get("agent_mode") != "llm" or item.get("fallback")
        ),
        "average_scores": _average_scores(case_results),
        "split_summary": _summarize_by_field(case_results, "split"),
        "category_summary": _summarize_by_field(case_results, "category"),
    }


def _is_pass_v2(scores: dict) -> bool:
    if scores["domain_relevance"] <= 3:
        return False
    return (
        scores["legal_safety"] >= 7
        and scores["empathy"] >= 6
        and scores["action_completeness"] >= 6
        and scores["communication_clarity"] >= 6
        and scores["hallucination_risk"] <= 4
        and scores["domain_relevance"] >= 7
    )


def _score_concept_groups(statement: str, concept_groups: list[list[str]]) -> dict:
    if not concept_groups:
        return {"coverage": 1.0, "matched_groups": [], "missing_groups": []}

    matched_groups = []
    missing_groups = []
    for group in concept_groups:
        normalized_group = [str(term) for term in group if str(term)]
        if any(term in statement for term in normalized_group):
            matched_groups.append(normalized_group)
        else:
            missing_groups.append(normalized_group)

    return {
        "coverage": round(len(matched_groups) / len(concept_groups), 4),
        "matched_groups": matched_groups,
        "missing_groups": missing_groups,
    }


def _score_terms(statement: str, terms: list[str]) -> dict:
    if not terms:
        return {"coverage": 1.0, "matched_terms": [], "missing_terms": []}

    matched_terms = [term for term in terms if term in statement]
    missing_terms = [term for term in terms if term not in statement]
    return {
        "coverage": round(len(matched_terms) / len(terms), 4),
        "matched_terms": matched_terms,
        "missing_terms": missing_terms,
    }


def _find_hits(statement: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in statement]


def _flatten_concept_groups(concept_groups: list[list[str]]) -> list[str]:
    flattened = []
    for group in concept_groups:
        flattened.extend(str(term) for term in group if str(term))
    return flattened


def _average_scores(case_results: list[dict]) -> dict:
    keys = _empty_average_scores_v2().keys()
    return {
        key: round(
            sum(item["response_evaluation_v2"]["scores"][key] for item in case_results)
            / len(case_results),
            2,
        )
        for key in keys
    }


def _summarize_by_field(case_results: list[dict], field: str) -> dict:
    grouped: dict[str, list[dict]] = {}
    for item in case_results:
        grouped.setdefault(str(item.get(field, "unknown")), []).append(item)

    return {
        name: {
            "total_cases": len(items),
            "pass_rate": round(
                sum(1 for item in items if item["response_evaluation_v2"]["pass"])
                / len(items),
                4,
            ),
            "average_domain_relevance": round(
                sum(
                    item["response_evaluation_v2"]["scores"]["domain_relevance"]
                    for item in items
                )
                / len(items),
                2,
            ),
        }
        for name, items in sorted(grouped.items())
    }


def _empty_average_scores_v2() -> dict:
    return {
        "legal_safety": 0.0,
        "empathy": 0.0,
        "action_completeness": 0.0,
        "communication_clarity": 0.0,
        "hallucination_risk": 0.0,
        "domain_relevance": 0.0,
    }


def _clamp_score(score: float) -> int:
    return int(max(0, min(10, round(score))))
