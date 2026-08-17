from time import perf_counter

import os

from backend.llm import LLMClient
from backend.llm.client import record_llm_fallback
from backend.llm.parser import LLMParseError, parse_json_response, validate_required_fields
from backend.logger import get_logger
from backend.tools.registry import tool_registry
from backend.tools.sentiment_tool import SentimentAnalysisTool


logger = get_logger(__name__)
AGENT_NAME = "Agent A"
REQUIRED_FIELDS = (
    "risk_level",
    "public_emotion",
    "keywords",
    "recommended_tone",
    "analysis_summary",
)
ALLOWED_PUBLIC_EMOTIONS = {"angry", "worried", "neutral", "positive"}
DEFAULT_RECOMMENDED_TONE = "先共情、再回应行动、避免抢先定性"
_LAST_TOOL_INFO = {
    "name": None,
    "input": None,
    "output": None,
    "success": False,
    "duration_ms": 0.0,
}


def run(event: str) -> dict:
    if _agent_mode() == "llm":
        _set_tool_info(
            name="sentiment_analysis",
            tool_input={"event": event},
            output=None,
            success=False,
            duration_ms=0.0,
        )
        try:
            return _run_llm(event)
        except Exception as exc:
            logger.warning(
                "%s fallback to mock mode due to llm failure: %s | %s",
                AGENT_NAME,
                exc.__class__.__name__,
                str(exc),
            )
            record_llm_fallback(AGENT_NAME, exc)
            return _run_mock(event)

    _set_tool_info(name=None, tool_input=None, output=None, success=False, duration_ms=0.0)
    return _run_mock(event)


def get_last_tool_info() -> dict:
    return dict(_LAST_TOOL_INFO)


def _set_tool_info(
    name: str | None,
    tool_input: dict | None,
    output,
    success: bool,
    duration_ms: float,
) -> None:
    _LAST_TOOL_INFO.update(
        {
            "name": name,
            "input": tool_input,
            "output": output,
            "success": success,
            "duration_ms": duration_ms,
        }
    )


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
    public_emotion = "angry" if any(word in event for word in ["要求", "曝光", "愤怒", "偷拍视频"]) else "worried"

    return _normalize_output(
        {
            "risk_level": risk_level,
            "public_emotion": public_emotion,
            "keywords": keywords or ["舆情扩散"],
            "recommended_tone": DEFAULT_RECOMMENDED_TONE,
            "analysis_summary": "当前事件具有较强传播性和监管敏感性，回应应强调重视、调查、整改与配合监管。",
        }
    )


