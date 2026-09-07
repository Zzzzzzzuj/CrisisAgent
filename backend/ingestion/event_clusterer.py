import hashlib
import re
from datetime import datetime

from .schemas import NormalizedSentimentItem


RISK_TERMS = (
    "食品", "过期", "隐私", "数据", "泄露", "用户", "账号", "信息", "地址",
    "联系方式", "支付", "扣费", "故障", "投诉", "召回", "过热", "抵制", "赔偿",
)


def _tokens(text: str) -> set[str]:
    chinese = re.findall(r"[\u4e00-\u9fff]{2}", text)
    words = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
    return set(chinese + words)


def _date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compatible(left: NormalizedSentimentItem, right: NormalizedSentimentItem) -> bool:
    if left.company != right.company:
        return False
    left_date, right_date = _date(left.published_at), _date(right.published_at)
    if left_date and right_date and abs((left_date - right_date).days) > 7:
        return False
    left_tokens, right_tokens = _tokens(left.normalized_text), _tokens(right.normalized_text)
    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    risk_overlap = set(term for term in RISK_TERMS if term in left.normalized_text) & set(
        term for term in RISK_TERMS if term in right.normalized_text
    )
    return overlap >= 0.16 and bool(risk_overlap)


def cluster_items(items: list[NormalizedSentimentItem]) -> list[list[NormalizedSentimentItem]]:
    clusters: list[list[NormalizedSentimentItem]] = []
    for item in items:
        match = next((cluster for cluster in clusters if any(_compatible(item, other) for other in cluster)), None)
        if match is None:
            clusters.append([item])
        else:
            match.append(item)
    return clusters


def cluster_id(items: list[NormalizedSentimentItem]) -> str:
    seed = "|".join(sorted(item.item_id for item in items))
    return "cluster_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
