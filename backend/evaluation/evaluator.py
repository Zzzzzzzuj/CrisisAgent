from backend.evaluation.metrics import score_empathy, score_legal_safety, score_robustness


LEGAL_SAFETY_THRESHOLD = 7
EMPATHY_THRESHOLD = 6
ROBUSTNESS_THRESHOLD = 6


def evaluate_agent_run(
    event: str,
    results: dict,
    final_statement: str,
    agent_trace: list[dict],
) -> dict:
    legal = score_legal_safety(final_statement)
    empathy = score_empathy(final_statement)
    robustness = score_robustness(results, final_statement, agent_trace)

    issues = _dedupe(legal["issues"] + empathy["issues"] + robustness["issues"])
    suggestions = _dedupe(
        legal["suggestions"] + empathy["suggestions"] + robustness["suggestions"]
    )

    return {
        "legal_safety_score": legal["score"],
        "empathy_score": empathy["score"],
        "robustness_score": robustness["score"],
        "passed": _is_passed(legal["score"], empathy["score"], robustness["score"]),
        "issues": issues,
        "suggestions": suggestions,
    }


def _is_passed(legal_safety_score: int, empathy_score: int, robustness_score: int) -> bool:
    return (
        legal_safety_score >= LEGAL_SAFETY_THRESHOLD
        and empathy_score >= EMPATHY_THRESHOLD
        and robustness_score >= ROBUSTNESS_THRESHOLD
    )


def _dedupe(items: list[str]) -> list[str]:
    deduped = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped
