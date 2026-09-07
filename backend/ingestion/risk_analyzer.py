from datetime import datetime, timedelta, timezone

from .event_clusterer import RISK_TERMS
from .schemas import NormalizedSentimentItem


HIGH_TERMS = (
    "食品", "过期", "泄露", "隐私", "个人信息", "账号信息", "订单信息", "监管", "投诉", "伤害",
    "过热", "异味", "不适", "召回", "欺诈", "赔偿", "抵制",
)
MEDIUM_TERMS = ("差评", "服务异常", "退款", "故障", "质疑", "担心")
ANGER_TERMS = ("抵制", "曝光", "欺骗", "赔偿", "监管介入", "愤怒")
WORRY_TERMS = ("安全", "隐私", "泄露", "账号信息", "订单信息", "地址", "过热", "不适", "风险", "担心")
DISAPPOINTMENT_TERMS = ("体验差", "失望", "投诉")
HISTORICAL_TERMS = ("去年", "曾经", "历史", "回顾", "旧闻", "过去")
CURRENT_TERMS = ("目前", "当前", "正在", "近期", "今日", "持续", "传播", "影响", "要求")


def analyze_risk(text: str) -> str:
    if any(term in text for term in HIGH_TERMS):
        return "high"
    if any(term in text for term in MEDIUM_TERMS):
        return "medium"
    return "low"


def analyze_emotion(text: str) -> str:
    if any(term in text for term in ANGER_TERMS):
        return "angry"
    if any(term in text for term in WORRY_TERMS):
        return "worried"
    if any(term in text for term in DISAPPOINTMENT_TERMS):
        return "disappointed"
    return "neutral"


def analyze_event_status(items: list[NormalizedSentimentItem], observation_time: datetime | None = None) -> str:
    combined = " ".join(item.normalized_text for item in items)
    if any(term in combined for term in HISTORICAL_TERMS):
        return "historical"
    now = observation_time or datetime.now(timezone.utc)
    dates = [_parse_date(item.published_at) for item in items]
    recent = any(date and now - timedelta(days=30) <= date <= now + timedelta(days=1) for date in dates)
    if recent and any(term in combined for term in CURRENT_TERMS):
        return "current"
    return "uncertain"


def _parse_date(value: str) -> datetime | None:
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date if date.tzinfo else date.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def analyze_fact_status(items: list[NormalizedSentimentItem]) -> str:
    statuses = {item.fact_status for item in items}
    if "conflicting" in statuses or len({item.normalized_text for item in items}) > 1 and any(
        "否认" in item.normalized_text or "未发现" in item.normalized_text for item in items
    ):
        return "conflicting"
    if "unverified" in statuses or len(items) < 2:
        return "unverified"
    return "verified"


def human_review_required(risk_level: str, event_status: str, fact_status: str) -> bool:
    return risk_level == "high" or fact_status in {"unverified", "conflicting"} or event_status == "uncertain"