def _run_llm(event: str) -> dict:
    tool_result = _run_sentiment_tool(event)
    prompt = _build_sentiment_prompt(event, tool_result)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, REQUIRED_FIELDS)

    validated = _validate_llm_output(parsed)
    logger.info("%s parsed llm result: %s", AGENT_NAME, validated)
    mapped_output = {
        "risk_level": validated["risk_level"],
        "public_emotion": _normalize_public_emotion(validated["public_emotion"]),
        "keywords": validated["keywords"],
        "recommended_tone": _normalize_recommended_tone(validated["recommended_tone"]),
        "analysis_summary": validated["analysis_summary"],
    }
    normalized_output = _normalize_output(mapped_output)
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    logger.debug("%s llm output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def call_llm(prompt: str) -> str:
    client = LLMClient()
    if client.config.mock_enabled:
        raise RuntimeError("LLM_API_KEY is not configured; fallback to mock sentiment agent.")
    return client.chat(
        messages=[
            {
                "role": "system",
                "content": "You are a crisis public opinion analysis agent. Return JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
        agent_name=AGENT_NAME,
    )


def _build_sentiment_prompt(event: str, tool_result: dict) -> str:
    return f"""
你是 CrisisAgent 的舆情分析 Agent A，负责分析企业危机公关事件的风险等级和公众情绪。

输入事件：
{event}

工具分析结果：
{tool_result}
tool_result: {tool_result}

请根据事件内容和工具结果进行判断。不要直接复制工具结果，工具结果只作为辅助参考。

风险判断要求：
- risk_level 使用字符串，可取 low / medium / high / critical，优先识别食品安全、监管介入、偷拍视频、数据泄露等高风险信号。
- public_emotion 必须使用固定枚举：angry / worried / neutral / positive。
- keywords 必须是字符串数组，提取 3-5 个关键风险词。
- recommended_tone 必须输出中文固定风格描述，建议优先使用：先共情、再回应行动、避免抢先定性。
- analysis_summary 必须使用中文，简要解释为什么这样判断。

只输出 JSON，不要输出 markdown，不要输出解释文字。JSON schema：
{{
  "risk_level": "high",
  "public_emotion": "angry",
  "keywords": ["食品安全", "监管介入"],
  "recommended_tone": "先共情、再回应行动、避免抢先定性",
  "analysis_summary": "..."
}}
""".strip()


def _agent_mode() -> str:
    return os.getenv("AGENT_MODE", "mock").strip().lower() or "mock"


def _run_sentiment_tool(event: str) -> dict:
    tool_input = {"event": event}
    start_time = perf_counter()

    try:
        tool = _get_sentiment_tool()
        tool_output = tool.run(tool_input)
    except Exception as exc:
        duration_ms = (perf_counter() - start_time) * 1000
        logger.warning(
            "%s sentiment_analysis tool failed, continuing without tool result: %s | %s",
            AGENT_NAME,
            exc.__class__.__name__,
            str(exc),
        )
        _set_tool_info(
            name="sentiment_analysis",
            tool_input=tool_input,
            output=None,
            success=False,
            duration_ms=duration_ms,
        )
        return {}

    duration_ms = (perf_counter() - start_time) * 1000
    _set_tool_info(
        name="sentiment_analysis",
        tool_input=tool_input,
        output=tool_output,
        success=True,
        duration_ms=duration_ms,
    )
    return tool_output


def _get_sentiment_tool():
    try:
        return tool_registry.get("sentiment_analysis")
    except KeyError:
        tool = SentimentAnalysisTool()
        tool_registry.register(tool)
        return tool


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

    normalized_emotion = _normalize_public_emotion(payload["public_emotion"])
    if normalized_emotion not in ALLOWED_PUBLIC_EMOTIONS:
        raise ValueError(
            "Field 'public_emotion' must normalize to one of: angry, worried, neutral, positive."
        )

    return payload


def _normalize_public_emotion(value: str) -> str:
    normalized = value.strip().lower()

    if normalized in ALLOWED_PUBLIC_EMOTIONS:
        return normalized
    if any(token in normalized for token in ["angry", "anger", "distrust", "rage", "愤怒", "不信任"]):
        return "angry"
    if any(token in normalized for token in ["worried", "concern", "anxious", "fear", "担忧", "焦虑", "担心"]):
        return "worried"
    if any(token in normalized for token in ["positive", "supportive", "认可", "支持", "正面"]):
        return "positive"
    if any(token in normalized for token in ["neutral", "mixed", "中性", "观望", "复杂"]):
        return "neutral"

    raise ValueError(f"Unsupported public_emotion value: {value}")


def _normalize_recommended_tone(value: str) -> str:
    normalized = value.strip().lower()

    if any(
        token in normalized
        for token in [
            "先共情",
            "回应行动",
            "避免抢先定性",
            "empathy",
            "action",
            "avoid premature",
            "avoid premature judgment",
        ]
    ):
        return DEFAULT_RECOMMENDED_TONE

    if any(token in normalized for token in ["冷静", "事实", "审慎", "calm", "fact-based", "cautious"]):
        return "保持冷静、基于事实回应、避免情绪化对抗"

    if any(token in normalized for token in ["透明", "及时", "更新", "transparent", "timely", "update"]):
        return "保持透明、及时同步进展、持续回应关切"

    return DEFAULT_RECOMMENDED_TONE


def _normalize_output(payload: dict) -> dict:
    return {
        "risk_level": str(payload["risk_level"]),
        "public_emotion": _normalize_public_emotion(str(payload["public_emotion"])),
        "keywords": [str(item) for item in payload["keywords"]],
        "recommended_tone": _normalize_recommended_tone(str(payload["recommended_tone"])),
        "analysis_summary": str(payload["analysis_summary"]),
    }
