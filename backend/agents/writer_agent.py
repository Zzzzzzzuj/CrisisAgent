from backend.config import get_config
from backend.llm_client import call_llm
from backend.logger import get_logger
from backend.prompt_loader import load_prompt
from backend.utils.json_parser import parse_llm_json


logger = get_logger(__name__)
AGENT_NAME = "Agent C"
FIRST_DRAFT_REQUIRED_FIELDS = ("statement", "strategy", "tone", "notes")


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


def generate_first_draft(payload: dict) -> dict:
    return run(payload)


def _run_mock(payload: dict) -> dict:
    event = payload["event"]
    sentiment = payload["sentiment_analysis"]

    statement = (
        "我们已关注到关于本次事件的网络反馈，对由此引发的公众担忧深表重视。"
        "公司已第一时间启动内部核查程序，对涉及批次、采购与生产环节展开全面排查。"
        "在事实进一步核实前，我们将及时同步调查进展，并积极配合相关监管要求。"
        "对于事件给消费者带来的不安，我们表示诚挚歉意。"
    )

    return _normalize_first_draft_output(
        {
            "statement": statement,
            "strategy": "快速回应，先表达重视与歉意，再说明核查与配合监管。",
            "tone": sentiment["recommended_tone"],
            "notes": f"基于事件“{event}”生成第一版回应。",
        }
    )


def _run_llm(payload: dict) -> dict:
    prompt = load_prompt(
        "writer_agent",
        {
            "event": payload["event"],
            "sentiment_analysis": payload["sentiment_analysis"],
            "redteam_review": "",
            "legal_review": "",
        },
    )
    raw_text = call_llm(prompt)
    parsed = parse_llm_json(raw_text)

    if "error_type" in parsed:
        raise ValueError(
            f"JSON parsing failed: {parsed['error_type']} - {parsed['message']}"
        )

    validated = _validate_first_draft_output(parsed)
    logger.info("%s parsed llm result: %s", AGENT_NAME, validated)

    mapped_output = {
        "statement": validated["statement"],
        "strategy": validated["strategy"],
        "tone": validated["tone"],
        "notes": validated["notes"],
    }
    normalized_output = _normalize_first_draft_output(mapped_output)
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def _validate_first_draft_output(payload: dict) -> dict:
    missing_fields = [field for field in FIRST_DRAFT_REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    for field in FIRST_DRAFT_REQUIRED_FIELDS:
        if not isinstance(payload[field], str):
            raise TypeError(f"Field '{field}' must be a string.")

    return payload


def _normalize_first_draft_output(payload: dict) -> dict:
    return {
        "statement": str(payload["statement"]),
        "strategy": str(payload["strategy"]),
        "tone": str(payload["tone"]),
        "notes": str(payload["notes"]),
    }


def generate_second_draft(payload: dict) -> dict:
    first_statement = payload["first_draft"]["statement"]
    redteam_review = payload["redteam_review"]
    legal_review = payload["legal_review"]
    integrated_tasks = legal_review.get("integrated_revision_tasks", [])
    public_opinion_suggestions = legal_review.get("public_opinion_suggestions", [])

    statement = (
        "我们已注意到关于此事的相关传播内容，并充分理解公众对此产生的担忧与关切。"
        "公司已立即启动专项核查，对相关原料、生产流程、仓储管理及涉事批次进行全面排查。"
        "如核查发现任何违反食品安全要求的情形，我们将严肃处理并依法依规承担相应责任。"
        "目前，我们正同步配合监管部门开展调查，并将根据核查进展持续对外说明。"
        "对于给消费者和合作伙伴带来的不安，我们再次表示歉意。"
    )

    return {
        "statement": statement,
        "strategy": "优先落实 Legal Agent 整合出的修订任务，再兼顾红队反馈中的高价值舆情建议。",
        "revisions_from_v1": [
            "强化对公众担忧的回应",
            "补充专项核查范围",
            "加入依法依规承担责任的条件式表述",
            "根据红队与合规意见弱化可能被视为推责的措辞",
        ],
        "review_summary": {
            "redteam_focus": redteam_review["attack_summary"],
            "legal_focus": legal_review["review_summary"],
            "integrated_revision_tasks": integrated_tasks,
            "public_opinion_suggestions": public_opinion_suggestions,
            "first_draft_excerpt": first_statement[:80],
        },
    }
