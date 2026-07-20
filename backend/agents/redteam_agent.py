from backend.config import get_config
from backend.llm_client import call_llm
from backend.logger import get_logger
from backend.prompt_loader import load_prompt
from backend.utils.json_parser import parse_llm_json


logger = get_logger(__name__)
AGENT_NAME = "Agent D"
REQUIRED_FIELDS = ("issues", "attack_summary", "suggestions")


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
    draft = payload["draft"]
    issues = []

    if "事实进一步核实前" in draft:
        issues.append("可能被解读为企业在拖延表态。")
    if "歉意" in draft and "消费者" in draft:
        pass
    else:
        issues.append("对受影响对象的共情表达不够具体。")
    if "整改" not in draft and "排查" in draft:
        issues.append("只提排查，未说明后续整改与问责动作。")

    suggestions = [
        "更明确表达对消费者担忧的理解。",
        "补充核查范围和后续处理承诺。",
        "避免让公众感觉企业只是程序性回应。",
    ]

    return _normalize_output(
        {
            "issues": issues or ["整体回应稳健，但行动承诺还可更具体。"],
            "attack_summary": "公众和媒体可能质疑回应过于模板化，且对整改与责任表述不够有力。",
            "suggestions": suggestions,
        }
    )


def _run_llm(payload: dict) -> dict:
    prompt = load_prompt(
        "redteam_agent",
        {
            "event": payload["event"],
            "draft": payload["draft"],
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
        "issues": validated["issues"],
        "attack_summary": validated["attack_summary"],
        "suggestions": validated["suggestions"],
    }
    normalized_output = _normalize_output(mapped_output)
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def _validate_output(payload: dict) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    if not isinstance(payload["issues"], list):
        raise TypeError("Field 'issues' must be a list.")
    if not all(isinstance(item, str) for item in payload["issues"]):
        raise TypeError("All items in 'issues' must be strings.")
    if not isinstance(payload["attack_summary"], str):
        raise TypeError("Field 'attack_summary' must be a string.")
    if not isinstance(payload["suggestions"], list):
        raise TypeError("Field 'suggestions' must be a list.")
    if not all(isinstance(item, str) for item in payload["suggestions"]):
        raise TypeError("All items in 'suggestions' must be strings.")

    return payload


def _normalize_output(payload: dict) -> dict:
    return {
        "issues": [str(item) for item in payload["issues"]],
        "attack_summary": str(payload["attack_summary"]),
        "suggestions": [str(item) for item in payload["suggestions"]],
    }
