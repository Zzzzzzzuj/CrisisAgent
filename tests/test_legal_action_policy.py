from copy import deepcopy

import pytest

from backend.agents import legal_agent
from backend.agents.legal_action_policy import recommend_legal_actions
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.config import get_config
from backend.core.executor import execute
from backend.core.policy import evaluate_human_policy
from backend.core.state import AgentState
from backend.schemas import CrisisRunRequest
from backend.storage import get_session
from backend.workflow import run_crisis_workflow


def _observation(*, relation="candidate_rule_relevant", legal=True, fact=False,
                 retrieval="executed_with_hits", relation_status="ok", reason=None,
                 fallback_used=False):
    claim = {"claim": "使用过期原料可能违反食品安全规定",
             "requires_legal_rule": legal, "requires_case_fact": fact}
    relations = [] if not legal or relation is None else [{
        "claim_index": 0, "evidence_ref": "rule-1", "relation": relation,
        **({"reason": reason} if reason else {}),
    }]
    extraction = {"legal_claims": [claim], "claim_extraction_status": "ok"}
    relation_result = {"legal_claim_relations": relations, "relation_status": relation_status}
    coverage = build_claim_coverage(extraction["legal_claims"], relation_result)
    rag = {"retrieval_status": retrieval, "retrieval_executed": retrieval.startswith("executed_"),
           "fallback_used": fallback_used}
    return extraction, coverage, relation_result, rag


def _recommend(**kwargs):
    return recommend_legal_actions(*_observation(**kwargs))["claim_action_recommendations"][0]


@pytest.mark.parametrize("input_options,action,reason", [
    ({}, "CONTINUE", "candidate_rule_available"),
    ({"relation": "no_rule_match"}, "TARGETED_LEGAL_SEARCH", "targeted_legal_search_may_improve_coverage"),
    ({"fact": True}, "REQUEST_HUMAN_FACT_VERIFICATION", "trusted_case_fact_unavailable"),
    ({"fact": True, "relation": "no_rule_match"}, "REQUEST_HUMAN_FACT_VERIFICATION", "trusted_case_fact_unavailable"),
    ({"legal": False, "fact": True, "relation": None}, "REQUEST_HUMAN_FACT_VERIFICATION", "trusted_case_fact_unavailable"),
    ({"relation": "uncertain", "reason": "claim_context_insufficient"}, "STOP_UNRESOLVED", "claim_context_insufficient"),
    ({"relation": "uncertain", "reason": "semantic_relation_unclear"}, "STOP_UNRESOLVED", "semantic_relation_unclear"),
    ({"relation": "uncertain", "relation_status": "fallback"}, "STOP_UNRESOLVED", "relation_module_failure"),
    ({"relation": "no_rule_match", "retrieval": "skipped_by_gate"}, "STOP_UNRESOLVED", "retrieval_not_completed"),
    ({"relation": "no_rule_match", "retrieval": "retrieval_error"}, "STOP_UNRESOLVED", "retrieval_not_completed"),
    ({"relation": "no_rule_match", "fallback_used": True}, "STOP_UNRESOLVED", "retrieval_fallback_used"),
    ({"relation": None, "retrieval": "executed_no_hit", "relation_status": "skipped"}, "STOP_UNRESOLVED", "retrieval_no_hit"),
    ({"relation": None, "retrieval": "disabled", "relation_status": "skipped"}, "STOP_UNRESOLVED", "retrieval_not_completed"),
    ({"relation": None, "retrieval": "not_started", "relation_status": "skipped"}, "STOP_UNRESOLVED", "retrieval_not_completed"),
])
def test_policy_matrix(input_options, action, reason):
    recommendation = _recommend(**input_options)
    assert recommendation == {"claim_index": 0, "recommended_action": action, "action_reason": reason}


@pytest.mark.parametrize("module_reason", ["invalid_output", "invalid_evidence_ref", "execution_error"])
def test_module_failure_does_not_become_evidence_gap(module_reason):
    extraction, coverage, relation, rag = _observation(relation="uncertain", relation_status="fallback")
    relation["relation_status_reason"] = module_reason
    result = recommend_legal_actions(extraction, coverage, relation, rag)
    assert result["claim_action_recommendations"][0]["recommended_action"] == "STOP_UNRESOLVED"
    assert result["claim_action_recommendations"][0]["action_reason"] == "relation_module_failure"


@pytest.mark.parametrize("untrusted", [
    {"event": "经调查，本批次未使用过期原料"},
    {"fact_status": "verified"},
    {"sources": [{"type": "news", "text": "未使用过期原料"}] * 3},
])
def test_external_claim_repetition_does_not_remove_human_fact_recommendation(untrusted):
    observation = _observation(fact=True, relation="no_rule_match")
    assert untrusted
    recommendation = recommend_legal_actions(*observation)["claim_action_recommendations"][0]
    assert recommendation["recommended_action"] == "REQUEST_HUMAN_FACT_VERIFICATION"


def test_p30_cannot_emit_a_claim_with_neither_requirement():
    extraction, coverage, relation, rag = _observation(legal=False, fact=False, relation=None)
    assert recommend_legal_actions(extraction, coverage, relation, rag)["claim_action_recommendations"][0] == {
        "claim_index": 0, "recommended_action": "STOP_UNRESOLVED",
        "action_reason": "observation_inconsistent",
    }


