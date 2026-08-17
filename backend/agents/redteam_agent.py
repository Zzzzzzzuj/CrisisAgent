from backend.config import get_config
from backend.llm import LLMClient
from backend.llm.client import record_llm_fallback
from backend.llm.parser import parse_json_response, validate_required_fields
from backend.logger import get_logger


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
            record_llm_fallback(AGENT_NAME, exc)

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
    prompt = _build_redteam_prompt(payload)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, REQUIRED_FIELDS)

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


def call_llm(prompt: str) -> str:
    client = LLMClient()
    if client.config.mock_enabled:
        raise RuntimeError("LLM_API_KEY is not configured; fallback to mock redteam agent.")
    return client.chat(
        messages=[
            {
                "role": "system",
                "content": "You are CrisisAgent RedTeam Agent D. Return JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
        agent_name=AGENT_NAME,
    )


def _build_redteam_prompt(payload: dict) -> str:
    return f"""
你是 CrisisAgent 的红队攻击 Agent D，扮演危机公关审查专家、媒体观察者和公众质疑者。

输入事件：
{payload["event"]}

待审查声明 draft：
{payload["draft"]}

请从公众和媒体最可能质疑的角度进行审查，重点分析：
- 声明是否模板化、空泛或缺少诚意。
- 是否遗漏关键行动，例如调查、整改、召回、补偿、监管配合、后续更新。
- 是否存在公众质疑点，例如推责、拖延、避重就轻。
- 是否存在信任风险，例如承诺不具体、透明度不足、对受影响人群回应不够。

输出要求：
- issues 必须是字符串数组，列出 1-5 个主要问题。
- attack_summary 必须是一段中文摘要，说明外部可能如何攻击这份声明。
- suggestions 必须是字符串数组，给出可执行修改建议。
- 只输出 JSON，不要输出 markdown，不要输出额外解释。

JSON schema：
{{
  "issues": [],
  "attack_summary": "",
  "suggestions": []
}}
""".strip()


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
