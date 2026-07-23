from backend.config import get_config
from backend.llm_client import call_llm
from backend.logger import get_logger
from backend.prompt_loader import load_prompt
from backend.rag.retriever import retrieve
from backend.utils.json_parser import parse_llm_json


logger = get_logger(__name__)
AGENT_NAME = "Agent B"
_LAST_RAG_INFO = {
    "enabled": False,
    "hit": False,
    "sources": [],
    "count": 0,
}
REQUIRED_FIELDS = (
    "legal_risks",
    "safe_points",
    "revision_advice",
    "public_opinion_suggestions",
    "integrated_revision_tasks",
)


def run(payload: dict) -> dict:
    config = get_config()

    if config.agent_mode == "llm":
        _set_rag_info(enabled=True, hit=False, sources=[])
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

    _set_rag_info(enabled=False, hit=False, sources=[])
    return _run_mock(payload)


def get_last_rag_info() -> dict:
    return {
        "enabled": _LAST_RAG_INFO["enabled"],
        "hit": _LAST_RAG_INFO["hit"],
        "sources": list(_LAST_RAG_INFO["sources"]),
        "count": _LAST_RAG_INFO["count"],
    }


def _set_rag_info(enabled: bool, hit: bool, sources: list[str]) -> None:
    _LAST_RAG_INFO.update(
        {
            "enabled": enabled,
            "hit": hit,
            "sources": sources,
            "count": len(sources),
        }
    )


def _run_mock(payload: dict) -> dict:
    draft = payload["draft"]
    redteam_review = payload["redteam_review"]
    redteam_suggestions = redteam_review.get("suggestions", [])
    legal_risks = []

    if "确认" in draft or "确实" in draft:
        legal_risks.append("存在在调查完成前直接确认事实的风险。")
    if "一定" in draft or "绝不" in draft:
        legal_risks.append("存在绝对化承诺风险。")
    if "负责到底" in draft:
        legal_risks.append("责任表达过满，可能引发额外法律解释空间。")

    public_opinion_suggestions = []
    for suggestion in redteam_suggestions:
        if "公众" in suggestion or "消费者" in suggestion or "担忧" in suggestion:
            public_opinion_suggestions.append(suggestion)
        elif "核查" in suggestion or "处理承诺" in suggestion:
            public_opinion_suggestions.append(suggestion)

    if not public_opinion_suggestions and redteam_suggestions:
        public_opinion_suggestions = redteam_suggestions[:2]

    integrated_revision_tasks = [
        "保留对公众担忧和消费者不安的明确回应，避免只做程序性表态。",
        "补充核查范围、后续整改和处理动作，但不要提前认定全部事实。",
        "涉及责任时使用条件式表达，例如以核查结果为前提依法依规处理。",
        "避免绝对化承诺，同时让回应看起来不是模板化推责。",
    ]

    return _normalize_output(
        {
            "legal_risks": legal_risks or ["未发现明显高风险承认性表述，但仍需保持条件式措辞。"],
            "safe_points": [
                "使用了核查、配合监管等相对稳妥表达。",
                "未直接下结论认定全部事实成立。",
            ],
            "revision_advice": [
                "保留对事件的重视与歉意，但避免提前定责。",
                "如需提及责任，建议加上核查结果前提。",
                "避免使用绝对化保证性语言。",
            ],
            "public_opinion_suggestions": public_opinion_suggestions,
            "integrated_revision_tasks": integrated_revision_tasks,
            "legal_safety_score_hint": 8,
            "review_summary": "当前草稿整体偏稳妥。结合红队反馈后，建议同时增强公众沟通力度，并继续坚持调查中、配合监管、依法处理的表达方式。",
        }
    )


def _run_llm(payload: dict) -> dict:
    legal_context = _retrieve_legal_context(payload)
    prompt = load_prompt(
        "legal_agent",
        {
            "event": payload["event"],
            "draft": payload["draft"],
            "redteam_review": payload["redteam_review"],
            "legal_context": legal_context,
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
        "legal_risks": validated["legal_risks"],
        "safe_points": validated["safe_points"],
        "revision_advice": validated["revision_advice"],
        "public_opinion_suggestions": validated["public_opinion_suggestions"],
        "integrated_revision_tasks": validated["integrated_revision_tasks"],
        "legal_safety_score_hint": validated.get("legal_safety_score_hint", 8),
        "review_summary": validated.get(
            "review_summary",
            "当前草稿整体偏稳妥，建议继续坚持调查中、配合监管、依法处理的表达方式。",
        ),
    }
    normalized_output = _normalize_output(mapped_output)
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def _retrieve_legal_context(payload: dict) -> str:
    query = _build_retrieval_query(payload)
    try:
        retrieval_result = retrieve(query, top_k=3)
    except Exception as exc:
        logger.warning(
            "%s RAG retrieval failed: %s | %s",
            AGENT_NAME,
            exc.__class__.__name__,
            str(exc),
        )
        _set_rag_info(enabled=True, hit=False, sources=[])
        return ""

    sources = retrieval_result.get("sources", [])
    source_names = []
    for source in sources:
        if not isinstance(source, dict) or not source.get("source"):
            continue
        source_name = str(source["source"])
        if source_name not in source_names:
            source_names.append(source_name)
    _set_rag_info(enabled=True, hit=bool(source_names), sources=source_names)
    logger.info("%s RAG retrieved %s sources: %s", AGENT_NAME, len(sources), sources)
    return retrieval_result.get("context", "")


def _build_retrieval_query(payload: dict) -> str:
    redteam_review = payload["redteam_review"]
    return "\n".join(
        [
            f"事件：{payload['event']}",
            f"声明草稿：{payload['draft']}",
            f"红队问题：{redteam_review.get('issues', [])}",
            f"红队建议：{redteam_review.get('suggestions', [])}",
        ]
    )


def _validate_output(payload: dict) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    for field in REQUIRED_FIELDS:
        if not isinstance(payload[field], list):
            raise TypeError(f"Field '{field}' must be a list.")
        if not all(isinstance(item, str) for item in payload[field]):
            raise TypeError(f"All items in '{field}' must be strings.")

    if "legal_safety_score_hint" in payload and not isinstance(payload["legal_safety_score_hint"], int):
        raise TypeError("Field 'legal_safety_score_hint' must be an integer when provided.")
    if "review_summary" in payload and not isinstance(payload["review_summary"], str):
        raise TypeError("Field 'review_summary' must be a string when provided.")

    return payload


def _normalize_output(payload: dict) -> dict:
    return {
        "legal_risks": [str(item) for item in payload["legal_risks"]],
        "safe_points": [str(item) for item in payload["safe_points"]],
        "revision_advice": [str(item) for item in payload["revision_advice"]],
        "public_opinion_suggestions": [str(item) for item in payload["public_opinion_suggestions"]],
        "integrated_revision_tasks": [str(item) for item in payload["integrated_revision_tasks"]],
        "legal_safety_score_hint": int(payload.get("legal_safety_score_hint", 8)),
        "review_summary": str(
            payload.get(
                "review_summary",
                "当前草稿整体偏稳妥，建议继续坚持调查中、配合监管、依法处理的表达方式。",
            )
        ),
    }
