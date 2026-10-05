import json

from backend.agents.legal_targeted_search import _select_legal_action
from backend.llm.client import LLMClient, get_llm_trace_calls, legal_operation_scope, reset_last_llm_trace
from backend.llm.config import LLMConfig


def test_action_proposal_parse_failure_keeps_legal_operation_and_attempt_identity(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not-json"}}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("backend.llm.client.assert_external_model_call_allowed", lambda **kwargs: None)
    monkeypatch.setattr("backend.llm.client.httpx.Client", FakeClient)
    reset_last_llm_trace()
    client = LLMClient(config=LLMConfig(provider="openai_compatible", model="test-model",
                                        api_key="test-key", base_url="https://provider.invalid"),
                       max_retries=0)

    extraction = {"legal_claims": [{"claim": "fixture", "requires_case_fact": True,
                                    "requires_legal_rule": True}]}
    coverage = {"claim_coverage": [{"claim_index": 0, "case_fact_status": "unresolved",
                                    "legal_rule_status": "uncertain"}]}
    eligible = [
        {"action": "REQUEST_HUMAN_FACT", "target_claim_index": 0, "reason_code": "CASE_FACT_GAP"},
        {"action": "RETRIEVE_LEGAL_EVIDENCE", "target_claim_index": 0, "reason_code": "LEGAL_RULE_GAP"},
    ]
    _, decision = _select_legal_action(
        eligible, extraction, coverage, mode="llm",
        llm_call=lambda prompt: client.chat([{"role": "user", "content": prompt}], agent_name="Agent B"),
        previous_observation=None, relation={"legal_claim_relations": []}, rag_info={},
        attempted={}, requested_gaps=[], consumed_requests=[], round_index=0,
        max_rounds=3, tool_calls_used=0, max_calls=2, same_action_limit=2,
        risk_level="unknown",
    )

    assert decision["proposal_status"] == "INVALID_JSON"
    assert decision["proposal_fallback_used"] is True
    trace = get_llm_trace_calls()
    assert len(trace) == 1
    assert trace[0]["operation_type"] == "legal.action_proposal"
    assert trace[0]["llm_call_id"]
    assert trace[0]["operation_span_id"]
    assert decision["operation_span_id"] == trace[0]["operation_span_id"]
    assert decision["llm_call_id"] == trace[0]["llm_call_id"]
    assert trace[0]["attempts"] == [{
        "attempt_index": 0,
        "attempt_latency_ms": trace[0]["attempts"][0]["attempt_latency_ms"],
        "attempt_status": "SUCCESS",
    }]
    assert trace[0]["success"] is False
    assert trace[0]["fallback_used"] is True
    assert trace[0]["failure_type"] == "invalid_json"
    assert trace[0]["input_tokens"] == 8
    assert "not-json" not in json.dumps(trace)
    assert "test-key" not in json.dumps(trace)


def test_action_proposal_call_site_assigns_operation_scope(monkeypatch):
    from backend.agents import legal_targeted_search
    from backend.llm.client import _LEGAL_OPERATION_CONTEXT

    observed = []

    def proposal(_context, *, llm_call):
        observed.append(dict(_LEGAL_OPERATION_CONTEXT.get({})))
        return {"status": "ok", "proposal": {
            "action": "REQUEST_HUMAN_FACT", "reason_code": "CASE_FACT_GAP",
            "target_claim_index": 0,
        }}

    monkeypatch.setattr(legal_targeted_search, "request_legal_action_proposal", proposal)
    extraction = {"legal_claims": [{"claim": "fixture", "requires_case_fact": True,
                                    "requires_legal_rule": True}]}
    coverage = {"claim_coverage": [{"claim_index": 0, "case_fact_status": "unresolved",
                                    "legal_rule_status": "uncertain"}]}
    eligible = [
        {"action": "REQUEST_HUMAN_FACT", "target_claim_index": 0, "reason_code": "CASE_FACT_GAP"},
        {"action": "RETRIEVE_LEGAL_EVIDENCE", "target_claim_index": 0, "reason_code": "LEGAL_RULE_GAP"},
    ]
    selected, decision = _select_legal_action(
        eligible, extraction, coverage, mode="llm", llm_call=lambda _prompt: "{}",
        previous_observation=None, relation={"legal_claim_relations": []}, rag_info={},
        attempted={}, requested_gaps=[], consumed_requests=[], round_index=0,
        max_rounds=3, tool_calls_used=0, max_calls=2, same_action_limit=2,
        risk_level="unknown",
    )

    assert selected["action"] == "REQUEST_HUMAN_FACT"
    assert decision["proposal_called"] is True
    assert observed[0]["operation_type"] == "legal.action_proposal"
    assert observed[0]["operation_span_id"]
    assert decision["operation_span_id"] == observed[0]["operation_span_id"]
