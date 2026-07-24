from backend.tools.base import BaseTool


class SentimentAnalysisTool(BaseTool):
    name = "sentiment_analysis"
    description = "Mock public opinion analysis for a crisis event."

    def run(self, params: dict) -> dict:
        event = params.get("event") if isinstance(params, dict) else None
        if not isinstance(event, str) or not event.strip():
            raise ValueError("sentiment_analysis requires a non-empty string param: event")

        return {
            "emotion": _detect_emotion(event),
            "heat_level": _detect_heat_level(event),
            "trend": _detect_trend(event),
        }


def _detect_emotion(event: str) -> str:
    if any(keyword in event for keyword in ("愤怒", "抵制", "过期", "泄露", "违法")):
        return "angry"
    if any(keyword in event for keyword in ("担忧", "质疑", "投诉", "无法")):
        return "worried"
    if any(keyword in event for keyword in ("正面", "支持", "捐赠")):
        return "positive"
    return "neutral"


def _detect_heat_level(event: str) -> str:
    if any(keyword in event for keyword in ("热搜", "监管", "公开视频", "大量", "抵制")):
        return "high"
    if any(keyword in event for keyword in ("投诉", "质疑", "传播")):
        return "medium"
    return "low"


def _detect_trend(event: str) -> str:
    if any(keyword in event for keyword in ("持续", "发酵", "传播", "热搜")):
        return "rising"
    if any(keyword in event for keyword in ("澄清", "回应", "调查")):
        return "stable"
    return "unknown"
