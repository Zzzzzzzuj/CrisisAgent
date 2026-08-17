from backend.config import get_config
from backend.llm import LLMClient
from backend.llm.client import record_llm_fallback
from backend.llm.parser import parse_json_response, validate_required_fields
from backend.logger import get_logger


logger = get_logger(__name__)
AGENT_NAME = "Agent E"
REQUIRED_FIELDS = ("final_statement", "scores", "recommendation", "reason")
REQUIRED_SCORE_FIELDS = ("legal_safety", "empathy", "robustness")


def run(payload: dict) -> dict:
    try:
        config = get_config()
    except Exception as exc:
        logger.warning(
            "%s fallback to mock mode due to config failure: %s | %s",
            AGENT_NAME,
            exc.__class__.__name__,
            str(exc),
        )
        record_llm_fallback(AGENT_NAME, exc)
        return _run_mock(payload)

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
            record_llm_fallback(AGENT_NAME, exc)

    return _run_mock(payload)


def _run_mock(payload: dict) -> dict:
    statement = _extract_second_draft(payload)
    redteam_review = payload.get("redteam_review", {})
    legal_review = payload.get("legal_review", {})
    sentiment_analysis = payload.get("sentiment_analysis", {})

    legal_safety = max(0, min(10, int(legal_review.get("legal_safety_score_hint", 7))))
    empathy = 8 if any(term in statement for term in ("担忧", "关切", "歉意", "理解")) else 6
    robustness = (
        8
        if len(redteam_review.get("issues", [])) <= 3
        and sentiment_analysis.get("risk_level") == "high"
        else 7
    )
    reason = "第二版在共情、行动说明和法律稳妥性之间取得了较平衡的结果，可作为当前对外回应底稿。"

    return _normalize_output(
        {
            "final_statement": statement,
            "scores": {
                "legal_safety": legal_safety,
                "empathy": empathy,
                "robustness": robustness,
            },
            "recommendation": "publish",
            "reason": reason,
            "decision_summary": reason,
        }
    )