def test_missing_or_inconsistent_observation_cannot_recommend_search():
    extraction, coverage, relation, rag = _observation(relation="no_rule_match")
    coverage["claim_coverage"][0]["legal_rule_status"] = "candidate_found"
    assert recommend_legal_actions(extraction, coverage, relation, rag)["claim_action_recommendations"][0]["recommended_action"] == "STOP_UNRESOLVED"
    coverage["claim_coverage"][0]["legal_rule_status"] = "no_candidate"
    relation["legal_claim_relations"] = []
    assert recommend_legal_actions(extraction, coverage, relation, rag)["claim_action_recommendations"][0]["recommended_action"] == "STOP_UNRESOLVED"
    coverage["claim_coverage"] = []
    assert recommend_legal_actions(extraction, coverage, relation, rag)["claim_action_recommendations"][0]["recommended_action"] == "STOP_UNRESOLVED"


def test_status_alone_does_not_prove_retrieval_executed():
    extraction, coverage, relation, rag = _observation(relation="no_rule_match")
    rag["retrieval_executed"] = False
    result = recommend_legal_actions(extraction, coverage, relation, rag)["claim_action_recommendations"][0]
    assert result == {"claim_index": 0, "recommended_action": "STOP_UNRESOLVED",
                      "action_reason": "retrieval_not_completed"}


def test_uncertain_without_reason_stops_without_retrieval():
    assert _recommend(relation="uncertain")["action_reason"] == "uncertainty_unexplained"


def test_policy_is_deterministic_and_does_not_mutate_observation():
    observation = _observation(relation="no_rule_match")
    original = deepcopy(observation)
    assert recommend_legal_actions(*observation) == recommend_legal_actions(*observation)
    assert observation == original


def test_policy_empty_claims_does_not_invent_action():
    assert recommend_legal_actions({"legal_claims": []}, {"claim_coverage": []},
                                   {"legal_claim_relations": []}, {"retrieval_status": "not_started"}) == {
        "claim_action_recommendations": [],
    }


def test_mock_legal_policy_does_not_call_llm_or_retrieve(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    monkeypatch.setattr(legal_agent, "call_llm", lambda *_: pytest.fail("LLM must not run"))
    monkeypatch.setattr(legal_agent, "retrieve", lambda *_args, **_kwargs: pytest.fail("retrieval must not run"))
    result = legal_agent.run({"event": "食品安全投诉", "draft": "目前不存在违法行为", "redteam_review": {}})
    recommendation = result["_metadata"]["claim_action_recommendation"]["claim_action_recommendations"][0]
    assert recommendation["recommended_action"] == "REQUEST_HUMAN_FACT_VERIFICATION"


def test_recommendation_does_not_change_legal_output_or_prompt(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    payload = {"event": "食品安全投诉", "draft": "目前不存在违法行为", "redteam_review": {}}
    baseline = legal_agent.run(payload)
    prompt = legal_agent._build_legal_prompt(payload, "法规文本")
    monkeypatch.setattr(legal_agent, "recommend_legal_actions", lambda *_: {
        "claim_action_recommendations": [{"claim_index": 0, "recommended_action": "STOP_UNRESOLVED",
                                          "action_reason": "uncertainty_unexplained"}],
    })
    changed = legal_agent.run(payload)
    assert {key: value for key, value in baseline.items() if key != "_metadata"} == {
        key: value for key, value in changed.items() if key != "_metadata"
    }
    assert legal_agent._build_legal_prompt(payload, "法规文本") == prompt


def test_recommendation_does_not_change_human_review():
    state = AgentState("action-review", "plan", "食品安全投诉")
    before = evaluate_human_policy(state, {"passed": True})
    state.metadata["legal_claim_action_recommendation"] = {
        "claim_action_recommendations": [{"claim_index": 0, "recommended_action": "REQUEST_HUMAN_FACT_VERIFICATION",
                                          "action_reason": "trusted_case_fact_unavailable"}],
    }
    state.add_trace({"agent": "legal", "rag": state.metadata["legal_claim_action_recommendation"]})
    assert evaluate_human_policy(state, {"passed": True}) == before


def test_policy_failure_does_not_interrupt_fixed_workflow(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    monkeypatch.setattr(legal_agent, "recommend_legal_actions", lambda *_: 1 / 0)
    result = legal_agent.run({"event": "食品安全投诉", "draft": "目前不存在违法行为", "redteam_review": {}})
    assert result["_metadata"]["claim_action_recommendation"] == {
        "claim_action_recommendations": [], "recommendation_status": "fallback",
    }
    response = run_crisis_workflow(CrisisRunRequest(event="食品安全投诉"))
    assert len(response.agent_trace) == 6
    assert response.agent_trace[-1].status == "success"


def test_fixed_workflow_trace_and_session_record_recommendation(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    response = run_crisis_workflow(CrisisRunRequest(event="食品安全投诉"))
    rag = response.model_dump()["agent_trace"][3]["rag"]
    assert "claim_action_recommendations" in rag
    assert get_session(response.session_id)["legal_claim_action_recommendation"]["claim_action_recommendations"] == rag["claim_action_recommendations"]


def test_dynamic_state_and_trace_record_recommendation(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    state = AgentState("action-test", "plan", "食品安全投诉")
    state.set_result("writer", {"statement": "目前不存在违法行为"})
    result = execute({"plan_id": "plan", "plan": [{"agent": "legal", "reason": "review"}]}, state)
    assert result["executed_agents"] == ["legal"]
    assert result["execution_trace"][0]["rag"]["claim_action_recommendations"] == (
        state.metadata["legal_claim_action_recommendation"]["claim_action_recommendations"]
    )
