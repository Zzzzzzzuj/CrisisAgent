import asyncio

import httpx

from backend.agents.context_pack import build_context_pack
from backend.agents.memory_retriever import retrieve_memories
from backend.api.event_store import JsonCrisisEventStore
from backend.main import app


def _request(method, path, body=None):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.request(method, path, json=body)
    return asyncio.run(send())


def test_context_pack_limits_inputs_and_records_dropped_fields():
    pack = build_context_pack(
        event={"event_id": "e1", "company": "示例公司", "risk_level": "high", "fact_status": "unverified", "event_status": "current"},
        public_signals=[{"title": str(index), "content_preview": "x" * 700} for index in range(7)],
        alerts=[{"title": str(index)} for index in range(5)],
        legal_evidence=[{"text": "e" * 700} for _ in range(5)],
        case_memories=[
            {"memory_id": str(index), "entity_name": "示例公司", "tags": ["food"], "final_statement_summary": "summary"}
            for index in range(5)
        ],
        human_review_notes=["note"] * 5,
    )
    assert len(pack["top_public_signals"]) == 5
    assert len(pack["top_alerts"]) == 3
    assert len(pack["top_legal_evidence"]) == 3
    assert len(pack["related_case_memories"]) <= 3
    assert "public_signals" in pack["dropped_fields"]
    assert "alerts" in pack["dropped_fields"]
    assert "legal_evidence" in pack["dropped_fields"]
    assert "case_memories" in pack["dropped_fields"]
    assert "human_review_notes" in pack["dropped_fields"]
    assert all(len(item["content_preview"]) <= 500 for item in pack["top_public_signals"])


def test_context_pack_excludes_sensitive_fields_and_accepts_text():
    pack = build_context_pack(
        event_text="某公司发生需要核实的产品事件",
        public_signals=[{"content": "full", "system_prompt": "secret", "api_key": "secret", "title": "signal"}],
    )
    serialized = str(pack)
    assert "system_prompt" not in serialized
    assert "api_key" not in serialized
    assert "full" not in serialized


def test_context_pack_drops_explicitly_low_relevance_items():
    pack = build_context_pack(
        event_text="示例公司产品事件",
        public_signals=[{"title": "noise", "relevant": False}, {"title": "kept", "relevance_score": 0.9}],
    )
    assert [item["title"] for item in pack["top_public_signals"]] == ["kept"]
    assert "public_signals" in pack["dropped_fields"]


def test_context_pack_api_builds_from_existing_event(monkeypatch, tmp_path):
    event_path = tmp_path / "events.json"
    monkeypatch.setenv("CRISIS_EVENT_STORE_PATH", str(event_path))
    monkeypatch.setenv("AUDIT_LOG_STORE_PATH", str(tmp_path / "audit.json"))
    store = JsonCrisisEventStore(event_path)
    event, _ = store.create_from_cluster(
        source_run_id="run-pack",
        cluster={"cluster_id": "cluster-pack", "event": "产品质量事件", "company": "示例公司",
                 "risk_level": "medium", "public_emotion": "worried", "fact_status": "verified",
                 "event_status": "current", "human_review_required": False, "source_count": 1,
                 "source_items": ["source-a"], "event_fingerprint": "fp-pack"},
    )
    response = _request("POST", "/api/context-pack/build", {"event_id": event["event_id"]})
    assert response.status_code == 200
    assert response.json()["context_pack"]["event_facts"]["event_id"] == event["event_id"]
    assert response.json()["safety_notes"]
    focused = _request("POST", "/api/context-pack/build", {"event_id": event["event_id"], "target_agent": "legal"})
    assert focused.status_code == 200
    assert focused.json()["agent_specific_focus"]["target_agent"] == "legal"


def test_lifecycle_memory_retriever_prefers_same_group_and_nearby_round():
    memories = [
        {"memory_id": "old", "case_group_id": "g1", "round_index": 1, "crisis_type": "food_safety",
         "entity_name": "示例公司", "risk_level": "high", "fact_status": "verified", "tags": ["召回"],
         "created_at": "2026-01-01T00:00:00+00:00"},
        {"memory_id": "latest", "case_group_id": "g1", "round_index": 3, "crisis_type": "food_safety",
         "entity_name": "示例公司", "risk_level": "high", "fact_status": "verified", "tags": ["召回"],
         "created_at": "2026-01-01T00:00:00+00:00"},
        {"memory_id": "other", "case_group_id": "g2", "round_index": 3, "crisis_type": "food_safety",
         "entity_name": "示例公司", "risk_level": "high", "fact_status": "verified", "tags": ["召回"],
         "created_at": "2026-01-01T00:00:00+00:00"},
    ]
    result = retrieve_memories({"company": "示例公司", "crisis_type": "food_safety", "risk_level": "high",
                                "fact_status": "verified", "tags": ["召回"], "case_group_id": "g1", "round_index": 3}, memories)
    assert result[0]["memory_id"] == "latest"
    assert "case_group_match" in result[0]["matched_reasons"]


def test_agent_specific_context_pack_focuses_on_lifecycle_memory():
    memories = [{
        "memory_id": "round-1", "entity_name": "示例公司", "crisis_type": "food_safety", "risk_level": "high",
        "fact_status": "verified", "tags": ["召回"], "final_statement_summary": "上一轮声明摘要",
        "previous_statement_summary": "上一轮声明摘要", "public_reaction_summary": "公众转而追问赔付",
        "previous_redteam_findings": ["责任边界不清"], "unresolved_redteam_findings": ["赔付标准未说明"],
        "previous_legal_constraints": ["避免承认未经证实的责任"], "avoid_repeating_points": ["不要重复高度重视"],
        "what_changed_since_previous": "新增召回范围", "outcome": "worsened", "round_index": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
    }]
    for agent, expected in {"redteam": "previous_redteam_findings", "legal": "previous_legal_constraints",
                            "writer": "previous_statement_summary", "decision": "outcome_trend"}.items():
        pack = build_context_pack(event={"company": "示例公司", "crisis_type": "food_safety", "risk_level": "high",
                                         "fact_status": "verified", "event_status": "current", "event_summary": "召回"},
                                  case_memories=memories, target_agent=agent)
        assert expected in pack["agent_specific_focus"]
        assert pack["selected_case_ids"] == ["round-1"]


def test_context_pack_agent_focus_excludes_sensitive_and_full_text_data():
    pack = build_context_pack(
        event={"company": "示例公司", "event_summary": "事件"}, target_agent="redteam",
        case_memories=[{"memory_id": "m1", "entity_name": "示例公司", "tags": ["事件"],
                        "previous_redteam_findings": ["issue"], "full_text": "PRIVATE_ARTICLE",
                        "system_prompt": "PRIVATE_PROMPT", "api_key": "PRIVATE_KEY",
                        "created_at": "2026-01-01T00:00:00+00:00"}],
    )
    serialized = str(pack)
    assert "PRIVATE_ARTICLE" not in serialized
    assert "PRIVATE_PROMPT" not in serialized
    assert "PRIVATE_KEY" not in serialized
