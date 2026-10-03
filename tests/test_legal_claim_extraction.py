import json

import pytest

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


def _business_result(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "claim_extraction_telemetry"}


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
    result = legal_claim_extractor.extract_claims("  ", "llm", lambda _: 1 / 0)
    assert _business_result(result) == {
        "legal_claims": [], "claim_extraction_status": "ok"
    }
    assert result["claim_extraction_telemetry"]["provider_status"] == "NOT_CALLED"


def test_high_risk_event_gap_is_added_as_case_fact_without_domain_keywords():
    event = "某互联网平台出现异常。社交平台流传相关截图。目前尚未确认数据是否真实泄露、涉及多少用户以及泄露原因。"
    result = legal_claim_extractor.extract_claims(
        "我们已关注到相关反馈，并将持续调查。", "mock", event=event, risk_level="high"
    )
    assert result["legal_claims"] == [{
        "claim": "数据是否真实泄露、涉及多少用户以及泄露原因",
        "requires_legal_rule": False,
        "requires_case_fact": True,
        "claim_origin": "event_fact_gap",
    }]
    assert result["event_fact_gap_detection"] == {
        "status": "deterministic_offline_rule",
        "candidate_count": 1,
        "reason": "explicit_material_uncertainty",
        "risk_level": "high",
    }


@pytest.mark.parametrize("event,risk", [
    ("平台正在改进服务，相关情况仍需关注。", "high"),
    ("某平台服务中断，尚未确认影响范围和故障原因。", "medium"),
])
def test_event_gap_requires_explicit_material_unknown(event, risk):
    result = legal_claim_extractor.extract_claims(
        "我们重视用户反馈，将持续跟进。", "mock", event=event, risk_level=risk
    )
    if risk == "high":
        assert result["legal_claims"] == []
        assert result["event_fact_gap_detection"]["candidate_count"] == 0
    else:
        assert len(result["legal_claims"]) == 1
        assert result["legal_claims"][0]["claim_origin"] == "event_fact_gap"


def test_same_explicit_gap_is_detected_independently_of_risk_level():
    event = "平台服务中断，尚未确认影响范围和故障原因。"
    outputs = [legal_claim_extractor.extract_claims(
        "我们正在核查。", "mock", event=event, risk_level=risk
    )["legal_claims"] for risk in ("low", "medium", "high")]
    assert outputs[0] == outputs[1] == outputs[2]


def test_event_gap_detection_uses_generic_unknown_dimensions_not_case_terms():
    event = "某机构遇到异常，目前尚未确认涉及范围及发生原因。"
    result = legal_claim_extractor.extract_claims("我们正在核查。", "mock", event=event, risk_level="low")
    assert result["legal_claims"][0]["claim_origin"] == "event_fact_gap"
    assert result["legal_claims"][0]["claim"] == "涉及范围及发生原因"


def test_event_gap_rule_generalizes_to_food_safety_and_service_outage():
    for event in (
        "某食品品牌受到关注。目前尚未确认涉事批次是否使用相关原料。",
        "某平台服务中断。目前尚未确认故障原因以及影响范围。",
    ):
        result = legal_claim_extractor.extract_claims("我们正在跟进。", "mock",
                                                       event=event, risk_level="high")
        assert len(result["legal_claims"]) == 1
        assert result["legal_claims"][0]["claim_origin"] == "event_fact_gap"
        assert result["legal_claims"][0]["requires_case_fact"] is True


def test_llm_parses_valid_claims_and_deduplicates():
    draft = "目前不存在违法行为"
    item = {"claim": draft, "requires_legal_rule": True, "requires_case_fact": True}
    result = legal_claim_extractor.extract_claims(
        draft, "llm", lambda prompt: json.dumps({"claims": [item, item]}, ensure_ascii=False)
    )
    assert _business_result(result) == {"legal_claims": [item], "claim_extraction_status": "ok"}
    assert result["claim_extraction_telemetry"] == {
        "claim_extraction_called": True,
        "provider_status": "SUCCESS",
        "parse_status": "SUCCESS",
        "schema_status": "SUCCESS",
        "validation_status": "SUCCESS",
        "raw_item_count": 2,
        "accepted_item_count": 1,
        "dropped_item_count": 1,
        "fallback_used": False,
        "failure_stage": "NONE",
        "reason_code": "NONE",
    }


