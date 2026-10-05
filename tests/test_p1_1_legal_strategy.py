"""Frozen, offline checks for bounded cross-action Legal decisions."""

import json
from pathlib import Path

import pytest

from backend.agents.legal_action_policy import (
    classify_legal_query_dependency,
    compute_eligible_actions,
    recommend_legal_actions,
    validate_action_proposal,
)
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_targeted_search import run_legal_action_loop
from evaluation.frozen_hash import canonical_text_sha256


DATASET = Path(__file__).resolve().parents[1] / "evaluation" / "p1_1_legal_strategy_frozen.json"
FROZEN_SHA256 = "8ea442daa566a0c5c62a526ac3e2138433466d8f0e946c9fee56201d3d7bc59b"
RULE = {"chunk_id": "rule", "source": "regulation",
        "text": "法律规定符合特定条件时应当向监管机构报告。"}


def _scenarios():
    raw = DATASET.read_bytes()
    assert canonical_text_sha256(raw) == FROZEN_SHA256
    data = json.loads(raw.decode("utf-8"))
    return data["development"] + data["holdout"]


def _scenario(case_id):
    return next(case for case in _scenarios() if case["case_id"] == case_id)


def _inputs(case):
    claim = {"claim": case["claim"], "requires_case_fact": case["requires_case_fact"],
             "requires_legal_rule": case["requires_legal_rule"]}
    extraction = {"legal_claims": [claim], "claim_extraction_status": "ok"}
    relation_rows = [] if case["relation"] is None else [
        {"claim_index": 0, "evidence_ref": "initial", "relation": case["relation"]}
    ]
    relation = {"legal_claim_relations": relation_rows,
                "relation_status": "ok" if relation_rows else "skipped"}
    coverage = build_claim_coverage([claim], relation)
    assert coverage["claim_coverage"][0]["case_fact_status"] == case["case_fact_status"]
    assert coverage["claim_coverage"][0]["legal_rule_status"] == case["legal_rule_status"]
    rag = {"query": "broad query", "retrieval_status": case["retrieval_status"],
           "retrieval_executed": case["retrieval_executed"],
           "fallback_used": case["fallback_used"]}
    return extraction, coverage, relation, rag


def _eligible(case):
    extraction, coverage, relation, rag = _inputs(case)
    recommendation = recommend_legal_actions(extraction, coverage, relation, rag)
    options = compute_eligible_actions(
        extraction, coverage, recommendation,
        requested_fact_gaps=case["requested_fact_gaps"],
        attempted_actions={int(index): count for index, count in case["attempted_actions"].items()},
        remaining_rounds=case["remaining_rounds"],
        remaining_tool_calls=case["remaining_tool_calls"],
        max_same_action_per_gap=case["max_same_action_per_gap"],
        claim_relation=relation, rag_info=rag,
    )
    return options


@pytest.mark.parametrize("case_id", ["DEV-01", "H1", "H2", "H3", "H4", "H5", "H6"])
def test_frozen_dependency_and_eligibility(case_id):
    case = _scenario(case_id)
    claim = {"claim": case["claim"], "requires_case_fact": case["requires_case_fact"],
             "requires_legal_rule": case["requires_legal_rule"]}
    assert classify_legal_query_dependency(claim)["dependency_type"] == case["expected_dependency"]
    actions = [row["action"] for row in _eligible(case)]
    assert actions == case["expected_eligible_actions"]
    assert not set(actions).intersection(case["prohibited_actions"])


def _relation_with_rule(_claims, chunks, **_kwargs):
    assert chunks[0]["chunk_id"] == "rule"
    return {"legal_claim_relations": [{"claim_index": 0, "evidence_ref": "rule",
                                       "relation": "candidate_rule_relevant"}], "relation_status": "ok"}


def _retrieve(query, *, top_k):
    assert "法律规定何时需要向监管机构报告" in query
    assert "公司是否已" not in query
    assert top_k == 3
    return {"chunks": [RULE], "sources": []}


def _human_observation(response_type="FACT_PROVIDED"):
    provided = response_type == "FACT_PROVIDED"
    return {"observation_type": "fact_provided" if provided else "fact_unavailable",
            "request_id": "request-h1", "claim_index": 0, "response_type": response_type,
            "verification_status": "human_asserted" if provided else "unresolved",
            "source": "human_provided" if provided else "human_response",
            "whether_new_information": provided, "consumed": True}


def test_retrieval_first_observation_removes_legal_gap_and_leaves_human_action():
    extraction, coverage, relation, rag = _inputs(_scenario("H1"))
    proposals = []

    def propose(prompt):
        proposals.append(prompt)
        return json.dumps({"action": "RETRIEVE_LEGAL_EVIDENCE",
                           "reason_code": "LEGAL_RULE_GAP", "target_claim_index": 0})

    result = run_legal_action_loop(
        extraction, coverage, relation, rag,
        retrieve_call=_retrieve, relation_call=_relation_with_rule,
        llm_call=propose, mode="llm",
    )
    actions = result["actions"]
    assert len(proposals) == 1
    assert [row["selected_action"] for row in actions] == [
        "RETRIEVE_LEGAL_EVIDENCE", "REQUEST_HUMAN_FACT"
    ]
    assert actions[0]["eligible_action_count"] == 2
    assert actions[0]["validator_allowed"] is True
    assert actions[0]["before_legal_rule_status"] == "no_candidate"
    assert actions[0]["after_legal_rule_status"] == "candidate_found"
    assert actions[1]["eligible_actions"] == [{"action": "REQUEST_HUMAN_FACT", "target_claim_index": 0}]
    assert actions[1]["previous_observation_changed_state"] is True
    assert result["claim_coverage"]["claim_coverage"][0]["case_fact_status"] == "unresolved"
    assert result["cursor"]["information_dependencies"][0]["dependency_type"] == "INDEPENDENT"
    assert result["stop_reason"] == "human_fact_required"


