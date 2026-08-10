import asyncio
import json

import httpx

from backend.core.dynamic_runtime import run_dynamic_agent
from backend.core.executor import execute
from backend.core.state import AgentState
from backend.agents import legal_agent
from backend.config import get_config
from backend.main import app


TEST_EVENT = "某食品品牌被曝光使用过期原料，相关视频在网络传播，消费者要求监管介入。"
LEGAL_OUTPUT = {
    "legal_risks": [],
    "safe_points": ["conditional wording"],
    "revision_advice": ["keep investigation wording"],
    "public_opinion_suggestions": ["respond to consumers"],
    "integrated_revision_tasks": ["add regulatory cooperation"],
    "legal_safety_score_hint": 8,
    "review_summary": "safe",
}


def _fake_registry():
    def sentiment(event):
        return {
            "risk_level": "high",
            "public_emotion": "angry",
            "keywords": ["过期原料", "监管介入"],
            "recommended_tone": "先共情、再回应行动、避免抢先定性",
            "analysis_summary": "high risk",
        }

    def writer(payload):
        return {
            "statement": "first draft",
            "strategy": "empathy first",
            "tone": "careful",
            "notes": "mock writer",
        }

    def redteam(payload):
        return {
            "issues": ["missing concrete action"],
            "attack_summary": "could be challenged",
            "suggestions": ["add investigation scope"],
        }

    def writer_v2(payload):
        return {
            "statement": "second draft",
            "strategy": "revise with legal advice",
            "revisions_from_v1": ["added investigation scope"],
            "review_summary": {},
        }

    def decision(payload):
        return {
            "final_statement": payload["second_draft"],
            "scores": {
                "legal_safety": 8,
                "empathy": 8,
                "robustness": 8,
            },
            "decision_summary": "ready",
        }

    return {
        "sentiment": sentiment,
        "writer": writer,
        "redteam": redteam,
        "legal": lambda payload: LEGAL_OUTPUT,
        "writer_v2": writer_v2,
        "decision": decision,
    }


def _rag_info(sources=None, count=None):
    sources = [] if sources is None else sources
    return {
        "enabled": True,
        "hit": bool(sources),
        "retrieval_type": "hybrid" if sources else None,
        "rerank_enabled": bool(sources),
        "query": "legal query from agent",
        "sources": sources,
        "chunks": [
            {
                "chunk_id": "chunk-1",
                "source": sources[0],
                "title": "Food Safety",
                "score": 0.8,
                "rerank_score": 0.9,
                "text_preview": "食品安全危机回应规范",
            }
        ]
        if sources
        else [],
        "scores": [0.8] if sources else [],
        "rerank_scores": [0.9] if sources else [],
        "count": len(sources) if count is None else count,
        "fallback_used": False,
        "gate": {
            "need_rag": True,
            "intent": "crisis_response_needed",
            "decision_score": 5,
            "current_incident": True,
            "current_incident_signals": ["current_response_need"],
            "task_intent": "ambiguous_enterprise_risk",
            "decision_path": "current_incident_override",
            "reason": "test gate result",
            "matched_signals": ["current_response_need"],
            "negative_signals": [],
        },
        "retrieval_skipped": False,
        "retrieval_executed": True,
        "retrieval_status": "executed_with_hits" if sources else "executed_no_hit",
    }


def _find_trace(trace: list[dict], agent: str) -> dict:
    for item in trace:
        if item.get("agent") == agent:
            return item
    raise AssertionError(f"{agent} trace not found")


def test_dynamic_execution_trace_records_legal_rag_sources(monkeypatch):
    monkeypatch.setattr(
        "backend.core.executor.legal_agent.get_last_rag_info",
        lambda: _rag_info(["food_safety.md", "legal_risk_rules.md"]),
    )

    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())
    legal_trace = _find_trace(result["execution_trace"], "legal")

    assert legal_trace["status"] == "success"
    assert legal_trace["rag"]["hit"] is True
    assert legal_trace["rag"]["sources"] == ["food_safety.md", "legal_risk_rules.md"]
    assert legal_trace["rag"]["count"] == 2
    assert legal_trace["rag"]["fallback_used"] is False
    assert legal_trace["rag"]["gate"]["need_rag"] is True
    assert legal_trace["rag"]["retrieval_executed"] is True
    assert legal_trace["rag"]["retrieval_skipped"] is False