def test_llm_empty_claims_is_observed_without_fallback():
    result = legal_claim_extractor.extract_claims(
        "普通表达，没有需要核验的承诺。", "llm",
        lambda _: json.dumps({"claims": []}, ensure_ascii=False),
    )
    telemetry = result["claim_extraction_telemetry"]
    assert result["legal_claims"] == []
    assert result["claim_extraction_status"] == "ok"
    assert telemetry["provider_status"] == "SUCCESS"
    assert telemetry["parse_status"] == telemetry["schema_status"] == "SUCCESS"
    assert telemetry["raw_item_count"] == telemetry["accepted_item_count"] == 0
    assert telemetry["fallback_used"] is False
    assert telemetry["failure_stage"] == "NONE"
    assert telemetry["reason_code"] == "EMPTY_MODEL_CLAIMS"


def test_llm_parse_failure_telemetry_preserves_fallback_and_business_result():
    draft = "目前不存在违法行为"
    result = legal_claim_extractor.extract_claims(draft, "llm", lambda _: "PRIVATE_RAW_RESPONSE not json")
    telemetry = result["claim_extraction_telemetry"]
    assert _business_result(result)["claim_extraction_status"] == "fallback"
    assert len(result["legal_claims"]) == 1
    assert telemetry["provider_status"] == "SUCCESS"
    assert telemetry["parse_status"] == "ERROR"
    assert telemetry["schema_status"] == "NOT_ATTEMPTED"
    assert telemetry["fallback_used"] is True
    assert telemetry["failure_stage"] == "PARSE"
    assert telemetry["reason_code"] == "JSON_PARSE_ERROR"
    assert telemetry["accepted_item_count"] == 1
    assert telemetry["dropped_item_count"] is None
    assert "PRIVATE_RAW_RESPONSE" not in json.dumps(telemetry)


def test_llm_schema_failure_telemetry_identifies_schema_stage():
    result = legal_claim_extractor.extract_claims(
        "经调查，本批次没有使用过期原料", "llm",
        lambda _: '{"claims":[{"claim":"经调查，本批次没有使用过期原料","requires_case_fact":true}]}',
    )
    telemetry = result["claim_extraction_telemetry"]
    assert telemetry["provider_status"] == "SUCCESS"
    assert telemetry["parse_status"] == "SUCCESS"
    assert telemetry["schema_status"] == "ERROR"
    assert telemetry["validation_status"] == "NOT_ATTEMPTED"
    assert telemetry["fallback_used"] is True
    assert telemetry["failure_stage"] == "SCHEMA"
    assert telemetry["reason_code"] == "SCHEMA_VALIDATION_ERROR"


def test_llm_claim_validation_failure_telemetry_identifies_validation_stage():
    result = legal_claim_extractor.extract_claims(
        "目前不存在违法行为", "llm",
        lambda _: json.dumps({"claims": [{"claim": "不相关的私有文本", "requires_legal_rule": True,
                                           "requires_case_fact": False}]}, ensure_ascii=False),
    )
    telemetry = result["claim_extraction_telemetry"]
    assert telemetry["schema_status"] == "SUCCESS"
    assert telemetry["validation_status"] == "ERROR"
    assert telemetry["fallback_used"] is True
    assert telemetry["failure_stage"] == "VALIDATION"
    assert telemetry["reason_code"] == "CLAIM_VALIDATION_ERROR"
    assert "不相关的私有文本" not in json.dumps(telemetry, ensure_ascii=False)


