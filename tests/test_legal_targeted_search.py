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
from backend.agents.legal_targeted_search import (
    execute_recommended_targeted_search,
    run_legal_action_loop,
)
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


def test_action_loop_updates_observation_and_does_not_repeat_resolved_gap():
    args = inputs()
    calls = []

    def fake_retrieve(query, top_k):
        calls.append(query)
        return {"chunks": [RULE], "sources": []}

    result = run_legal_action_loop(*args[:3], args[4], retrieve_call=fake_retrieve)
    assert len(calls) == 1
    assert result["claim_coverage"]["claim_coverage"][0]["legal_rule_status"] == "candidate_found"
    assert [row["selected_action"] for row in result["actions"]] == [
        "RETRIEVE_LEGAL_EVIDENCE", "USE_EXISTING_EVIDENCE", "STOP_RESOLVED"
    ]
    assert result["actions"][0]["observation_type"] == "retrieval_hit"
    assert result["actions"][0]["remaining_budget"]["tool_calls"] == 1
    assert result["stop_reason"] == "task_evidence_requirements_resolved"


def test_second_gap_action_reads_first_gap_observation():
    claims = [
        {"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": False},
        {"claim": "产品召回应遵守相关要求", "requires_legal_rule": True, "requires_case_fact": False},
    ]
    args = inputs(claims=claims)
    calls = []

    def fake_retrieve(query, top_k):
        calls.append(query)
        chunk = RULE if CLAIM in query else {
            "chunk_id": "recall-rule", "source": "product-law",
            "text": "产品经营者必须召回存在安全问题的产品。",
        }
        return {"chunks": [chunk], "sources": []}

    result = run_legal_action_loop(*args[:3], args[4], retrieve_call=fake_retrieve)
    searches = [row for row in result["actions"] if row.get("selected_action") == "RETRIEVE_LEGAL_EVIDENCE"]
    assert len(calls) == 2 and len(searches) == 2
    assert [row["claim_index"] for row in searches] == [0, 1]
    assert searches[1]["previous_observation"]["claim_index"] == 0
    assert searches[1]["previous_observation"]["legal_rule_status"] == "candidate_found"
    assert all(row["context_chars"] <= result["context_budget"] for row in searches)


