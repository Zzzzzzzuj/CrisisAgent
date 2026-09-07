import json
from datetime import datetime, timezone
from pathlib import Path

from backend.ingestion.deduplicator import deduplicate_items
from backend.ingestion.event_clusterer import cluster_items
from backend.ingestion.normalizer import clean_text, normalize_item
from backend.ingestion.pipeline import run_sentiment_ingestion_pipeline, to_crisis_event_text
from backend.ingestion.schemas import RawSentimentItem
from backend.ingestion.source_adapters import RssSourceAdapter


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "sentiment_ingestion_fixture.json"


def test_normalizer_removes_html_spaces_and_repeated_punctuation():
    assert clean_text("<p>  当前 事件！！！ </p>") == "当前 事件！"


def test_duplicate_url_title_and_content_are_deduplicated():
    base = RawSentimentItem("1", "a", "same", "标题", "正文", "2026-09-01T00:00:00+00:00", "公司", "verified")
    newer = RawSentimentItem("2", "b", "same", "标题", "更完整正文", "2026-09-02T00:00:00+00:00", "公司", "verified")
    result, stats = deduplicate_items([normalize_item(base), normalize_item(newer)])
    assert len(result) == 1
    assert stats["removed"] == 1
    assert result[0].item_id == "2"


def test_similar_items_cluster_together():
    items = [
        normalize_item(RawSentimentItem("1", "a", "u1", "产品过热反馈", "设备过热影响使用", "2026-09-01T00:00:00+00:00", "公司", "verified")),
        normalize_item(RawSentimentItem("2", "b", "u2", "设备过热讨论", "用户反馈设备过热并要求检查", "2026-09-02T00:00:00+00:00", "公司", "verified")),
    ]
    assert len(cluster_items(items)) == 1


def test_similar_privacy_items_cluster_together():
    items = [
        normalize_item(RawSentimentItem("1", "a", "u1", "账号信息异常可见", "用户看到其他账号地址", "2026-09-01T00:00:00+00:00", "公司", "unverified")),
        normalize_item(RawSentimentItem("2", "b", "u2", "用户信息显示异常", "订单信息可能被其他账号看到", "2026-09-02T00:00:00+00:00", "公司", "unverified")),
    ]
    assert len(cluster_items(items)) == 1


def test_fixture_produces_historical_uncertain_and_conflicting_events():
    events = run_sentiment_ingestion_pipeline(FIXTURE, datetime(2026, 9, 7, tzinfo=timezone.utc))
    statuses = {event.event_status for event in events}
    facts = {event.fact_status for event in events}
    assert "historical" in statuses
    assert "uncertain" in statuses
    assert "conflicting" in facts
    assert all(event.human_review_required for event in events if event.risk_level == "high" or event.event_status == "uncertain")
    privacy = next(event for event in events if event.company == "星河平台" and event.source_count == 2)
    assert privacy.risk_level == "high"
    assert privacy.public_emotion == "worried"


def test_cluster_can_be_converted_to_existing_event_text():
    event = run_sentiment_ingestion_pipeline(FIXTURE, datetime(2026, 9, 7, tzinfo=timezone.utc))[0]
    text = to_crisis_event_text(event)
    assert event.company in text
    assert "风险等级" in text
    assert "事实状态" in text


def test_rss_adapter_is_explicitly_offline():
    try:
        RssSourceAdapter().load("https://example.com/feed")
    except RuntimeError as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("RSS adapter must not perform network ingestion in Phase 1")
