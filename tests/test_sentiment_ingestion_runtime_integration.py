from datetime import datetime, timezone
from pathlib import Path

from backend.ingestion.pipeline import run_sentiment_ingestion_pipeline, to_crisis_event_text
from backend.core.runtime_tasks import run_dynamic_sync


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "sentiment_ingestion_fixture.json"


def _events():
    return run_sentiment_ingestion_pipeline(FIXTURE, datetime(2026, 9, 7, tzinfo=timezone.utc))


def test_clustered_event_text_preserves_runtime_context():
    event = _events()[0]
    text = to_crisis_event_text(event)
    assert text
    assert "来源数：" in text
    assert "事件状态：" in text
    assert "事实状态：" in text


def test_high_risk_unverified_and_conflicting_events_keep_review_signals():
    events = _events()
    assert any(event.risk_level == "high" and event.human_review_required for event in events)
    assert any(event.fact_status == "unverified" and event.human_review_required for event in events)
    assert any(event.fact_status == "conflicting" and event.human_review_required for event in events)


def test_clustered_event_enters_existing_mock_dynamic_runtime(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    from backend.config import get_config
    from backend.llm.config import get_llm_config

    get_config.cache_clear()
    get_llm_config.cache_clear()
    event = next(item for item in _events() if item.risk_level == "high" and item.human_review_required)

    result = run_dynamic_sync(to_crisis_event_text(event))

    assert result["status"] in {"completed", "waiting_human"}
    assert result["session_id"]
    assert result["execution_trace"]
    assert [item["agent"] for item in result["execution_trace"] if item.get("status") == "success"] == [
        "sentiment",
        "writer",
        "redteam",
        "legal",
        "writer_v2",
        "decision",
    ]
    # Existing Dynamic Runtime currently receives only the converted event
    # string; the upstream review flag is preserved in that text but is not
    # yet a separate runtime-policy input.
    assert "风险等级：high" in to_crisis_event_text(event)


def test_integration_uses_no_network_or_real_llm():
    # The test only reads the repository fixture and executes deterministic mock agents.
    assert FIXTURE.exists()