def test_llm_provider_failure_and_timeout_are_distinguished():
    def provider_error(_):
        raise RuntimeError("PRIVATE_PROVIDER_BODY")

    def provider_timeout(_):
        raise TimeoutError("PRIVATE_TIMEOUT_BODY")

    def llm_client_wrapped_timeout(_):
        raise RuntimeError("LLM chat request timed out.")

    error_result = legal_claim_extractor.extract_claims("目前不存在违法行为", "llm", provider_error)
    timeout_result = legal_claim_extractor.extract_claims("目前不存在违法行为", "llm", provider_timeout)
    wrapped_timeout_result = legal_claim_extractor.extract_claims(
        "目前不存在违法行为", "llm", llm_client_wrapped_timeout
    )
    error_telemetry = error_result["claim_extraction_telemetry"]
    timeout_telemetry = timeout_result["claim_extraction_telemetry"]
    wrapped_timeout_telemetry = wrapped_timeout_result["claim_extraction_telemetry"]
    assert (error_telemetry["provider_status"], error_telemetry["failure_stage"],
            error_telemetry["reason_code"], error_telemetry["fallback_used"]) == (
                "ERROR", "PROVIDER", "PROVIDER_ERROR", True)
    assert (timeout_telemetry["provider_status"], timeout_telemetry["failure_stage"],
            timeout_telemetry["reason_code"], timeout_telemetry["fallback_used"]) == (
                "TIMEOUT", "PROVIDER", "PROVIDER_TIMEOUT", True)
    assert (wrapped_timeout_telemetry["provider_status"], wrapped_timeout_telemetry["failure_stage"],
            wrapped_timeout_telemetry["reason_code"]) == (
                "TIMEOUT", "PROVIDER", "PROVIDER_TIMEOUT")
    for telemetry in (error_telemetry, timeout_telemetry, wrapped_timeout_telemetry):
        assert telemetry["parse_status"] == telemetry["schema_status"] == "NOT_ATTEMPTED"
        assert telemetry["raw_item_count"] is None
        assert telemetry["dropped_item_count"] is None
        assert "PRIVATE_" not in json.dumps(telemetry)


def test_claim_extraction_telemetry_has_no_business_or_provider_content():
    private_event = "PRIVATE_EVENT_BODY 尚未确认影响范围以及发生原因"
    private_draft = "PRIVATE_DRAFT_BODY 目前不存在违法行为"
    private_response = "PRIVATE_PROVIDER_RESPONSE_BODY"
    private_key = "sk-PRIVATE-KEY"

    result = legal_claim_extractor.extract_claims(
        private_draft, "llm", lambda _: private_response,
        event=private_event, risk_level="high",
    )
    telemetry = result["claim_extraction_telemetry"]
    serialized = json.dumps(telemetry, ensure_ascii=False)
    for private_value in (private_event, private_draft, private_response, private_key,
                          "Prompt", "Authorization", "PRIVATE_PROVIDER"):
        assert private_value not in serialized


def test_claim_extraction_telemetry_does_not_change_claim_output():
    draft = "目前不存在违法行为"
    expected = {"legal_claims": [{"claim": draft, "requires_legal_rule": True,
                                  "requires_case_fact": True}], "claim_extraction_status": "ok"}
    result = legal_claim_extractor.extract_claims(
        draft, "llm", lambda _: json.dumps({"claims": [expected["legal_claims"][0]]}, ensure_ascii=False)
    )
    assert _business_result(result) == expected


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
    assert _business_result(result) == {"legal_claims": [], "claim_extraction_status": "fallback"}


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
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
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
    assert isinstance(legal_trace["rag"]["claim_summaries"], list)
    saved = get_session(response.session_id)
    assert len(legal_trace["rag"]["claim_summaries"]) == len(saved["legal_claim_extraction"]["legal_claims"])
    assert all("claim" not in item for item in legal_trace["rag"]["claim_summaries"])


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
    assert result["execution_trace"][0]["rag"]["claim_extraction_telemetry"]["provider_status"] == "NOT_CALLED"