def test_dynamic_rag_sources_come_from_legal_agent_metadata(monkeypatch):
    expected_rag = _rag_info(["legal_risk_rules.md"], count=1)
    monkeypatch.setattr(
        "backend.core.executor.legal_agent.get_last_rag_info",
        lambda: expected_rag,
    )

    state = AgentState(session_id="session-rag", plan_id="plan-rag", event=TEST_EVENT)
    state.set_result("writer", {"statement": "draft from state"})
    state.set_result("redteam", {"issues": [], "suggestions": []})
    result = execute(
        {"plan_id": "plan-rag", "plan": [{"agent": "legal", "reason": "review legal"}]},
        state,
        agent_registry={"legal": lambda payload: LEGAL_OUTPUT},
    )

    legal_trace = result["execution_trace"][0]
    assert legal_trace["rag"] == expected_rag
    assert legal_trace["rag"]["sources"] == ["legal_risk_rules.md"]


def test_dynamic_legal_trace_handles_empty_rag_result(monkeypatch):
    monkeypatch.setattr(
        "backend.core.executor.legal_agent.get_last_rag_info",
        lambda: _rag_info([], count=0),
    )

    state = AgentState(session_id="session-empty-rag", plan_id="plan-rag", event=TEST_EVENT)
    state.set_result("writer", {"statement": "draft"})
    state.set_result("redteam", {"issues": [], "suggestions": []})
    result = execute(
        {"plan_id": "plan-rag", "plan": [{"agent": "legal", "reason": "review legal"}]},
        state,
        agent_registry={"legal": lambda payload: LEGAL_OUTPUT},
    )

    legal_trace = result["execution_trace"][0]
    assert legal_trace["rag"]["sources"] == []
    assert legal_trace["rag"]["count"] == 0
    json.dumps(legal_trace)


def test_legal_rag_metadata_count_tracks_sources_and_scores_track_chunks(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        legal_agent,
        "evaluate_retrieval_need",
        lambda **kwargs: {
            "need_rag": True,
            "intent": "crisis_response_needed",
            "decision_score": 5,
            "reason": "test gate result",
            "matched_signals": ["current_response_need"],
            "negative_signals": [],
            "current_incident": True,
            "current_incident_signals": ["current_response_need"],
            "task_intent": "ambiguous_enterprise_risk",
            "decision_path": "current_incident_override",
        },
    )
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {
            "context": "[food_safety.md]\ncontext",
            "sources": [
                {"source": "food_safety.md", "score": 0.9, "retrieval_type": "hybrid"},
                {"source": "food_safety.md", "score": 0.8, "retrieval_type": "hybrid"},
                {"source": "legal_risk_rules.md", "score": 0.7, "retrieval_type": "hybrid"},
            ],
            "chunks": [
                {
                    "chunk_id": "food-1",
                    "source": "food_safety.md",
                    "title": "Food Safety",
                    "score": 0.9,
                    "rerank_score": 0.95,
                    "metadata": {"retrieval_type": "hybrid", "rerank_enabled": True},
                    "text": "chunk one",
                },
                {
                    "chunk_id": "food-2",
                    "source": "food_safety.md",
                    "title": "Food Safety",
                    "score": 0.8,
                    "rerank_score": 0.85,
                    "metadata": {"retrieval_type": "hybrid", "rerank_enabled": True},
                    "text": "chunk two",
                },
                {
                    "chunk_id": "legal-1",
                    "source": "legal_risk_rules.md",
                    "title": "Legal Rules",
                    "score": 0.7,
                    "rerank_score": 0.75,
                    "metadata": {"retrieval_type": "hybrid", "rerank_enabled": True},
                    "text": "chunk three",
                },
            ],
        },
    )
    monkeypatch.setattr(
        legal_agent,
        "call_llm",
        lambda prompt: """
        {
          "legal_risks": [],
          "safe_points": ["safe"],
          "revision_advice": ["advice"],
          "public_opinion_suggestions": ["suggestion"],
          "integrated_revision_tasks": ["task"],
          "legal_safety_score_hint": 8,
          "review_summary": "summary"
        }
        """,
    )

    legal_agent.run(
        {
            "event": TEST_EVENT,
            "draft": "draft",
            "redteam_review": {"issues": [], "suggestions": []},
        }
    )
    rag_info = legal_agent.get_last_rag_info()

    assert rag_info["sources"] == ["food_safety.md", "legal_risk_rules.md"]
    assert rag_info["count"] == len(rag_info["sources"])
    assert len(rag_info["chunks"]) == 3
    assert rag_info["scores"] == [0.9, 0.8, 0.7]
    assert rag_info["rerank_scores"] == [0.95, 0.85, 0.75]
    assert len(rag_info["scores"]) == len(rag_info["chunks"])
    assert len(rag_info["rerank_scores"]) == len(rag_info["chunks"])


