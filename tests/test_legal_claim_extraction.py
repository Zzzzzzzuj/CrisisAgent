import json

from backend.agents import legal_agent
from backend.agents import legal_claim_extractor
from backend.config import get_config
from backend.core.executor import execute
from backend.core.state import AgentState
from backend.schemas import CrisisRunRequest
from backend.storage import get_session
from backend.workflow import run_crisis_workflow


def _extract(draft: str) -> list[dict]:
    result = legal_claim_extractor.extract_claims(draft, "mock")
    assert result["claim_extraction_status"] == "ok"
    return result["legal_claims"]


def test_mock_mixed_claim_needs_both_kinds_of_evidence():
    assert _extract("目前不存在违法行为") == [{
        "claim": "目前不存在违法行为",
        "requires_legal_rule": True,
        "requires_case_fact": True,
    }]


def test_mock_legal_rule_only_claim():
    assert _extract("使用超过保质期的食品原料可能违反相关食品安全规定") == [{
        "claim": "使用超过保质期的食品原料可能违反相关食品安全规定",
        "requires_legal_rule": True,
        "requires_case_fact": False,
    }]


def test_mock_case_fact_only_claim():
    assert _extract("经调查，本批次没有使用过期原料") == [{
        "claim": "经调查，本批次没有使用过期原料",
        "requires_legal_rule": False,
        "requires_case_fact": True,
    }]


def test_expressions_and_promises_are_not_extracted():
    assert _extract("我们对此深表歉意。我们将依法依规承担责任。") == []


def test_multiple_claims_and_duplicates():
    claims = _extract("目前不存在违法行为。经调查，本批次没有使用过期原料。"
                      "目前不存在违法行为。")
    assert len(claims) == 2
    assert claims[0]["requires_legal_rule"] is True
    assert claims[1]["requires_legal_rule"] is False


def test_empty_draft_does_not_call_llm():
    assert legal_claim_extractor.extract_claims("  ", "llm", lambda _: 1 / 0) == {
        "legal_claims": [], "claim_extraction_status": "ok"
    }


def test_llm_parses_valid_claims_and_deduplicates():
    draft = "目前不存在违法行为"
    item = {"claim": draft, "requires_legal_rule": True, "requires_case_fact": True}
    result = legal_claim_extractor.extract_claims(
        draft, "llm", lambda prompt: json.dumps({"claims": [item, item]}, ensure_ascii=False)
    )
    assert result == {"legal_claims": [item], "claim_extraction_status": "ok"}


def test_llm_invalid_json_falls_back_to_deterministic_rules():
    result = legal_claim_extractor.extract_claims("目前不存在违法行为", "llm", lambda _: "not json")
    assert result["claim_extraction_status"] == "fallback"
    assert result["legal_claims"][0]["requires_legal_rule"] is True
    assert result["legal_claims"][0]["requires_case_fact"] is True


def test_llm_missing_fields_falls_back_to_deterministic_rules():
    result = legal_claim_extractor.extract_claims(
        "经调查，本批次没有使用过期原料", "llm",
        lambda _: '{"claims":[{"claim":"经调查，本批次没有使用过期原料","requires_case_fact":true}]}',
    )
    assert result["claim_extraction_status"] == "fallback"
    assert result["legal_claims"][0]["requires_case_fact"] is True


def test_llm_cannot_turn_promise_into_claim():
    draft = "我们将依法依规承担责任"
    result = legal_claim_extractor.extract_claims(
        draft, "llm",
        lambda _: json.dumps({"claims": [{"claim": draft, "requires_legal_rule": True,
                                           "requires_case_fact": True}]}, ensure_ascii=False),
    )
    assert result == {"legal_claims": [], "claim_extraction_status": "fallback"}


def test_extraction_failure_does_not_break_legal_review(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    monkeypatch.setattr(legal_claim_extractor, "_extract_mock", lambda _: 1 / 0)
    result = legal_agent.run({"event": "食品安全投诉", "draft": "目前不存在违法行为", "redteam_review": {}})
    assert result["_metadata"]["claim_extraction"]["claim_extraction_status"] == "failed"
    assert "legal_risks" in result


def test_extraction_failure_does_not_break_fixed_workflow(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    monkeypatch.setattr(legal_claim_extractor, "_extract_mock", lambda _: 1 / 0)
    response = run_crisis_workflow(CrisisRunRequest(event="某食品品牌被曝使用过期原料"))
    trace = response.model_dump()["agent_trace"]
    assert len(trace) == 6
    assert trace[3]["rag"]["claim_extraction_status"] == "failed"
    assert trace[-1]["status"] == "success"


def test_existing_legal_rag_and_review_still_run_after_extraction_fallback(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    get_config.cache_clear()
    calls = {"retrieval": 0}
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: {"need_rag": True,
                                                                                  "reason": "legal issue"})

    def fake_retrieve(query, top_k=3):
        calls["retrieval"] += 1
        return {"context": "legal context", "sources": [], "chunks": []}

    def fake_llm(prompt):
        if "声明草稿：" in prompt:
            return "not json"
        return json.dumps({
            "legal_risks": [], "safe_points": ["safe"], "revision_advice": ["advice"],
            "public_opinion_suggestions": [], "integrated_revision_tasks": [],
        })

    monkeypatch.setattr(legal_agent, "retrieve", fake_retrieve)
    monkeypatch.setattr(legal_agent, "call_llm", fake_llm)
    result = legal_agent.run({"event": "食品安全投诉", "draft": "目前不存在违法行为", "redteam_review": {}})
    assert calls["retrieval"] == 1
    assert result["safe_points"] == ["safe"]
    assert result["_metadata"]["claim_extraction"]["claim_extraction_status"] == "fallback"
    assert legal_agent.get_last_rag_info()["evidence_quality"]["evaluated"] is True


def test_fixed_workflow_trace_and_session_record_claim_extraction(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    response = run_crisis_workflow(CrisisRunRequest(event="某食品品牌被曝使用过期原料"))
    legal_trace = response.model_dump()["agent_trace"][3]
    assert legal_trace["rag"]["claim_extraction_status"] == "ok"
    assert isinstance(legal_trace["rag"]["legal_claims"], list)
    saved = get_session(response.session_id)
    assert saved["legal_claim_extraction"]["legal_claims"] == legal_trace["rag"]["legal_claims"]


def test_dynamic_executor_state_and_trace_record_claim_extraction(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    state = AgentState("claim-test", "claim-plan", "某品牌食品安全投诉")
    state.set_result("writer", {"statement": "目前不存在违法行为"})
    result = execute({"plan_id": "claim-plan", "plan": [{"agent": "legal", "reason": "review"}]}, state)
    assert result["executed_agents"] == ["legal"]
    assert "_metadata" not in state.get_result("legal")
    assert state.metadata["legal_claim_extraction"]["legal_claims"][0] == {
        "claim": "目前不存在违法行为",
        "requires_legal_rule": True,
        "requires_case_fact": True,
    }
    assert result["execution_trace"][0]["rag"]["claim_extraction_status"] == "ok"
