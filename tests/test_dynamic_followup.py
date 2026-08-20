import asyncio

import httpx

from backend.core.dynamic_runtime import run_dynamic_agent
from backend.core.state import AgentState
from backend.main import app


def _request(method: str, url: str, json: dict | None = None):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, json=json)

    return asyncio.run(send_request())


def _patch_checkpoint(monkeypatch):
    store = {}

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
    return store


def test_dynamic_runtime_result_includes_reasoning_mode_metadata():
    result = run_dynamic_agent("用户反馈商品包装轻微破损，希望客服处理。", agent_registry=_fake_registry())

    assert result["selected_reasoning_mode"] in {"fast", "standard", "strict"}
    assert "reasoning_mode_reason" in result
    assert "recommended_execution_policy" in result


def test_followup_uses_existing_session_state_and_rag_evidence(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = _state_with_final_statement()
    store[state.session_id] = state.to_dict()

    response = _request(
        "POST",
        f"/api/dynamic/{state.session_id}/followup",
        json={
            "question": "如果媒体追问下一步怎么办？",
            "followup_type": "media_qna",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == state.session_id
    assert body["mode"] == "mock"
    assert body["used_session_state"] is True
    assert body["context_summary"]["final_statement_present"] is True
    assert body["context_summary"]["rag_evidence_count"] == 1
    assert "媒体问答建议" in body["answer"]


def test_followup_rejects_missing_question(monkeypatch):
    store = _patch_checkpoint(monkeypatch)
    state = _state_with_final_statement()
    store[state.session_id] = state.to_dict()

    response = _request(
        "POST",
        f"/api/dynamic/{state.session_id}/followup",
        json={"question": "", "followup_type": "clarification"},
    )

    assert response.status_code == 422
    assert "question" in response.json()["detail"]


def test_followup_missing_session_returns_404(monkeypatch):
    _patch_checkpoint(monkeypatch)

    response = _request(
        "POST",
        "/api/dynamic/missing/followup",
        json={"question": "怎么回应？", "followup_type": "rewrite"},
    )

    assert response.status_code == 404


def _state_with_final_statement() -> AgentState:
    state = AgentState(
        session_id="followup-session",
        plan_id="plan-followup",
        event="某食品品牌被曝光使用过期原料，消费者要求监管介入。",
    )
    state.set_result(
        "decision",
        {
            "final_statement": "我们已启动核查并将及时公开进展。",
            "scores": {"legal_safety": 8, "empathy": 8, "robustness": 8},
        },
    )
    state.trace = [
        {
            "agent": "legal",
            "status": "success",
            "rag": {
                "evidence_chunks": [
                    {
                        "source": "food_safety.md",
                        "source_category": "food_safety",
                        "text_preview": "食品安全事件应先核查批次并配合监管。",
                    }
                ]
            },
        }
    ]
    return state


def _fake_registry():
    return {
        "sentiment": lambda event: {"risk_level": "low", "public_emotion": "calm"},
        "writer": lambda payload: {"statement": "draft"},
        "redteam": lambda payload: {"issues": [], "suggestions": []},
        "legal": lambda payload: {"legal_risks": [], "safe_points": []},
        "writer_v2": lambda payload: {"statement": "second draft"},
        "decision": lambda payload: {
            "final_statement": "final",
            "scores": {"legal_safety": 8, "empathy": 8, "robustness": 8},
        },
    }
