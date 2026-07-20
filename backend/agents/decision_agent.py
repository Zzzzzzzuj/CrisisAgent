from backend.config import get_config
from backend.llm_client import call_llm
from backend.logger import get_logger
from backend.prompt_loader import load_prompt
from backend.utils.json_parser import parse_llm_json


logger = get_logger(__name__)
AGENT_NAME = "Agent E"
REQUIRED_FIELDS = ("final_statement", "scores", "decision_summary")
REQUIRED_SCORE_FIELDS = ("legal_safety", "empathy", "robustness")


def run(payload: dict) -> dict:
    config = get_config()

    if config.agent_mode == "llm":
        try:
            return _run_llm(payload)
        except Exception as exc:
            logger.warning(
                "%s fallback to mock mode due to llm failure: %s | %s",
                AGENT_NAME,
                exc.__class__.__name__,
                str(exc),
            )

    return _run_mock(payload)


def _run_mock(payload: dict) -> dict:
    statement = payload["second_draft"]
    redteam_review = payload["redteam_review"]
    legal_review = payload["legal_review"]
    sentiment_analysis = payload["sentiment_analysis"]

    legal_safety = max(0, min(10, legal_review.get("legal_safety_score_hint", 7)))
    empathy = 8 if "担忧" in statement and "歉意" in statement else 6
    robustness = (
        8
        if len(redteam_review.get("issues", [])) <= 3
        and sentiment_analysis["risk_level"] == "high"
        else 7
    )

    return _normalize_output(
        {
            "final_statement": statement,
            "scores": {
                "legal_safety": legal_safety,
                "empathy": empathy,
                "robustness": robustness,
            },
            "decision_summary": "第二版在共情、行动说明和法律稳妥性之间取得了更平衡的结果，可作为当前对外回应底稿。",
        }
    )


def _run_llm(payload: dict) -> dict:
    prompt = load_prompt(
        "decision_agent",
        {
            "event": payload["event"],
            "second_draft": payload["second_draft"],
            "sentiment_analysis": payload["sentiment_analysis"],
            "redteam_review": payload["redteam_review"],
            "legal_review": payload["legal_review"],
        },
    )
    raw_text = call_llm(prompt)
    parsed = parse_llm_json(raw_text)

    if "error_type" in parsed:
        raise ValueError(
            f"JSON parsing failed: {parsed['error_type']} - {parsed['message']}"
        )

    validated = _validate_output(parsed)
    logger.info("%s parsed llm result: %s", AGENT_NAME, validated)

    mapped_output = {
        "final_statement": validated["final_statement"],
        "scores": {
            "legal_safety": validated["scores"]["legal_safety"],
            "empathy": validated["scores"]["empathy"],
            "robustness": validated["scores"]["robustness"],
        },
        "decision_summary": validated["decision_summary"],
    }
    normalized_output = _normalize_output(mapped_output)
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def _validate_output(payload: dict) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    if not isinstance(payload["final_statement"], str):
        raise TypeError("Field 'final_statement' must be a string.")
    if not isinstance(payload["scores"], dict):
        raise TypeError("Field 'scores' must be an object.")
    if not isinstance(payload["decision_summary"], str):
        raise TypeError("Field 'decision_summary' must be a string.")

    missing_score_fields = [
        field for field in REQUIRED_SCORE_FIELDS if field not in payload["scores"]
    ]
    if missing_score_fields:
        raise ValueError(
            f"Missing required score fields: {', '.join(missing_score_fields)}"
        )

    for field in REQUIRED_SCORE_FIELDS:
        if not isinstance(payload["scores"][field], int):
            raise TypeError(f"Score field '{field}' must be an integer.")

    return payload


def _normalize_output(payload: dict) -> dict:
    return {
        "final_statement": str(payload["final_statement"]),
        "scores": {
            "legal_safety": max(0, min(10, int(payload["scores"]["legal_safety"]))),
            "empathy": max(0, min(10, int(payload["scores"]["empathy"]))),
            "robustness": max(0, min(10, int(payload["scores"]["robustness"]))),
        },
        "decision_summary": str(payload["decision_summary"]),
    }