def test_dynamic_trace_preserves_source_count_and_chunk_score_layers(monkeypatch):
    rag_info = {
        "enabled": True,
        "hit": True,
        "retrieval_type": "hybrid",
        "rerank_enabled": True,
        "query": "legal query from agent",
        "sources": ["food_safety.md", "legal_risk_rules.md"],
        "chunks": [
            {"chunk_id": "food-1", "source": "food_safety.md", "score": 0.9, "rerank_score": 0.95},
            {"chunk_id": "food-2", "source": "food_safety.md", "score": 0.8, "rerank_score": 0.85},
            {"chunk_id": "legal-1", "source": "legal_risk_rules.md", "score": 0.7, "rerank_score": 0.75},
        ],
        "scores": [0.9, 0.8, 0.7],
        "rerank_scores": [0.95, 0.85, 0.75],
        "count": 2,
        "fallback_used": False,
    }
    monkeypatch.setattr(
        "backend.core.executor.legal_agent.get_last_rag_info",
        lambda: rag_info,
    )

    state = AgentState(session_id="session-rag-layers", plan_id="plan-rag", event=TEST_EVENT)
    state.set_result("writer", {"statement": "draft"})
    state.set_result("redteam", {"issues": [], "suggestions": []})
    result = execute(
        {"plan_id": "plan-rag", "plan": [{"agent": "legal", "reason": "review legal"}]},
        state,
        agent_registry={"legal": lambda payload: LEGAL_OUTPUT},
    )

    trace_rag = result["execution_trace"][0]["rag"]
    assert trace_rag["count"] == len(trace_rag["sources"])
    assert len(trace_rag["scores"]) == len(trace_rag["chunks"])
    assert len(trace_rag["rerank_scores"]) == len(trace_rag["chunks"])
    assert trace_rag == rag_info


def test_dynamic_rag_trace_does_not_affect_other_agents(monkeypatch):
    monkeypatch.setattr(
        "backend.core.executor.legal_agent.get_last_rag_info",
        lambda: _rag_info(["food_safety.md"]),
    )

    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())

    for item in result["execution_trace"]:
        if item["agent"] == "legal":
            assert "rag" in item
        else:
            assert "rag" not in item


def test_dynamic_api_fields_still_exist_with_rag_trace(monkeypatch):
    store = {}
    rag_info = _rag_info(["food_safety.md"])

    def save(state):
        store[state.session_id] = state.to_dict()
        return store[state.session_id]

    def load(session_id):
        data = store.get(session_id)
        if data is None:
            return None
        return AgentState.from_dict(data)

    monkeypatch.setattr("backend.main.save_checkpoint", save)
    monkeypatch.setattr("backend.main.load_checkpoint", load)
    monkeypatch.setattr(
        "backend.main.run_dynamic_agent",
        lambda event: {
            "session_id": "session-api-rag",
            "plan_id": "plan-api-rag",
            "event": event,
            "planner_input": {"event": event, "category": "food_safety", "risk_level": "high"},
            "raw_plan": {"plan_id": "raw", "plan": []},
            "validated_plan": {"plan_id": "plan-api-rag", "plan": []},
            "executed_agents": ["legal"],
            "results": {"legal": LEGAL_OUTPUT},
            "failed_agents": [],
            "execution_trace": [
                {
                    "agent": "legal",
                    "reason": "review legal",
                    "start_time": "2026-08-06T00:00:00+00:00",
                    "end_time": "2026-08-06T00:00:00.100000+00:00",
                    "status": "success",
                    "output": LEGAL_OUTPUT,
                    "error": None,
                    "rag": rag_info,
                }
            ],
        },
    )
    monkeypatch.setattr("backend.main.evaluate_runtime_state", lambda state: {"passed": True, "issues": []})
    monkeypatch.setattr(
        "backend.main.evaluate_human_policy",
        lambda state, evaluation: {"required": False, "reason": "", "triggers": []},
    )

    response = _request("POST", "/api/dynamic/run", json={"event": TEST_EVENT})

    assert response.status_code == 200
    body = response.json()
    assert "session_id" in body
    assert "results" in body
    assert "execution_trace" in body
    assert "status" in body
    assert body["execution_trace"][0]["rag"]["sources"] == ["food_safety.md"]


def _request(method: str, url: str, json: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json)

    return asyncio.run(send_request())
