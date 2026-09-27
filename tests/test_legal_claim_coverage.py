from copy import deepcopy

import pytest

from backend.agents import legal_agent
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.config import get_config
from backend.core.executor import execute
from backend.core.policy import evaluate_human_policy
from backend.core.state import AgentState
from backend.schemas import CrisisRunRequest
from backend.storage import get_session
from backend.workflow import run_crisis_workflow


def _claim(*, legal=True, fact=False):
    return {"claim": "当前声明", "requires_legal_rule": legal, "requires_case_fact": fact}


def _relation(value, index=0):
    return {"claim_index": index, "evidence_ref": "rule-1", "relation": value}


def _coverage(claims=None, rows=None, status="ok"):
    result = build_claim_coverage(
        [_claim()] if claims is None else claims,
        {"legal_claim_relations": [] if rows is None else rows, "relation_status": status},
    )
    return result["claim_coverage"]


def test_legal_rule_only_with_candidate():
    assert _coverage(rows=[_relation("candidate_rule_relevant")]) == [{
        "claim_index": 0, "legal_rule_status": "candidate_found", "case_fact_status": "not_required",
    }]


def test_case_fact_only_is_unresolved_without_legal_relation():
    assert _coverage(claims=[_claim(legal=False, fact=True)]) == [{
        "claim_index": 0, "legal_rule_status": "not_required", "case_fact_status": "unresolved",
        "case_fact_reason": "trusted_case_fact_unavailable",
    }]


def test_mixed_claim_keeps_rule_candidate_separate_from_case_fact():
    assert _coverage(claims=[_claim(fact=True)], rows=[_relation("candidate_rule_relevant")]) == [{
        "claim_index": 0, "legal_rule_status": "candidate_found", "case_fact_status": "unresolved",
        "case_fact_reason": "trusted_case_fact_unavailable",
    }]


def test_neither_requirement_has_no_coverage():
    assert _coverage(claims=[_claim(legal=False, fact=False)]) == [{
        "claim_index": 0, "legal_rule_status": "not_required", "case_fact_status": "not_required",
    }]


def test_only_no_rule_matches_means_no_candidate():
    assert _coverage(rows=[_relation("no_rule_match"),
                           {**_relation("no_rule_match"), "evidence_ref": "rule-2"}])[0]["legal_rule_status"] == "no_candidate"


@pytest.mark.parametrize("rows,status", [
    ([_relation("uncertain")], "ok"),
    ([_relation("no_rule_match"), _relation("uncertain")], "ok"),
    ([], "ok"),
    ([], "skipped"),
    ([_relation("candidate_rule_relevant")], "fallback"),
    ([_relation("candidate_rule_relevant", index=2)], "ok"),
    ([{"claim_index": 0, "evidence_ref": "", "relation": "candidate_rule_relevant"}], "ok"),
])
def test_uncertain_or_invalid_relations_never_claim_candidate(rows, status):
    assert _coverage(rows=rows, status=status)[0]["legal_rule_status"] == "uncertain"


def test_known_candidate_with_other_uncertain_evidence_is_still_only_a_candidate():
    rows = [_relation("candidate_rule_relevant"),
            {**_relation("uncertain"), "evidence_ref": "rule-2"}]
    assert _coverage(rows=rows)[0]["legal_rule_status"] == "candidate_found"


@pytest.mark.parametrize("untrusted_context", [
    {"event": "经调查，本批次没有使用过期原料"},
    {"sources": [{"type": "news", "content": "本批次没有使用过期原料"}]},
    {"fact_status": "verified"},
    {"sources": [{"type": "rss", "content": "没有使用过期原料"}] * 3},
    {"context_pack": {"facts": ["本批次没有使用过期原料"]}},
    {"redteam_review": {"issues": []}, "sentiment": {"risk_level": "low"}},
])
def test_untrusted_context_cannot_upgrade_case_fact(untrusted_context):
    claims = [_claim(legal=False, fact=True)]
    before = deepcopy(claims)
    row = _coverage(claims=claims)[0]
    assert untrusted_context
    assert row["case_fact_status"] == "unresolved"
    assert row["case_fact_reason"] == "trusted_case_fact_unavailable"
    assert claims == before


def test_deterministic_result_and_input_unchanged():
    claims = [_claim(fact=True)]
    relations = {"legal_claim_relations": [_relation("candidate_rule_relevant")], "relation_status": "ok"}
    original = deepcopy(relations)
    assert build_claim_coverage(claims, relations) == build_claim_coverage(claims, relations)
    assert relations == original


def test_mock_legal_coverage_does_not_call_llm(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    monkeypatch.setattr(legal_agent, "call_llm", lambda *_: pytest.fail("LLM must not run"))
    result = legal_agent.run({
        "event": "企业称已经查明事故原因", "draft": "目前不存在违法行为",
        "redteam_review": {}, "fact_status": "verified",
    })
    coverage = result["_metadata"]["claim_coverage"]["claim_coverage"][0]
    assert coverage["legal_rule_status"] == "uncertain"
    assert coverage["case_fact_status"] == "unresolved"
    assert "claim_coverage" not in result["review_summary"]


def test_coverage_exception_does_not_break_legal_workflow(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    monkeypatch.setattr(legal_agent, "build_claim_coverage", lambda *_: 1 / 0)
    result = legal_agent.run({"event": "食品投诉", "draft": "目前不存在违法行为", "redteam_review": {}})
    assert result["_metadata"]["claim_coverage"] == {"claim_coverage": []}
    assert "legal_risks" in result
    response = run_crisis_workflow(CrisisRunRequest(event="食品投诉"))
    assert len(response.agent_trace) == 6
    assert response.agent_trace[-1].status == "success"


def test_fixed_workflow_trace_and_session_keep_shadow_coverage(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    response = run_crisis_workflow(CrisisRunRequest(event="食品安全投诉"))
    rag = response.model_dump()["agent_trace"][3]["rag"]
    assert "claim_coverage" in rag
    assert get_session(response.session_id)["legal_claim_coverage"]["claim_coverage"] == rag["claim_coverage"]


def test_dynamic_state_and_trace_keep_shadow_coverage(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    state = AgentState("coverage-test", "plan", "食品安全投诉")
    state.set_result("writer", {"statement": "目前不存在违法行为"})
    result = execute({"plan_id": "plan", "plan": [{"agent": "legal", "reason": "review"}]}, state)
    assert result["executed_agents"] == ["legal"]
    assert state.metadata["legal_claim_coverage"]["claim_coverage"][0]["case_fact_status"] == "unresolved"
    assert result["execution_trace"][0]["rag"]["claim_coverage"] == state.metadata["legal_claim_coverage"]["claim_coverage"]


def test_legal_prompt_and_human_review_policy_ignore_coverage():
    payload = {"event": "食品投诉", "draft": "目前不存在违法行为", "redteam_review": {}}
    before_prompt = legal_agent._build_legal_prompt(payload, "法律资料")
    payload["claim_coverage"] = {"claim_coverage": [_coverage(claims=[_claim(fact=True)])[0]]}
    assert legal_agent._build_legal_prompt(payload, "法律资料") == before_prompt

    state = AgentState("coverage-review", "plan", "食品投诉")
    before_review = evaluate_human_policy(state, {"passed": True})
    state.metadata["legal_claim_coverage"] = payload["claim_coverage"]
    state.add_trace({"agent": "legal", "rag": {"claim_coverage": payload["claim_coverage"]["claim_coverage"]}})
    assert evaluate_human_policy(state, {"passed": True}) == before_review
