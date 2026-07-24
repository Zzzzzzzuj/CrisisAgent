from backend.context import ContextManager
from backend.config import get_config
from backend.llm_client import call_llm
from backend.logger import get_logger
from backend.memory.retriever import retrieve_memories
from backend.prompt_loader import load_prompt
from backend.utils.json_parser import parse_llm_json


logger = get_logger(__name__)
AGENT_NAME = "Agent C"
FIRST_DRAFT_REQUIRED_FIELDS = ("statement", "strategy", "tone", "notes")
CONTEXT_MAX_TOKENS = 300
_LAST_MEMORY_INFO = {
    "enabled": False,
    "hit": False,
    "categories": [],
    "memory_ids": [],
}
_LAST_CONTEXT_INFO = {
    "before_tokens": 0,
    "after_tokens": 0,
    "sources": [],
}


def run(payload: dict) -> dict:
    config = get_config()

    if config.agent_mode == "llm":
        _set_memory_info(enabled=True, hit=False, memories=[])
        _set_context_info(before_tokens=0, after_tokens=0, sources=[])
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

    _set_memory_info(enabled=False, hit=False, memories=[])
    _set_context_info(before_tokens=0, after_tokens=0, sources=[])
    return _run_mock(payload)


def generate_first_draft(payload: dict) -> dict:
    return run(payload)


def get_last_memory_info() -> dict:
    return {
        "enabled": _LAST_MEMORY_INFO["enabled"],
        "hit": _LAST_MEMORY_INFO["hit"],
        "categories": list(_LAST_MEMORY_INFO["categories"]),
        "memory_ids": list(_LAST_MEMORY_INFO["memory_ids"]),
    }


def get_last_context_info() -> dict:
    return {
        "before_tokens": _LAST_CONTEXT_INFO["before_tokens"],
        "after_tokens": _LAST_CONTEXT_INFO["after_tokens"],
        "sources": list(_LAST_CONTEXT_INFO["sources"]),
    }


def _set_context_info(before_tokens: int, after_tokens: int, sources: list[str]) -> None:
    _LAST_CONTEXT_INFO.update(
        {
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "sources": list(sources),
        }
    )


def _set_memory_info(enabled: bool, hit: bool, memories: list[dict]) -> None:
    categories = []
    memory_ids = []
    for memory in memories:
        category = memory.get("category")
        memory_id = memory.get("memory_id")
        if category and category not in categories:
            categories.append(category)
        if memory_id and memory_id not in memory_ids:
            memory_ids.append(memory_id)

    _LAST_MEMORY_INFO.update(
        {
            "enabled": enabled,
            "hit": hit,
            "categories": categories,
            "memory_ids": memory_ids,
        }
    )


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
    memory_context = _retrieve_memory_context(payload)
    context = _build_context(payload, memory_context)
    prompt = load_prompt(
        "writer_agent",
        {
            "event": payload["event"],
            "sentiment_analysis": payload["sentiment_analysis"],
            "redteam_review": "",
            "legal_review": "",
            "memory_context": memory_context,
            "context": context,
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


def _build_context(payload: dict, memory_context: str) -> str:
    manager = ContextManager()
    manager.add_context(
        source="event",
        content=str(payload.get("event", "")),
        priority=100,
    )
    manager.add_context(
        source="sentiment_analysis",
        content=str(payload.get("sentiment_analysis", {})),
        priority=80,
    )
    if memory_context:
        manager.add_context(
            source="memory_context",
            content=memory_context,
            priority=60,
        )

    sorted_items = manager.sort_by_priority()
    before_tokens = sum(item.token_size for item in sorted_items)
    context = manager.build_context(max_tokens=CONTEXT_MAX_TOKENS)
    sources = [item.source for item in sorted_items if f"[{item.source}]" in context]
    after_tokens = sum(item.token_size for item in sorted_items if item.source in sources)
    _set_context_info(before_tokens=before_tokens, after_tokens=after_tokens, sources=sources)
    return context


def _retrieve_memory_context(payload: dict) -> str:
    query = _build_memory_query(payload)
    try:
        retrieval_result = retrieve_memories(query, top_k=3)
    except Exception as exc:
        logger.warning(
            "%s memory retrieval failed: %s | %s",
            AGENT_NAME,
            exc.__class__.__name__,
            str(exc),
        )
        _set_memory_info(enabled=True, hit=False, memories=[])
        return ""

    memories = retrieval_result.get("memories", [])
    _set_memory_info(enabled=True, hit=bool(memories), memories=memories)
    return retrieval_result.get("context", "")


def _build_memory_query(payload: dict) -> str:
    sentiment = payload.get("sentiment_analysis", {})
    return "\n".join(
        [
            f"event: {payload.get('event', '')}",
            f"risk_level: {sentiment.get('risk_level', '')}",
            f"public_emotion: {sentiment.get('public_emotion', '')}",
            f"keywords: {sentiment.get('keywords', [])}",
        ]
    )


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
