from backend.config import get_config
from backend.llm_client import call_llm
from backend.logger import get_logger
from backend.prompt_loader import load_prompt
from backend.utils.json_parser import parse_llm_json


logger = get_logger(__name__)
AGENT_NAME = "Agent A"
REQUIRED_FIELDS = (
    "risk_level",
    "public_emotion",
    "keywords",
    "recommended_tone",
    "analysis_summary",
)


def run(event: str) -> dict:
    config = get_config()

    if config.agent_mode == "llm":
        try:
            return _run_llm(event)
        except Exception as exc:
            logger.warning(
                "%s fallback to mock mode due to llm failure: %s | %s",
                AGENT_NAME,
                exc.__class__.__name__,
                str(exc),
            )

    return _run_mock(event)


def _run_mock(event: str) -> dict:
    keywords = []
    if "过期" in event:
        keywords.append("过期原料")
    if "偷拍视频" in event or "视频" in event:
        keywords.append("传播视频")
    if "监管" in event:
        keywords.append("监管介入")
    if "网友" in event:
        keywords.append("公众愤怒")

    risk_level = "high" if any(word in event for word in ["过期", "监管", "爆", "曝光"]) else "medium"
    public_emotion = "angry" if any(word in event for word in ["要求", "曝光", "愤怒", "偷拍视频"]) else "concerned"
    recommended_tone = "先共情、再回应行动、避免抢先定性"

    return _normalize_output(
        {
            "risk_level": risk_level,
            "public_emotion": public_emotion,
            "keywords": keywords or ["舆情扩散"],
            "recommended_tone": recommended_tone,
            "analysis_summary": "当前事件具有较强传播性和监管敏感性，回应应强调重视、调查、整改与配合监管。",
        }
    )


def _run_llm(event: str) -> dict:
    prompt = load_prompt("sentiment_agent", {"event": event})
    raw_text = call_llm(prompt)
    parsed = parse_llm_json(raw_text)

    if "error_type" in parsed:
        raise ValueError(
            f"JSON parsing failed: {parsed['error_type']} - {parsed['message']}"
        )

    validated = _validate_llm_output(parsed)
    logger.info("%s parsed llm result: %s", AGENT_NAME, validated)
    mapped_output = {
        "risk_level": validated["risk_level"],
        "public_emotion": validated["public_emotion"],
        "keywords": validated["keywords"],
        "recommended_tone": validated["recommended_tone"],
        "analysis_summary": validated["analysis_summary"],
    }
    normalized_output = _normalize_output(mapped_output)
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    logger.debug("%s llm output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def _validate_llm_output(payload: dict) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    if not isinstance(payload["risk_level"], str):
        raise TypeError("Field 'risk_level' must be a string.")
    if not isinstance(payload["public_emotion"], str):
        raise TypeError("Field 'public_emotion' must be a string.")
    if not isinstance(payload["keywords"], list):
        raise TypeError("Field 'keywords' must be a list.")
    if not all(isinstance(item, str) for item in payload["keywords"]):
        raise TypeError("All items in 'keywords' must be strings.")
    if not isinstance(payload["recommended_tone"], str):
        raise TypeError("Field 'recommended_tone' must be a string.")
    if not isinstance(payload["analysis_summary"], str):
        raise TypeError("Field 'analysis_summary' must be a string.")

    return payload


def _normalize_output(payload: dict) -> dict:
    return {
        "risk_level": str(payload["risk_level"]),
        "public_emotion": str(payload["public_emotion"]),
        "keywords": [str(item) for item in payload["keywords"]],
        "recommended_tone": str(payload["recommended_tone"]),
        "analysis_summary": str(payload["analysis_summary"]),
    }