def test_no_hit_and_tool_failure_stop_without_retrying_same_gap():
    no_hit_calls = []
    no_hit = run_legal_action_loop(
        *inputs()[:3], inputs()[4],
        retrieve_call=lambda query, top_k: no_hit_calls.append(query) or {"chunks": []},
    )
    assert len(no_hit_calls) == 1
    assert no_hit["actions"][0]["observation_type"] == "retrieval_no_hit"
    assert no_hit["stop_reason"] == "no_eligible_action_after_observation"

    timeout_calls = []

    def transient_then_hit(*_args, **_kwargs):
        timeout_calls.append(True)
        if len(timeout_calls) == 1:
            raise TimeoutError()
        return {"chunks": [RULE], "sources": []}

    timeout = run_legal_action_loop(*inputs()[:3], inputs()[4], retrieve_call=transient_then_hit)
    assert len(timeout_calls) == 2
    assert timeout["actions"][0]["observation_type"] == "tool_timeout"
    assert timeout["actions"][0]["stop_reason"] == "bounded_retry_pending"
    assert timeout["actions"][1]["previous_observation"]["type"] == "tool_timeout"
    assert timeout["actions"][1]["selected_action"] == "RETRIEVE_LEGAL_EVIDENCE"
    assert timeout["stop_reason"] == "task_evidence_requirements_resolved"

    exhausted = run_legal_action_loop(
        *inputs()[:3], inputs()[4],
        retrieve_call=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    assert len(exhausted["actions"]) == 2
    assert exhausted["stop_reason"] == "tool_failure"

    invalid = run_legal_action_loop(
        *inputs()[:3], inputs()[4], retrieve_call=lambda *_args, **_kwargs: {"chunks": "invalid"},
    )
    assert invalid["actions"][0]["observation_type"] == "invalid_output"
    assert invalid["stop_reason"] == "tool_failure"


def test_loop_respects_round_and_tool_budgets_and_existing_evidence():
    claims = [
        {"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": False},
        {"claim": "产品召回应遵守相关要求", "requires_legal_rule": True, "requires_case_fact": False},
    ]
    args = inputs(claims=claims)
    calls = []
    bounded = run_legal_action_loop(
        *args[:3], args[4],
        retrieve_call=lambda query, top_k: calls.append(query) or {"chunks": [RULE]},
        policy={"max_tool_calls": 1, "max_rounds": 3, "context_budget": 6000,
                "max_same_action_per_gap": 1},
    )
    assert len(calls) == 1
    assert bounded["stop_reason"] == "tool_budget_exhausted"
    assert bounded["remaining_budget"]["tool_calls"] == 0

    evidence = {"chunk_id": "rule", "source": "food-law", "text": RULE["text"]}
    initial_relation = build_legal_claim_relations([claims[0]], [evidence])
    covered = build_claim_coverage([claims[0]], initial_relation)
    extraction = {"legal_claims": [claims[0]], "claim_extraction_status": "ok"}
    no_call = run_legal_action_loop(
        extraction, covered, initial_relation,
        {"query": "broad", "retrieval_status": "executed_with_hits",
         "retrieval_executed": True, "fallback_used": False},
        retrieve_call=lambda *_args, **_kwargs: pytest.fail("sufficient evidence must not be searched again"),
    )
    assert no_call["tool_calls_used"] == 0
    assert no_call["actions"][-1]["selected_action"] == "STOP_RESOLVED"


def _human_observation(response_type="FACT_UNAVAILABLE"):
    return {"observation_type": "fact_provided" if response_type == "FACT_PROVIDED" else "fact_unavailable",
            "request_id": "request-1", "claim_index": 0, "response_type": response_type,
            "source": "human_provided" if response_type == "FACT_PROVIDED" else "human_response",
            "verification_status": "human_asserted" if response_type == "FACT_PROVIDED" else "unresolved",
            "availability": response_type == "FACT_PROVIDED",
            "whether_new_information": response_type == "FACT_PROVIDED", "consumed": True}


def test_human_observation_resumes_same_loop_and_retrieval_changes_next_action():
    claims = [{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": True}]
    extraction, coverage, relation, _, rag = inputs(claims=claims)
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("must pause first"))
    assert first["cursor"]["round_count"] == 1
    assert first["cursor"]["remaining_rounds"] == 2
    calls = []
    resumed = run_legal_action_loop(
        extraction, first["claim_coverage"], first["claim_evidence_relation"], rag,
        retrieve_call=lambda query, top_k: calls.append(query) or {"chunks": [RULE], "sources": []},
        cursor=first["cursor"], human_observation=_human_observation(),
    )
    assert len(calls) == 1
    assert resumed["rounds"] == 3
    assert resumed["tool_calls_used"] == 1
    assert resumed["remaining_budget"]["tool_calls"] == 1
    assert resumed["actions"][2]["selected_action"] == "RETRIEVE_LEGAL_EVIDENCE"
    assert resumed["actions"][2]["previous_observation"]["request_id"] == "request-1"
    assert resumed["actions"][-2]["selected_action"] == "USE_EXISTING_EVIDENCE"
    assert resumed["actions"][-1]["selected_action"] == "STOP_UNRESOLVED"
    assert resumed["claim_coverage"]["claim_coverage"][0]["legal_rule_status"] == "candidate_found"
    assert resumed["claim_coverage"]["claim_coverage"][0]["case_fact_status"] == "unresolved"
    assert resumed["stop_reason"] == "fact_unavailable_requires_safe_revision"


def test_human_response_is_consumed_once_and_unavailable_does_not_repeat_request():
    claim = {"claim": "本批次情况尚未确认", "requires_legal_rule": False, "requires_case_fact": True}
    extraction, coverage, relation, _, rag = inputs(claims=[claim])
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("no legal search"))
    second = run_legal_action_loop(extraction, coverage, relation, rag,
                                   retrieve_call=lambda *_a, **_kw: pytest.fail("no legal search"),
                                   cursor=first["cursor"], human_observation=_human_observation())
    assert second["rounds"] == 2
    assert second["stop_reason"] == "no_information_gain"
    assert sum(row["selected_action"] == "REQUEST_HUMAN_FACT" for row in second["actions"]) == 1
    repeat = run_legal_action_loop(extraction, coverage, relation, rag,
                                   retrieve_call=lambda *_a, **_kw: pytest.fail("duplicate action"),
                                   cursor=second["cursor"], human_observation=_human_observation())
    assert repeat["stop_reason"] == "human_fact_already_consumed"
    assert repeat["actions"] == second["actions"]


def test_human_assertion_remains_unverified_and_second_fact_fails_closed():
    claims = [
        {"claim": "第一项事实", "requires_legal_rule": False, "requires_case_fact": True},
        {"claim": "第二项事实", "requires_legal_rule": False, "requires_case_fact": True},
    ]
    extraction, coverage, relation, _, rag = inputs(claims=claims)
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("no legal search"))
    resumed = run_legal_action_loop(extraction, coverage, relation, rag,
                                    retrieve_call=lambda *_a, **_kw: pytest.fail("no legal search"),
                                    cursor=first["cursor"], human_observation=_human_observation("FACT_PROVIDED"))
    assert resumed["stop_reason"] == "second_human_fact_not_supported"
    assert resumed["cursor"]["consumed_request_ids"] == ["request-1"]
    assert resumed["claim_coverage"]["claim_coverage"][0]["case_fact_status"] == "unresolved"
    assert all(row["selected_action"] != "STOP_RESOLVED" for row in resumed["actions"])