@pytest.mark.parametrize("response_type,input_status", [
    ("FACT_PROVIDED", "human_asserted"), ("FACT_UNAVAILABLE", "unavailable"),
])
def test_human_first_observation_changes_input_gap_but_not_legal_rule(response_type, input_status):
    extraction, coverage, relation, rag = _inputs(_scenario("H1"))
    first = run_legal_action_loop(
        extraction, coverage, relation, rag,
        retrieve_call=lambda *_a, **_kw: pytest.fail("mock must pause before retrieval"),
    )
    assert first["actions"][0]["selected_action"] == "REQUEST_HUMAN_FACT"
    assert first["claim_coverage"]["claim_coverage"][0]["legal_rule_status"] == "no_candidate"
    resumed = run_legal_action_loop(
        extraction, first["claim_coverage"], first["claim_evidence_relation"], rag,
        retrieve_call=_retrieve, relation_call=_relation_with_rule,
        cursor=first["cursor"], human_observation=_human_observation(response_type),
    )
    row = resumed["claim_coverage"]["claim_coverage"][0]
    assert row["case_fact_input_status"] == input_status
    assert row["case_fact_status"] == "unresolved"
    assert row["verification_status"] == ("human_asserted" if response_type == "FACT_PROVIDED" else "unresolved")
    assert row["legal_rule_status"] == "candidate_found"
    assert resumed["actions"][2]["selected_action"] == "RETRIEVE_LEGAL_EVIDENCE"
    assert resumed["actions"][2]["previous_observation_changed_state"] is True
    assert resumed["cursor"]["requested_fact_gaps"] == [0]
    assert resumed["cursor"]["consumed_request_ids"] == ["request-h1"]
    assert resumed["stop_reason"] != "task_evidence_requirements_resolved"


def test_fact_dependent_retrieval_is_denied_even_if_proposal_forges_eligibility():
    case = _scenario("H2")
    extraction, coverage, relation, rag = _inputs(case)
    forged = [{"action": "RETRIEVE_LEGAL_EVIDENCE", "target_claim_index": 0,
               "reason_code": "LEGAL_RULE_GAP"}]
    verdict = validate_action_proposal(
        {"action": "RETRIEVE_LEGAL_EVIDENCE", "reason_code": "LEGAL_RULE_GAP",
         "target_claim_index": 0}, forged, extraction, coverage,
        remaining_rounds=3, remaining_tool_calls=2, max_same_action_per_gap=2,
    )
    assert verdict == {"allowed": False, "reason_code": "fact_dependent_legal_query",
                       "safety_violation": True}
    assert [item["action"] for item in _eligible(case)] == ["REQUEST_HUMAN_FACT"]


def test_checkpoint_cursor_restores_dependency_gap_and_budget_without_upgrading_human_fact():
    extraction, coverage, relation, rag = _inputs(_scenario("H1"))

    def propose(_prompt):
        return json.dumps({"action": "RETRIEVE_LEGAL_EVIDENCE",
                           "reason_code": "LEGAL_RULE_GAP", "target_claim_index": 0})

    waiting = run_legal_action_loop(extraction, coverage, relation, rag,
                                    retrieve_call=_retrieve, relation_call=_relation_with_rule,
                                    llm_call=propose, mode="llm")
    cursor = json.loads(json.dumps(waiting["cursor"], ensure_ascii=False))
    resumed = run_legal_action_loop(
        extraction, waiting["claim_coverage"], waiting["claim_evidence_relation"], rag,
        retrieve_call=lambda *_a, **_kw: pytest.fail("candidate rule must not be retrieved twice"),
        cursor=cursor, human_observation=_human_observation(),
    )
    assert resumed["cursor"]["information_dependencies"] == cursor["information_dependencies"]
    assert resumed["cursor"]["tool_calls_used"] == 1
    assert resumed["cursor"]["requested_fact_gaps"] == [0]
    assert resumed["cursor"]["consumed_request_ids"] == ["request-h1"]
    assert resumed["claim_coverage"]["claim_coverage"][0]["verification_status"] == "human_asserted"
    assert resumed["claim_coverage"]["claim_coverage"][0]["case_fact_status"] == "unresolved"
    assert resumed["claim_coverage"]["claim_coverage"][0]["legal_rule_status"] == "candidate_found"
    assert resumed["stop_reason"] == "human_asserted_fact_requires_review"

    tampered = json.loads(json.dumps(cursor))
    tampered["information_dependencies"][0]["dependency_type"] = "FACT_DEPENDENT"
    rejected = run_legal_action_loop(
        extraction, waiting["claim_coverage"], waiting["claim_evidence_relation"], rag,
        retrieve_call=lambda *_a, **_kw: pytest.fail("tampered cursor must fail closed"),
        cursor=tampered, human_observation=_human_observation(),
    )
    assert rejected["stop_reason"] == "dependency_or_gap_state_mismatch"