def _run_llm(payload: dict) -> dict:
    prompt = _build_decision_prompt(payload)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, REQUIRED_FIELDS)

    validated = _validate_output(parsed)
    logger.info("%s parsed llm result: %s", AGENT_NAME, validated)
    normalized_output = _normalize_output(
        {
            "final_statement": validated["final_statement"],
            "scores": {
                "legal_safety": validated["scores"]["legal_safety"],
                "empathy": validated["scores"]["empathy"],
                "robustness": validated["scores"]["robustness"],
            },
            "recommendation": validated["recommendation"],
            "reason": validated["reason"],
            "decision_summary": validated["reason"],
        }
    )
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def call_llm(prompt: str) -> str:
    client = LLMClient()
    if client.config.mock_enabled:
        raise RuntimeError("LLM_API_KEY is not configured; fallback to mock decision agent.")
    return client.chat(
        messages=[
            {
                "role": "system",
                "content": "You are CrisisAgent Decision Agent E. Return JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
        agent_name=AGENT_NAME,
    )


def _build_decision_prompt(payload: dict) -> str:
    writer_v2 = payload.get("writer_v2") or _extract_second_draft(payload)
    return f"""
{_decision_stability_requirements()}

你是 CrisisAgent 的最终决策 Agent E，角色是企业危机响应首席决策官。

输入事件 event：
{payload.get("event", "")}

writer_v2 第二版声明：
{writer_v2}

legal_review 合规审查：
{payload.get("legal_review", {})}

redteam_review 红队反馈：
{payload.get("redteam_review", {})}

evaluation 运行评估：
{payload.get("evaluation", {})}

任务：
综合所有 Agent 输出，判断当前声明是否适合公开发布。

评估要求：
- 判断法律风险是否可控。
- 判断公众沟通效果是否足够。
- 判断是否吸收红队和法律建议。
- 不要重新生成长文本；final_statement 应直接采用或轻微清理 writer_v2 声明。
- scores 必须是 0-10 的整数。
- recommendation 建议使用 publish / revise / hold 之一。
- reason 用中文简要说明决策原因。

只输出 JSON，不要输出 markdown，不要输出额外解释。JSON schema：
{{
  "final_statement": "",
  "scores": {{
    "legal_safety": 0,
    "empathy": 0,
    "robustness": 0
  }},
  "recommendation": "",
  "reason": ""
}}
""".strip()


def _decision_stability_requirements() -> str:
    return """
Decision Agent 稳定评分要求：
角色：你是企业危机响应首席决策官。

你的任务不是重新生成声明，也不是重写 Writer_v2 文案。
你只负责：
1. 判断 Writer_v2 声明是否适合公开发布。
2. 根据 Legal / RedTeam / Evaluation 信息评分。
3. 输出稳定结构化结果。

final_statement 要求：
- 必须直接使用 Writer_v2 statement。
- 禁止重新创作、扩写或改变声明内容。
- 只允许做极轻微格式清理，不允许改变含义。

legal_safety 评分规则：
- 10 分：无提前定责；包含调查/核查/排查；包含配合监管部门/接受监督；包含整改、召回、信息公开、第三方审计等措施。
- 8 分：基本合规，但缺少部分细节。
- 7 分以下：存在明确法律风险，例如提前确认违法事实、提前定责、绝对化承诺、缺少核查或监管沟通。

empathy 评分规则：
- 10 分：有歉意或关切；明确关注消费者影响；沟通态度积极。
- 8 分：有基本回应，但情绪安抚或消费者视角不够充分。
- 7 分以下：缺少情绪回应、歉意、关切或消费者视角。

robustness 评分规则：
- 10 分：有行动计划；有持续更新；有监督机制；吸收 redteam 和 legal 建议。
- 8 分：基本完整，但后续措施或监督机制略弱。
- 7 分以下：缺少后续措施、更新安排、监督机制，或明显未吸收 redteam/legal 建议。

recommendation 规则：
- 如果三项分数均 >= 7，优先输出 publish。
- 如果任一分数 < 7，输出 revise。
- 只有存在严重法律风险或声明不可发布时才输出 hold。

稳定性要求：
- 不要过度降低评分。若 Writer_v2 已包含共情、核查、配合监管、整改/召回/更新/监督等要素，分数通常应为 8-10。
- scores 必须是 0-10 的整数。
- recommendation 必须是 publish / revise / hold 之一。
- reason 用中文简要说明评分依据。
""".strip()


def _validate_output(payload: dict) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    if not isinstance(payload["final_statement"], str):
        raise TypeError("Field 'final_statement' must be a string.")
    if not isinstance(payload["scores"], dict):
        raise TypeError("Field 'scores' must be an object.")
    if not isinstance(payload["recommendation"], str):
        raise TypeError("Field 'recommendation' must be a string.")
    if not isinstance(payload["reason"], str):
        raise TypeError("Field 'reason' must be a string.")

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
    reason = str(payload.get("reason", payload.get("decision_summary", "")))
    return {
        "final_statement": str(payload["final_statement"]),
        "scores": {
            "legal_safety": max(0, min(10, int(payload["scores"]["legal_safety"]))),
            "empathy": max(0, min(10, int(payload["scores"]["empathy"]))),
            "robustness": max(0, min(10, int(payload["scores"]["robustness"]))),
        },
        "recommendation": str(payload.get("recommendation", "publish")),
        "reason": reason,
        "decision_summary": str(payload.get("decision_summary", reason)),
    }


def _extract_second_draft(payload: dict) -> str:
    writer_v2 = payload.get("writer_v2")
    if isinstance(writer_v2, dict):
        return str(writer_v2.get("statement", ""))
    if isinstance(writer_v2, str):
        return writer_v2
    return str(payload.get("second_draft", ""))
