from pathlib import Path

from backend.ingestion.article_extractor import extract_article
from backend.ingestion.pipeline import run_sentiment_ingestion_items
from backend.ingestion.robots import RobotsChecker
from backend.ingestion.schemas import RawSentimentItem
from backend.ingestion.source_adapters import RssSourceAdapter
from backend.ingestion.source_registry import SourceDefinition, SourceRegistry


RSS_SAMPLE = """<?xml version='1.0'?><rss><channel>
<item><title>示例公司食品安全投诉</title><link>https://news.example/item-1</link>
<description>消费者投诉食品安全问题，监管部门关注。</description><pubDate>Mon, 07 Sep 2026 08:00:00 GMT</pubDate></item>
<item><title>季度财报</title><link>https://news.example/item-2</link>
<description>公司公布季度经营数据。</description><pubDate>Mon, 07 Sep 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def source(**overrides):
    values = dict(
        source_id="test_rss", source_name="Test RSS", source_type="rss",
        url="https://news.example/feed.xml", enabled=True,
        company_keywords=("示例公司",), risk_keywords=("食品安全", "投诉"),
    )
    values.update(overrides)
    return SourceDefinition(**values)


def test_registry_defaults_sources_to_disabled(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text('{"sources": [{"source_id":"x","source_name":"x","source_type":"rss","url":"https://example.com/a"}]}', encoding="utf-8")
    registry = SourceRegistry.from_file(path)
    assert registry.enabled_sources() == []


def test_no_live_fetch_flag_is_safe_by_default():
    assert SourceRegistry([source(enabled=False)]).enabled_sources() == []


def test_robots_denied_is_separate_from_fetch_failure():
    checker = RobotsChecker(fetcher=lambda *_: "User-agent: *\nDisallow: /")
    allowed, reason = checker.check("https://news.example/feed.xml")
    assert allowed is False
    assert reason == "robots_denied"


def test_robots_fetch_failure_is_conservative():
    checker = RobotsChecker(fetcher=lambda *_: (_ for _ in ()).throw(TimeoutError()))
    allowed, reason = checker.check("https://news.example/feed.xml")
    assert allowed is False
    assert reason.startswith("robots_fetch_failed")


def test_rss_sample_maps_only_matching_items():
    result = RssSourceAdapter.parse(RSS_SAMPLE, source())
    assert result.status == "collected"
    assert result.fetched_count == 2
    assert result.matched_count == 1
    assert result.items[0].fact_status == "unverified"


def test_article_html_fallback_extracts_title_and_content():
    article = extract_article("<html><head><title>示例文章</title></head><body><p>这是一段足够长的文章正文。</p></body></html>")
    assert article.title == "示例文章"
    assert "文章正文" in article.content


def test_rss_no_match_is_not_failed():
    result = RssSourceAdapter.parse("<rss><channel><item><title>普通新闻</title><description>无关内容</description></item></channel></rss>", source())
    assert result.status == "no_match"
    assert result.failed_reason is None


def test_rss_results_enter_existing_pipeline_without_network():
    result = RssSourceAdapter.parse(RSS_SAMPLE, source())
    events = run_sentiment_ingestion_items(result.items)
    assert len(events) == 1
    assert events[0].human_review_required is True


def test_registry_rejects_unsupported_or_non_https_sources(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text('{"sources": [{"source_id":"x","source_name":"x","source_type":"crawl","url":"http://example.com"}]}', encoding="utf-8")
    try:
        SourceRegistry.from_file(path)
    except ValueError as exc:
        assert "Unsupported source_type" in str(exc)
    else:
        raise AssertionError("unsafe source must be rejected")
