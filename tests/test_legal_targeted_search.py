from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from backend.agents import legal_agent
from backend.agents.legal_action_policy import (
    CONTINUE, REQUEST_HUMAN_FACT_VERIFICATION, STOP_UNRESOLVED,
    TARGETED_LEGAL_SEARCH, recommend_legal_actions,
)
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_claim_relation import build_legal_claim_relations
from backend.agents.legal_targeted_search import execute_recommended_targeted_search
from backend.core.executor import _collect_trace_metadata
from backend.core.policy import evaluate_human_policy
from backend.core.state import AgentState
from backend.workflow import _record_step
from evaluation.legal_targeted_loop import run_legal_targeted_loop_eval


CLAIM = "使用过期食品原料可能违反食品安全规定"
BROAD_QUERY = "事件：食品投诉；声明草稿：完整长篇声明；红队：完整批评文本"
RULE = {"chunk_id": "rule", "source": "food-law", "text": "食品生产经营者不得使用超过保质期的食品原料。"}
GUIDANCE = {"chunk_id": "guidance", "source": "pr-guide", "text": "建议及时向公众说明核查进展。",
            "score": 0.99, "rerank_score": 0.99}


def inputs(claims=None, relations=None):
    claims = claims or [{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": False}]
    extraction = {"legal_claims": claims, "claim_extraction_status": "ok"}
    relation = relations or {"legal_claim_relations": [
        {"claim_index": i, "evidence_ref": "guidance", "relation": "no_rule_match"}
        for i in range(len(claims))], "relation_status": "ok"}
    coverage = build_claim_coverage(claims, relation)
    rag = {"query": BROAD_QUERY, "retrieval_status": "executed_with_hits",
           "retrieval_executed": True, "fallback_used": False}
    recommendation = recommend_legal_actions(extraction, coverage, relation, rag)
    return extraction, coverage, relation, recommendation, rag


@pytest.mark.parametrize("action", [CONTINUE, REQUEST_HUMAN_FACT_VERIFICATION, STOP_UNRESOLVED])
def test_non_targeted_recommendations_never_search(action):
    args = list(inputs())
    args[3] = {"claim_action_recommendations": [{"claim_index": 0, "recommended_action": action}]}
    result = execute_recommended_targeted_search(*args, retrieve_call=lambda *_a, **_kw: pytest.fail("retrieved"))
    assert result == {"targeted_search_executions": []}


def test_one_minimum_index_and_distinct_query():
    args = inputs(claims=[{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": False},
                          {"claim": "产品召回可能违反规定", "requires_legal_rule": True,
                           "requires_case_fact": False}])
    calls = []

    def fake_retrieve(query, top_k):
        calls.append((query, top_k))
        return {"chunks": [RULE], "sources": []}

    before = deepcopy(args)
    result = execute_recommended_targeted_search(*args, retrieve_call=fake_retrieve)
    row = result["targeted_search_executions"][0]
    assert len(calls) == 1 and calls[0][1] == 3
    assert row["claim_index"] == 0 and row["round"] == 1
    assert row["query"] != BROAD_QUERY and CLAIM in row["query"]
    assert "完整长篇声明" not in row["query"] and "完整批评文本" not in row["query"]
    assert row["before_legal_rule_status"] == "no_candidate"
    assert row["after_legal_rule_status"] == "candidate_found"
    assert row["next_recommended_action"] == CONTINUE
    assert row["targeted_evidence_refs"] == ["rule"]
    assert args == before


def test_no_improvement_and_no_round_two():
    calls = []

    def fake_retrieve(query, top_k):
        calls.append(query)
        return {"chunks": [GUIDANCE]}

    result = execute_recommended_targeted_search(*inputs(), retrieve_call=fake_retrieve)
    row = result["targeted_search_executions"][0]
    assert len(calls) == 1
    assert row["after_legal_rule_status"] == "no_candidate"
    assert row["next_recommended_action"] == TARGETED_LEGAL_SEARCH
    assert row["stop_reason"] == "round_limit_reached"


def test_high_scores_do_not_create_candidate():
    row = execute_recommended_targeted_search(
        *inputs(), retrieve_call=lambda *_a, **_kw: {"chunks": [GUIDANCE]},
    )["targeted_search_executions"][0]
    assert row["after_legal_rule_status"] == "no_candidate"


@pytest.mark.parametrize("result,status", [({"chunks": []}, "no_hit"),
                                            ({"chunks": [RULE], "fallback_used": True}, "fallback")])
def test_empty_and_fallback_stop_conservatively(result, status):
    row = execute_recommended_targeted_search(
        *inputs(), retrieve_call=lambda *_a, **_kw: result,
    )["targeted_search_executions"][0]
    assert row["status"] == status
    assert row["after_legal_rule_status"] == "uncertain"


def test_retrieval_exception_and_relation_failure_do_not_escape():
    def broken(*_args, **_kwargs):
        raise RuntimeError("offline failure")

    failed = execute_recommended_targeted_search(*inputs(), retrieve_call=broken)
    assert failed["targeted_search_executions"][0]["status"] == "failed"
    failed_relation = execute_recommended_targeted_search(
        *inputs(), retrieve_call=lambda *_a, **_kw: {"chunks": [RULE]}, relation_call=broken,
    )
    assert failed_relation["targeted_search_executions"][0]["after_legal_rule_status"] == "uncertain"


def test_p31a_relation_is_required_for_coverage_change():
    relation_calls = []

    def relation(claims, chunks, **kwargs):
        relation_calls.append((claims, chunks))
        return build_legal_claim_relations(claims, chunks, **kwargs)

    row = execute_recommended_targeted_search(
        *inputs(), retrieve_call=lambda *_a, **_kw: {"chunks": [RULE]}, relation_call=relation,
    )["targeted_search_executions"][0]
    assert len(relation_calls) == 1 and relation_calls[0][0][0]["claim"] == CLAIM
    assert row["after_legal_rule_status"] == "candidate_found"


def test_legal_metadata_shadow_does_not_change_output_or_original_observation(monkeypatch):
    extraction, coverage, relation, recommendation, rag = inputs()
    monkeypatch.setattr(legal_agent, "get_last_rag_info", lambda: rag)
    monkeypatch.setattr(legal_agent, "retrieve", lambda *_a, **_kw: {"chunks": [RULE]})
    monkeypatch.setattr(legal_agent, "call_llm", lambda _prompt: json.dumps({"relations": [
        {"claim_index": 0, "evidence_ref": "rule", "relation": "candidate_rule_relevant"}]}))
    legal_agent._RELATION_CONTEXT.set(relation)
    output = {"legal_risks": ["review"], "revision_advice": ["caution"]}
    result = legal_agent._attach_metadata(output, claim_extraction=extraction, allow_targeted_search=True)
    assert output == {"legal_risks": ["review"], "revision_advice": ["caution"]}
    assert result["legal_risks"] == output["legal_risks"]
    assert result["_metadata"]["claim_coverage"] == coverage
    assert result["_metadata"]["claim_action_recommendation"] == recommendation
    assert result["_metadata"]["targeted_legal_search"]["targeted_search_executions"][0]["after_legal_rule_status"] == "candidate_found"


def test_fixed_loop_regression_is_reproducible_and_not_legal_accuracy():
    first = run_legal_targeted_loop_eval()
    assert first == run_legal_targeted_loop_eval()
    assert first["dataset_kind"] == "fixed_fake_retriever_regression"
    assert first["eligible_targeted_search_cases"] == 6
    assert first["targeted_searches_executed"] == 6
    assert first["coverage_improved_count"] == 2
    assert first["unchanged_count"] + first["degraded_or_uncertain_count"] + first["coverage_improved_count"] == 6


def test_llm_path_searches_after_original_prompt_and_keeps_business_output(monkeypatch):
    monkeypatch.setattr(legal_agent, "get_config", lambda: SimpleNamespace(agent_mode="llm"))
    monkeypatch.setattr(legal_agent, "_is_rag_enabled", lambda: True)
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **_kw: {"need_rag": True})
    searches = []
    prompts = []

    def fake_retrieve(query, top_k):
        searches.append(query)
        chunk = GUIDANCE if len(searches) == 1 else RULE
        return {"chunks": [chunk], "sources": [{"source": chunk["source"]}],
                "context": chunk["text"]}

    def fake_llm(prompt):
        prompts.append(prompt)
        if "从下面的声明草稿" in prompt:
            return json.dumps({"claims": [{"claim": CLAIM, "requires_legal_rule": True,
                                           "requires_case_fact": False}]}, ensure_ascii=False)
        if "只判断候选规则文本" in prompt:
            ref = "guidance" if "guidance" in prompt else "rule"
            return json.dumps({"relations": [{"claim_index": 0, "evidence_ref": ref,
                                               "relation": "no_rule_match" if ref == "guidance"
                                               else "candidate_rule_relevant"}]})
        return json.dumps({"legal_risks": ["审慎"], "safe_points": ["稳妥"],
                           "revision_advice": ["核查"], "public_opinion_suggestions": [],
                           "integrated_revision_tasks": ["修订"]}, ensure_ascii=False)

    monkeypatch.setattr(legal_agent, "retrieve", fake_retrieve)
    monkeypatch.setattr(legal_agent, "call_llm", fake_llm)
    output = legal_agent.run({"event": "食品投诉", "draft": CLAIM,
                              "redteam_review": {"suggestions": []}})
    assert len(searches) == 2 and searches[0] != searches[1]
    assert "相关法律规定" in searches[1] and "食品投诉" not in searches[1]
    legal_prompt = next(prompt for prompt in prompts if "你是 CrisisAgent 的合规审查" in prompt)
    assert legal_prompt == prompts[-2]
    assert RULE["text"] not in legal_prompt
    assert output["legal_risks"] == ["审慎"]
    assert output["_metadata"]["claim_coverage"]["claim_coverage"][0]["legal_rule_status"] == "no_candidate"
    assert output["_metadata"]["targeted_legal_search"]["targeted_search_executions"][0]["after_legal_rule_status"] == "candidate_found"


def test_shadow_action_is_traceable_without_changing_review_or_downstream_output(monkeypatch):
    shadow = {"targeted_search_executions": [{"claim_index": 0, "executed_action": TARGETED_LEGAL_SEARCH,
                                               "before_legal_rule_status": "no_candidate",
                                               "after_legal_rule_status": "candidate_found"}]}
    original_rag = {"retrieval_status": "executed_with_hits", "evidence_quality": {
        "evaluated": True, "status": "pass", "should_trigger_human_review": False}}
    metadata = {"rag": original_rag, "targeted_legal_search": shadow}
    trace_metadata = _collect_trace_metadata("legal", metadata)
    assert trace_metadata["rag"]["targeted_search_executions"] == shadow["targeted_search_executions"]
    assert trace_metadata["rag"]["evidence_quality"] == original_rag["evidence_quality"]

    monkeypatch.setattr(legal_agent, "get_last_rag_info", lambda: original_rag)
    trace = []
    output = _record_step(
        trace, "Agent B", "合规审查 Agent", {"draft": CLAIM},
        runner=lambda _: {"legal_risks": ["原有风险"], "_metadata": metadata},
    )
    assert output == {"legal_risks": ["原有风险"]}
    assert trace[0].rag["targeted_search_executions"] == shadow["targeted_search_executions"]
    assert "targeted_search_executions" not in str(output)

    def review(with_shadow):
        state = AgentState(session_id="offline", plan_id="fixed", event="事件")
        rag = {**original_rag, **(shadow if with_shadow else {})}
        state.add_trace({"agent": "legal", "rag": rag})
        return evaluate_human_policy(state, {"passed": True})

    assert review(True) == review(False)
