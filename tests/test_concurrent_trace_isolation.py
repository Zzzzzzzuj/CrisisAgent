from concurrent.futures import ThreadPoolExecutor

from backend.core.executor import execute
from backend.core.state import AgentState


def test_concurrent_sessions_keep_rag_and_llm_trace_isolated():
    def run_session(session_id: str, source: str, model: str) -> AgentState:
        state = AgentState(session_id=session_id, plan_id="plan", event=f"event {session_id}")
        state.set_result("writer", {"statement": f"draft {session_id}"})
        state.set_result("redteam", {"issues": [], "suggestions": []})

        def legal_runner(payload):
            return {
                "legal_risks": [],
                "safe_points": [f"safe {session_id}"],
                "revision_advice": [],
                "public_opinion_suggestions": [],
                "integrated_revision_tasks": [],
                "legal_safety_score_hint": 8,
                "review_summary": f"summary {session_id}",
                "_metadata": {
                    "rag": {
                        "rag_used": True,
                        "retrieval_backend": "db",
                        "retrieval_query": f"query {session_id}",
                        "sources": [source],
                        "evidence_chunks": [
                            {
                                "chunk_id": f"chunk-{session_id}",
                                "document_id": f"doc-{session_id}",
                                "document_version": 1,
                                "source_category": "food_safety",
                                "score": 0.8,
                                "rerank_score": 0.9,
                                "text_preview": f"evidence {session_id}",
                            }
                        ],
                        "fallback_used": False,
                    },
                    "llm": {
                        "provider": "openai_compatible",
                        "model": model,
                        "agent_name": "Agent B",
                        "success": True,
                        "fallback_used": False,
                    },
                },
            }

        execute(
            {"plan_id": "plan", "plan": [{"agent": "legal", "reason": "review"}]},
            state,
            agent_registry={"legal": legal_runner},
        )
        return state

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_session, "session-a", "food_safety.md", "model-a"),
            pool.submit(run_session, "session-b", "data_privacy.md", "model-b"),
        ]
        first, second = [future.result() for future in futures]

    first_trace = first.trace[0]
    second_trace = second.trace[0]

    assert first_trace["rag"]["sources"] == ["food_safety.md"]
    assert second_trace["rag"]["sources"] == ["data_privacy.md"]
    assert first_trace["rag"]["evidence_chunks"][0]["document_id"] == "doc-session-a"
    assert second_trace["rag"]["evidence_chunks"][0]["document_id"] == "doc-session-b"
    assert first_trace["llm"]["model"] == "model-a"
    assert second_trace["llm"]["model"] == "model-b"
    assert first.session_id == "session-a"
    assert second.session_id == "session-b"
    assert "_metadata" not in first.get_result("legal")
    assert "_metadata" not in second.get_result("legal")


def test_fallback_metadata_stays_on_current_trace_only():
    first = _run_failed_metadata_session("session-fallback-a", "invalid_json")
    second = _run_failed_metadata_session("session-fallback-b", "timeout")

    assert first.trace[0]["llm"]["failure_type"] == "invalid_json"
    assert second.trace[0]["llm"]["failure_type"] == "timeout"
    assert first.trace[0]["llm"]["fallback_used"] is True
    assert second.trace[0]["llm"]["fallback_used"] is True
    assert first.trace[0]["rag"]["retrieval_query"] == "query session-fallback-a"
    assert second.trace[0]["rag"]["retrieval_query"] == "query session-fallback-b"


def _run_failed_metadata_session(session_id: str, failure_type: str) -> AgentState:
    state = AgentState(session_id=session_id, plan_id="plan", event=f"event {session_id}")
    state.set_result("writer", {"statement": "draft"})
    state.set_result("redteam", {"issues": [], "suggestions": []})

    def legal_runner(payload):
        return {
            "legal_risks": ["fallback risk"],
            "safe_points": [],
            "revision_advice": [],
            "public_opinion_suggestions": [],
            "integrated_revision_tasks": [],
            "legal_safety_score_hint": 7,
            "review_summary": "fallback",
            "_metadata": {
                "rag": {
                    "rag_used": False,
                    "retrieval_backend": "none",
                    "retrieval_query": f"query {session_id}",
                    "evidence_chunks": [],
                    "fallback_used": False,
                },
                "llm": {
                    "success": False,
                    "failure_type": failure_type,
                    "fallback_used": True,
                },
            },
        }

    execute(
        {"plan_id": "plan", "plan": [{"agent": "legal", "reason": "review"}]},
        state,
        agent_registry={"legal": legal_runner},
    )
    return state
