import os

from backend.logger import get_logger
from backend.utils.json_parser import parse_llm_json
from evaluation.judge import judge_client


logger = get_logger(__name__)
JUDGE_FIELDS = (
    "legal_safety",
    "empathy",
    "action_completeness",
    "communication_clarity",
    "hallucination_risk",
    "issues",
)


def get_judge_mode() -> str:
    mode = os.getenv("EVALUATION_JUDGE_MODE", "rule").strip().lower() or "rule"
    if mode not in {"rule", "llm"}:
        raise ValueError("EVALUATION_JUDGE_MODE must be either 'rule' or 'llm'.")
    return mode


def evaluate_with_optional_judge(
    event: str,
    final_statement: str,
    rule_evaluation: dict,
) -> dict:
    mode = get_judge_mode()
    if mode == "rule":
        return _rule_judge_result(rule_evaluation)

    try:
        raw_text = judge_client.call_judge_llm(event, final_statement)
        parsed = parse_llm_json(raw_text)
        if "error_type" in parsed:
            raise ValueError(
                f"JSON parsing failed: {parsed['error_type']} - {parsed['message']}"
            )
        normalized = _normalize_judge_output(parsed)
    except Exception as exc:
        logger.warning(
            "LLM judge failed, fallback to rule evaluation: %s | %s",
            exc.__class__.__name__,
            str(exc),
        )
        fallback = _rule_judge_result(rule_evaluation)
        fallback.update(
            {
                "mode": "llm",
                "fallback": True,
                "fallback_to": "rule",
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        )
        return fallback

    return {
        "mode": "llm",
        "fallback": False,
        "scores": _extract_scores(normalized),
        "issues": normalized["issues"],
        "raw": normalized,
    }


def _rule_judge_result(rule_evaluation: dict) -> dict:
    return {
        "mode": "rule",
        "fallback": False,
        "scores": dict(rule_evaluation["scores"]),
        "issues": list(rule_evaluation.get("issues", [])),
        "raw": None,
    }


def _normalize_judge_output(payload: dict) -> dict:
    missing_fields = [field for field in JUDGE_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing judge fields: {', '.join(missing_fields)}")

    if not isinstance(payload["issues"], list):
        raise TypeError("Judge field 'issues' must be a list.")

    normalized = {
        "legal_safety": _normalize_score(payload["legal_safety"], "legal_safety"),
        "empathy": _normalize_score(payload["empathy"], "empathy"),
        "action_completeness": _normalize_score(
            payload["action_completeness"],
            "action_completeness",
        ),
        "communication_clarity": _normalize_score(
            payload["communication_clarity"],
            "communication_clarity",
        ),
        "hallucination_risk": _normalize_score(
            payload["hallucination_risk"],
            "hallucination_risk",
        ),
        "issues": [str(issue) for issue in payload["issues"]],
    }
    return normalized


def _extract_scores(payload: dict) -> dict:
    return {
        "legal_safety": payload["legal_safety"],
        "empathy": payload["empathy"],
        "action_completeness": payload["action_completeness"],
        "communication_clarity": payload["communication_clarity"],
        "hallucination_risk": payload["hallucination_risk"],
    }


def _normalize_score(value, field_name: str) -> int:
    if not isinstance(value, int | float):
        raise TypeError(f"Judge field '{field_name}' must be a number.")
    return int(max(0, min(10, round(value))))
