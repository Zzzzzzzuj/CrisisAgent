from datetime import datetime
from pathlib import Path

from .deduplicator import deduplicate_items
from .event_clusterer import cluster_id, cluster_items
from .normalizer import normalize_item
from .risk_analyzer import (
    analyze_emotion,
    analyze_event_status,
    analyze_fact_status,
    analyze_risk,
    human_review_required,
)
from .schemas import ClusteredCrisisEvent
from .source_adapters import load_local_items


def _cluster_event(items, observation_time: datetime | None = None) -> ClusteredCrisisEvent:
    combined = "；".join(item.normalized_text for item in items)
    risk_level = analyze_risk(combined)
    event_status = analyze_event_status(items, observation_time)
    fact_status = analyze_fact_status(items)
    dates = sorted(item.published_at for item in items)
    fingerprint = f"{items[0].company}|{risk_level}|{items[0].title[:24]}"
    return ClusteredCrisisEvent(
        cluster_id=cluster_id(items),
        company=items[0].company,
        event=combined,
        source_items=[item.item_id for item in items],
        source_count=len(items),
        first_published_at=dates[0] if dates else "",
        last_published_at=dates[-1] if dates else "",
        event_status=event_status,
        fact_status=fact_status,
        risk_level=risk_level,
        public_emotion=analyze_emotion(combined),
        human_review_required=human_review_required(risk_level, event_status, fact_status),
        event_fingerprint=fingerprint,
    )


def run_sentiment_ingestion_pipeline(input_path: str | Path, observation_time: datetime | None = None) -> list[ClusteredCrisisEvent]:
    raw_items = load_local_items(input_path)
    normalized = [normalize_item(item) for item in raw_items]
    deduped, _ = deduplicate_items(normalized)
    return [_cluster_event(cluster, observation_time) for cluster in cluster_items(deduped)]


def to_crisis_event_text(cluster: ClusteredCrisisEvent) -> str:
    fact_prefix = {
        "verified": "据多来源一致信息显示",
        "unverified": "据来源显示，相关信息尚待核实",
        "conflicting": "据来源显示，多来源存在不一致，尚待核实",
    }.get(cluster.fact_status, "据来源显示，相关信息尚待核实")
    return (
        f"企业：{cluster.company}；事件：{fact_prefix}：{cluster.event}；"
        f"风险等级：{cluster.risk_level}；公众情绪：{cluster.public_emotion}；"
        f"事件状态：{cluster.event_status}；事实状态：{cluster.fact_status}；"
        f"来源数：{cluster.source_count}；来源摘要：{', '.join(cluster.source_items)}。"
    )
