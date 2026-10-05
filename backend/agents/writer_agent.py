from backend.context import ContextManager
from backend.config import get_config
from backend.llm import LLMClient
from backend.llm.client import record_llm_fallback
from backend.llm.parser import parse_json_response, validate_required_fields
from backend.logger import get_logger
from backend.memory.retriever import retrieve_memories
from backend.harness.prompt_policy import writer_v2_policy_overlay


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
                "%s fallback to mock mode due to llm failure: %s",
                AGENT_NAME,
                exc.__class__.__name__,
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
        "对于尚未确认的信息，我们暂不作确定性判断。"
        "后续如有核查进展，我们将及时更新相关情况。"
        "对于事件给相关群体带来的不安，我们表示歉意。"
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
    runtime_pack = payload.get("context_pack") or {}
    memory_context = runtime_pack.get("rendered_context", "") if runtime_pack else _retrieve_memory_context(payload)
    context = _build_context(payload, memory_context)
    prompt = _build_writer_prompt(payload, memory_context, context)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, FIRST_DRAFT_REQUIRED_FIELDS)

    validated = _validate_first_draft_output(parsed)
    logger.info("%s parsed llm result fields=%s", AGENT_NAME, len(validated))

    mapped_output = {
        "statement": validated["statement"],
        "strategy": validated["strategy"],
        "tone": validated["tone"],
        "notes": validated["notes"],
    }
    normalized_output = _normalize_first_draft_output(mapped_output)
    logger.info("%s normalized output statement_chars=%s", AGENT_NAME, len(normalized_output["statement"]))
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
    # Runtime ContextPack already contains historical memories; do not repeat it as legacy memory.
    runtime_pack = payload.get("context_pack") or {}
    if runtime_pack:
        memory_context = ""
    pack_text = payload.get("context_pack_text") or runtime_pack.get("rendered_context", "")
    return f"""
你是 CrisisAgent 的策略文案 Agent C，负责为企业危机公关生成第一版对外声明。

输入事件：
{payload["event"]}

舆情分析 sentiment_analysis：
{payload["sentiment_analysis"]}

历史经验 memory_context：
{memory_context}

本轮 ContextPack（按 Writer 角色裁剪）：
{pack_text}

统一上下文 context:
{context}

写作要求：
- 先表达关注、理解公众担忧或歉意。
- 说明当前输入明确支持的事实状态；输入未证明行动已经发生时，使用建议性或条件性措辞，不得写成已启动、正在执行或已完成。
- 可以建议立即调查、核查或排查，但建议动作不代表当前企业已经执行该动作。
- 如果涉及食品安全、监管、数据隐私等高风险场景，要保留条件式表达。
- 不要使用“一定、绝不、保证”等绝对化承诺。
- 语气应参考 sentiment_analysis.recommended_tone。
- 历史经验仅供参考处理策略；不得将历史案例中的事实或已执行动作写成当前 Case 的事实。
- 人工提供的信息必须保留“据人工提供/尚待独立核实”等来源边界，不得改写成独立核实结论。
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
    runtime_pack = payload.get("context_pack") or {}
    if runtime_pack:
        pack_text = payload.get("context_pack_text") or runtime_pack.get("rendered_context", "")
        item = ContextManager().add_context(source="context_pack", content=pack_text, priority=100)
        _set_context_info(before_tokens=item.token_size, after_tokens=item.token_size,
                          sources=["context_pack"] if pack_text else [])
        return ""
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
            "%s memory retrieval failed: %s",
            AGENT_NAME,
            exc.__class__.__name__,
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
            "%s writer_v2 fallback to mock mode due to config failure: %s",
            AGENT_NAME,
            exc.__class__.__name__,
        )
        record_llm_fallback(f"{AGENT_NAME} writer_v2", exc)
        return _generate_second_draft_mock(payload)

    if config.agent_mode == "llm":
        try:
            return _generate_second_draft_llm(payload)
        except Exception as exc:
            logger.warning(
                "%s writer_v2 fallback to mock mode due to llm failure: %s",
                AGENT_NAME,
                exc.__class__.__name__,
            )
            record_llm_fallback(f"{AGENT_NAME} writer_v2", exc)

    return _generate_second_draft_mock(payload)


def _generate_second_draft_llm(payload: dict) -> dict:
    prompt = _build_writer_v2_prompt(payload)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, SECOND_DRAFT_REQUIRED_FIELDS)

    validated = _validate_second_draft_output(parsed)
    logger.info("%s writer_v2 parsed llm result fields=%s", AGENT_NAME, len(validated))
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
    logger.info("%s writer_v2 normalized output statement_chars=%s", AGENT_NAME, len(normalized_output["statement"]))
    return normalized_output


def _generate_second_draft_mock(payload: dict) -> dict:
    first_statement = payload["first_draft"]["statement"]
    redteam_review = payload["redteam_review"]
    legal_review = payload["legal_review"]
    integrated_tasks = legal_review.get("integrated_revision_tasks", [])
    public_opinion_suggestions = legal_review.get("public_opinion_suggestions", [])

    statement = (
        "我们已注意到关于此事的相关传播内容，并充分理解公众对此产生的担忧与关切。"
        "对于尚未确认的信息，我们暂不作确定性判断。"
        "后续如有核查进展，我们将及时更新，并根据已核实情况讨论后续措施。"
        "对于事件给相关群体带来的不安，我们再次表示歉意。"
    )

    revision = payload.get("human_fact_revision") or {}
    if revision.get("fact_currently_unavailable"):
        statement = statement.replace(
            "对于尚未确认的信息，我们暂不作确定性判断。",
            "对于目前仍无法确认的相关事实，我们将保持谨慎，不作确定性判断。",
        )

    return _normalize_second_draft_output(
        {
            "statement": statement,
            "strategy": "优先落实 Legal Agent 整合出的修订任务，再兼顾红队反馈中的高价值舆情建议。",
            "tone": "先共情、再回应行动、避免抢先定性",
            "revisions": [
                "强化对公众担忧的回应",
                "说明核查正在进行",
                "避免对未确认信息作确定性结论",
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

人工事实回复后的指定 Claim 修订约束（仅本轮事实不可确认时使用）：
{payload.get("human_fact_revision", {})}

本轮 ContextPack（按 Writer V2 角色裁剪）：
{payload.get("context_pack_text", "")}

任务：
根据原始声明、红队攻击意见和法律审核建议，生成第二版公开声明。

写作要求：
- 保留事实谨慎，不提前确认事实，不提前定责。
- 提供有帮助的核查/整改/监管配合/后续更新建议，但只有当前 Case 输入明确支持时，才能表述为已经或正在执行。
- 历史经验只支持策略参考，不支持当前事实或当前行动状态；建议动作不得升级为已执行动作。
- 人工提供的信息应明确归因于人工来源，不能称为独立核实；FACT_UNAVAILABLE 必须保持未知。
- 增强公众沟通，回应消费者/用户/公众担忧。
- 吸收 redteam_review.issues / suggestions。
- 优先执行 legal_review.revision_advice 和 legal_review.integrated_revision_tasks。
- 不使用“一定、绝不、保证”等绝对化承诺。
- 输出中文。

{writer_v2_policy_overlay(payload.get("harness_spec"))}

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
- statement 应说明当前已确认的核查状态或有用的下一步安排；不得仅为满足文案要求而声称调查、核查或排查已经启动。
- 当前输入未证明行动已执行时，可以且应使用“建议立即核查”“将尽快核实”“可考虑”等建议性/条件性表达。建议不等于已执行。
- ContextPack 中标记为 historical_experience 的内容属于历史案例经验，只能借鉴策略；不得移植历史事实或历史行动状态。
- human_asserted 信息必须保留人工来源归属，不得称为 independently_verified；FACT_UNAVAILABLE 对应事实仍未知。
- statement 必须包含“配合监管部门”或“接受监督”，说明监管沟通安排。
- statement 必须包含至少一种后续措施，例如“整改”“召回”“第三方审计”“信息公开”“持续更新”。
- statement 必须使用条件式、谨慎表达，不能在调查完成前确认违法事实或直接定责。
- statement 禁止使用“一定”“绝不”“保证”“永远”等绝对化承诺。
- statement 禁止推卸责任，不能暗示责任在消费者、媒体或第三方。
- statement 必须输出中文，语气应先共情、再说明行动、最后给出后续安排。

输出前自检：
- 如果 statement 缺少歉意/关切表达，请补充。
- 如果没有任何核查安排，请补充一个适当的建议或条件性下一步；不得将其改写成已执行事实。
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
