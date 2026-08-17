from backend.context import ContextManager
from backend.config import get_config
from backend.llm import LLMClient
from backend.llm.client import record_llm_fallback
from backend.llm.parser import parse_json_response, validate_required_fields
from backend.logger import get_logger
from backend.memory.retriever import retrieve_memories


logger = get_logger(__name__)
AGENT_NAME = "Agent C"
FIRST_DRAFT_REQUIRED_FIELDS = ("statement", "strategy", "tone", "notes")
SECOND_DRAFT_REQUIRED_FIELDS = ("statement", "strategy", "tone", "revisions")
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
            record_llm_fallback(AGENT_NAME, exc)
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
    prompt = _build_writer_prompt(payload, memory_context, context)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, FIRST_DRAFT_REQUIRED_FIELDS)

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


def call_llm(prompt: str) -> str:
    client = LLMClient()
    if client.config.mock_enabled:
        raise RuntimeError("LLM_API_KEY is not configured; fallback to mock writer agent.")
    return client.chat(
        messages=[
            {
                "role": "system",
                "content": "You are CrisisAgent Writer Agent C. Return JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.3,
        agent_name=AGENT_NAME,
    )


def _build_writer_prompt(payload: dict, memory_context: str, context: str) -> str:
    return f"""
你是 CrisisAgent 的策略文案 Agent C，负责为企业危机公关生成第一版对外声明。

输入事件：
{payload["event"]}

舆情分析 sentiment_analysis：
{payload["sentiment_analysis"]}

历史经验 memory_context：
{memory_context}

统一上下文 context:
{context}

写作要求：
- 先表达关注、理解公众担忧或歉意。
- 说明已启动调查/核查/排查，不要提前确认违法事实。
- 如果涉及食品安全、监管、数据隐私等高风险场景，要保留条件式表达。
- 不要使用“一定、绝不、保证”等绝对化承诺。
- 语气应参考 sentiment_analysis.recommended_tone。
- 输出中文。

只输出 JSON，不要输出 markdown，不要输出额外解释。JSON schema：
{{
  "statement": "",
  "strategy": "",
  "tone": "",
  "notes": ""
}}
""".strip()


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
    try:
        config = get_config()
    except Exception as exc:
        logger.warning(
            "%s writer_v2 fallback to mock mode due to config failure: %s | %s",
            AGENT_NAME,
            exc.__class__.__name__,
            str(exc),
        )
        record_llm_fallback(f"{AGENT_NAME} writer_v2", exc)
        return _generate_second_draft_mock(payload)

    if config.agent_mode == "llm":
        try:
            return _generate_second_draft_llm(payload)
        except Exception as exc:
            logger.warning(
                "%s writer_v2 fallback to mock mode due to llm failure: %s | %s",
                AGENT_NAME,
                exc.__class__.__name__,
                str(exc),
            )
            record_llm_fallback(f"{AGENT_NAME} writer_v2", exc)

    return _generate_second_draft_mock(payload)


def _generate_second_draft_llm(payload: dict) -> dict:
    prompt = _build_writer_v2_prompt(payload)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, SECOND_DRAFT_REQUIRED_FIELDS)

    validated = _validate_second_draft_output(parsed)
    logger.info("%s writer_v2 parsed llm result: %s", AGENT_NAME, validated)
    normalized_output = _normalize_second_draft_output(
        {
            "statement": validated["statement"],
            "strategy": validated["strategy"],
            "tone": validated["tone"],
            "revisions": validated["revisions"],
            "review_summary": validated.get("review_summary", {}),
        },
        payload,
    )
    logger.info("%s writer_v2 normalized output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def _generate_second_draft_mock(payload: dict) -> dict:
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

    return _normalize_second_draft_output(
        {
            "statement": statement,
            "strategy": "优先落实 Legal Agent 整合出的修订任务，再兼顾红队反馈中的高价值舆情建议。",
            "tone": "先共情、再回应行动、避免抢先定性",
            "revisions": [
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
        },
        payload,
    )


def _build_writer_v2_prompt(payload: dict) -> str:
    draft = _extract_first_statement(payload)
    return f"""
{_writer_v2_stability_requirements()}

你是 CrisisAgent 的 Writer_v2 Revision Agent，角色是危机公关高级文案专家。

输入事件 event：
{payload.get("event", "")}

原始声明 draft：
{draft}

红队攻击意见 redteam_review：
{payload.get("redteam_review", {})}

法律审核建议 legal_review：
{payload.get("legal_review", {})}

任务：
根据原始声明、红队攻击意见和法律审核建议，生成第二版公开声明。

写作要求：
- 保留事实谨慎，不提前确认事实，不提前定责。
- 增加核查行动、整改方向、监管配合和后续更新安排。
- 增强公众沟通，回应消费者/用户/公众担忧。
- 吸收 redteam_review.issues / suggestions。
- 优先执行 legal_review.revision_advice 和 legal_review.integrated_revision_tasks。
- 不使用“一定、绝不、保证”等绝对化承诺。
- 输出中文。

只输出 JSON，不要输出 markdown，不要输出额外解释。JSON schema：
{{
  "statement": "",
  "strategy": "",
  "tone": "",
  "revisions": []
}}
""".strip()


def _writer_v2_stability_requirements() -> str:
    return """
Writer_v2 评测稳定性硬性要求：
- statement 必须包含明确共情表达，例如“对受到影响的消费者表示歉意”“我们高度重视公众关切”“理解消费者的担忧”。
- statement 必须至少包含“调查”“核查”“排查”三个词中的一个，说明已经启动事实核验行动。
- statement 必须包含“配合监管部门”或“接受监督”，说明监管沟通安排。
- statement 必须包含至少一种后续措施，例如“整改”“召回”“第三方审计”“信息公开”“持续更新”。
- statement 必须使用条件式、谨慎表达，不能在调查完成前确认违法事实或直接定责。
- statement 禁止使用“一定”“绝不”“保证”“永远”等绝对化承诺。
- statement 禁止推卸责任，不能暗示责任在消费者、媒体或第三方。
- statement 必须输出中文，语气应先共情、再说明行动、最后给出后续安排。

输出前自检：
- 如果 statement 缺少歉意/关切表达，请补充。
- 如果 statement 缺少调查/核查/排查，请补充。
- 如果 statement 缺少配合监管部门/接受监督，请补充。
- 如果 statement 缺少整改/召回/第三方审计/信息公开/持续更新，请补充。
- 如果 statement 包含提前定责或绝对化承诺，请改写。
""".strip()


def _validate_second_draft_output(payload: dict) -> dict:
    missing_fields = [field for field in SECOND_DRAFT_REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    for field in ("statement", "strategy", "tone"):
        if not isinstance(payload[field], str):
            raise TypeError(f"Field '{field}' must be a string.")
    if not isinstance(payload["revisions"], list):
        raise TypeError("Field 'revisions' must be a list.")
    if not all(isinstance(item, str) for item in payload["revisions"]):
        raise TypeError("All items in 'revisions' must be strings.")
    if "review_summary" in payload and not isinstance(payload["review_summary"], (dict, str)):
        raise TypeError("Field 'review_summary' must be an object or string when provided.")

    return payload


def _normalize_second_draft_output(payload: dict, original_payload: dict) -> dict:
    revisions = [str(item) for item in payload["revisions"]]
    review_summary = payload.get("review_summary") or _build_writer_v2_review_summary(
        original_payload,
        revisions,
    )
    return {
        "statement": str(payload["statement"]),
        "strategy": str(payload["strategy"]),
        "tone": str(payload["tone"]),
        "revisions": revisions,
        "revisions_from_v1": revisions,
        "review_summary": review_summary,
    }


def _build_writer_v2_review_summary(payload: dict, revisions: list[str]) -> dict:
    redteam_review = payload.get("redteam_review", {})
    legal_review = payload.get("legal_review", {})
    return {
        "redteam_focus": redteam_review.get("attack_summary", ""),
        "legal_focus": legal_review.get("review_summary", ""),
        "integrated_revision_tasks": legal_review.get("integrated_revision_tasks", []),
        "public_opinion_suggestions": legal_review.get("public_opinion_suggestions", []),
        "first_draft_excerpt": _extract_first_statement(payload)[:80],
        "revisions": revisions,
    }


def _extract_first_statement(payload: dict) -> str:
    if isinstance(payload.get("first_draft"), dict):
        return str(payload["first_draft"].get("statement", ""))
    return str(payload.get("draft", ""))