@pytest.mark.parametrize("policy,reason", [
    ({"max_rounds": 1}, "round_budget_exhausted"),
    ({"max_tool_calls": 0}, "tool_budget_exhausted"),
])
def test_human_resume_keeps_original_budget(policy, reason):
    claims = [{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": True}]
    extraction, coverage, relation, _, rag = inputs(claims=claims)
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("pause first"), policy=policy)
    resumed = run_legal_action_loop(extraction, coverage, relation, rag,
                                    retrieve_call=lambda *_a, **_kw: pytest.fail("budget exhausted"),
                                    policy=policy, cursor=first["cursor"],
                                    human_observation=_human_observation())
    assert resumed["stop_reason"] == reason
    assert resumed["tool_calls_used"] == 0


def test_retrieval_no_hit_after_human_observation_stops_without_repeat():
    claims = [{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": True}]
    extraction, coverage, relation, _, rag = inputs(claims=claims)
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("pause first"))
    calls = []
    resumed = run_legal_action_loop(
        extraction, coverage, relation, rag,
        retrieve_call=lambda query, top_k: calls.append(query) or {"chunks": [], "sources": []},
        cursor=first["cursor"], human_observation=_human_observation(),
    )
    assert len(calls) == 1
    assert resumed["stop_reason"] == "unresolved_after_observation"
    assert resumed["actions"][2]["observation_type"] == "retrieval_no_hit"
    assert sum(row["selected_action"] == "RETRIEVE_LEGAL_EVIDENCE" for row in resumed["actions"]) == 1


def test_retrieval_without_coverage_gain_does_not_repeat_after_human():
    claims = [{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": True}]
    extraction, coverage, relation, _, rag = inputs(claims=claims)
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("pause first"))
    calls = []
    resumed = run_legal_action_loop(
        extraction, coverage, relation, rag,
        retrieve_call=lambda query, top_k: calls.append(query) or {"chunks": [GUIDANCE], "sources": []},
        cursor=first["cursor"], human_observation=_human_observation(),
    )
    assert len(calls) == 1
    assert resumed["stop_reason"] == "unresolved_after_observation"
    assert resumed["actions"][-1]["after_legal_rule_status"] == "no_candidate"


def test_last_tool_call_can_still_lead_to_non_tool_stop_after_human():
    claims = [{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": True}]
    extraction, coverage, relation, _, rag = inputs(claims=claims)
    policy = {"max_tool_calls": 1}
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("pause first"), policy=policy)
    resumed = run_legal_action_loop(
        extraction, coverage, relation, rag,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        cursor=first["cursor"], human_observation=_human_observation(), policy=policy,
    )
    assert resumed["tool_calls_used"] == 1
    assert resumed["remaining_budget"]["tool_calls"] == 0
    assert resumed["actions"][-1]["selected_action"] == "STOP_UNRESOLVED"
    assert resumed["stop_reason"] == "fact_unavailable_requires_safe_revision"


def test_nonzero_tool_usage_in_saved_cursor_is_not_reset():
    claims = [{"claim": CLAIM, "requires_legal_rule": True, "requires_case_fact": True}]
    extraction, coverage, relation, _, rag = inputs(claims=claims)
    first = run_legal_action_loop(extraction, coverage, relation, rag,
                                  retrieve_call=lambda *_a, **_kw: pytest.fail("pause first"))
    saved_cursor = deepcopy(first["cursor"])
    saved_cursor["tool_calls_used"] = 1
    saved_cursor["remaining_tool_calls"] = 1
    resumed = run_legal_action_loop(extraction, coverage, relation, rag,
                                    retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
                                    cursor=saved_cursor, human_observation=_human_observation())
    assert resumed["tool_calls_used"] == 2
    assert resumed["remaining_budget"]["tool_calls"] == 0
    assert resumed["stop_reason"] == "fact_unavailable_requires_safe_revision"


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
