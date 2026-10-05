import json

import pytest

from backend.agents.legal_action_policy import (
    REQUEST_HUMAN_FACT,
    RETRIEVE_LEGAL_EVIDENCE,
    STOP_RESOLVED,
    compute_eligible_actions,
    recommend_legal_actions,
    validate_action_proposal,
)
from backend.agents.legal_action_proposal import (
    build_legal_decision_context,
    request_legal_action_proposal,
)
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_targeted_search import run_legal_action_loop
from backend.core.trace_safety import sanitize_trace_metadata


CLAIMS = [
    {"claim": "第一项法律规则声明", "requires_legal_rule": True, "requires_case_fact": False},
    {"claim": "第二项法律规则声明", "requires_legal_rule": True, "requires_case_fact": False},
]
RELATION = {
    "legal_claim_relations": [
        {"claim_index": 0, "evidence_ref": "guidance", "relation": "no_rule_match"},
        {"claim_index": 1, "evidence_ref": "guidance", "relation": "no_rule_match"},
    ],
    "relation_status": "ok",
}
RAG = {"query": "broad", "retrieval_status": "executed_with_hits",
       "retrieval_executed": True, "fallback_used": False}
RULE = {"chunk_id": "rule", "source": "law", "text": "经营者应当遵守相关法律规定。"}


def test_human_fact_eligibility_and_validator_are_claim_scoped():
    claims = [
        {"claim": "第一项事实", "requires_legal_rule": False, "requires_case_fact": True},
        {"claim": "第二项事实", "requires_legal_rule": False, "requires_case_fact": True},
    ]
    extraction, coverage, relation, recommendations = _inputs(claims=claims, relation={
        "legal_claim_relations": [], "relation_status": "skipped",
    })
    eligible = compute_eligible_actions(
        extraction, coverage, recommendations,
        requested_fact_gaps=[0], attempted_actions={}, remaining_rounds=2,
        remaining_tool_calls=2, max_same_action_per_gap=2,
    )
    assert eligible == [{"action": REQUEST_HUMAN_FACT, "target_claim_index": 1,
                          "reason_code": "CASE_FACT_GAP"}]
    allowed = validate_action_proposal(
        eligible[0], eligible, extraction, coverage,
        requested_fact_gaps=[0], consumed_request_ids=["request-1"], attempted_actions={},
        remaining_rounds=2, remaining_tool_calls=2, max_same_action_per_gap=2,
    )
    assert allowed == {"allowed": True, "reason_code": "allowed", "safety_violation": False}
    blocked = validate_action_proposal(
        {"action": REQUEST_HUMAN_FACT, "target_claim_index": 0, "reason_code": "CASE_FACT_GAP"},
        eligible, extraction, coverage,
        requested_fact_gaps=[0], consumed_request_ids=["request-1"], attempted_actions={},
        remaining_rounds=2, remaining_tool_calls=2, max_same_action_per_gap=2,
    )
    assert blocked["allowed"] is False
    assert blocked["reason_code"] == "human_fact_already_consumed"


def _inputs(claims=None, relation=None):
    claims = claims or CLAIMS
    relation = relation or RELATION
    extraction = {"legal_claims": claims, "claim_extraction_status": "ok"}
    coverage = build_claim_coverage(claims, relation)
    recommendations = recommend_legal_actions(extraction, coverage, relation, RAG)
    return extraction, coverage, relation, recommendations


def _relation_for_selected(claims, chunks, **_kwargs):
    return {"legal_claim_relations": [
        {"claim_index": 0, "evidence_ref": chunks[0]["chunk_id"],
         "relation": "candidate_rule_relevant"}], "relation_status": "ok"}


def test_multiple_eligible_actions_let_valid_proposal_choose_executed_claim():
    extraction, coverage, relation, _ = _inputs()
    proposal_calls = []
    queries = []

    def proposal(prompt):
        proposal_calls.append(prompt)
        return json.dumps({"action": RETRIEVE_LEGAL_EVIDENCE,
                           "reason_code": "LEGAL_RULE_GAP", "target_claim_index": 1})

    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda query, top_k: queries.append(query) or {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected, llm_call=proposal, mode="llm",
        policy={"max_tool_calls": 1},
    )
    first = result["actions"][0]
    assert len(proposal_calls) == 1
    assert first["eligible_action_count"] == 2
    assert first["eligible_target_claim_indices"] == [0, 1]
    assert first["deterministic_baseline_action"] == RETRIEVE_LEGAL_EVIDENCE
    assert first["deterministic_baseline_target_claim_index"] == 0
    assert first["proposal_called"] is True
    assert first["proposal_status"] == "VALID"
    assert first["proposal_action"] == RETRIEVE_LEGAL_EVIDENCE
    assert first["proposal_target_claim_index"] == 1
    assert first["validator_called"] is True
    assert first["validator_allowed"] is True
    assert first["fallback_reason_code"] is None
    assert first["executed_action"] == RETRIEVE_LEGAL_EVIDENCE
    assert first["executed_target_claim_index"] == 1
    assert first["claim_index"] == 1
    assert CLAIMS[1]["claim"] in queries[0] and CLAIMS[0]["claim"] not in queries[0]


def test_proposal_can_choose_retrieval_over_a_separate_human_fact_gap():
    claims = [
        {"claim": "待确认企业事实", "requires_legal_rule": False, "requires_case_fact": True},
        CLAIMS[1],
    ]
    relation = {"legal_claim_relations": [
        {"claim_index": 1, "evidence_ref": "guidance", "relation": "no_rule_match"}],
        "relation_status": "ok"}
    extraction, coverage, relation, _ = _inputs(claims, relation)
    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected,
        llm_call=lambda _prompt: json.dumps({
            "action": RETRIEVE_LEGAL_EVIDENCE,
            "reason_code": "LEGAL_RULE_GAP",
            "target_claim_index": 1,
        }),
        mode="llm", policy={"max_tool_calls": 1},
    )
    assert result["actions"][0]["eligible_action_count"] == 2
    assert result["actions"][0]["selected_action"] == RETRIEVE_LEGAL_EVIDENCE
    assert result["actions"][0]["claim_index"] == 1


def test_single_eligible_action_does_not_call_proposal_llm():
    extraction, coverage, relation, _ = _inputs(claims=[CLAIMS[0]], relation={
        "legal_claim_relations": [
            {"claim_index": 0, "evidence_ref": "guidance", "relation": "no_rule_match"}],
        "relation_status": "ok",
    })
    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected,
        llm_call=lambda _prompt: pytest.fail("single eligible action must not call LLM"),
        mode="llm", policy={"max_tool_calls": 1},
    )
    assert result["actions"][0]["eligible_action_count"] == 1
    assert result["actions"][0]["proposal_status"] == "NOT_CALLED"
    assert result["actions"][0]["proposal_called"] is False
    assert result["actions"][0]["validator_called"] is False
    assert result["actions"][0]["deterministic_baseline_target_claim_index"] == 0


def test_zero_eligible_actions_stop_safely_without_llm():
    result = run_legal_action_loop(
        {"legal_claims": []}, {"claim_coverage": []},
        {"legal_claim_relations": [], "relation_status": "skipped"}, RAG,
        retrieve_call=lambda *_a, **_kw: pytest.fail("no action"),
        llm_call=lambda _prompt: pytest.fail("no proposal"), mode="llm",
    )
    assert result["stop_reason"] == "no_eligible_action"
    assert result["actions"][0]["eligible_action_count"] == 0


def test_invalid_proposal_records_parse_failure_without_validator_call():
    extraction, coverage, relation, _ = _inputs()
    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected, llm_call=lambda _prompt: "not-json",
        mode="llm", policy={"max_tool_calls": 1},
    )
    first = result["actions"][0]
    assert first["proposal_status"] == "INVALID_JSON"
    assert first["validator_called"] is False
    assert first["validator_allowed"] is False
    assert first["proposal_fallback_used"] is True
    assert first["fallback_reason_code"] == "PARSE_FAILURE"


def test_validator_reject_records_rejection_without_normal_fallback():
    extraction, coverage, relation, _ = _inputs()
    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected,
        llm_call=lambda _prompt: json.dumps({
            "action": "STOP_RESOLVED", "reason_code": "REQUIREMENTS_RESOLVED",
            "target_claim_index": 0,
        }),
        mode="llm", policy={"max_tool_calls": 1},
    )
    first = result["actions"][0]
    assert first["proposal_status"] == "REJECTED"
    assert first["validator_called"] is True
    assert first["validator_allowed"] is False
    assert first["validator_reason_code"] == "unresolved_requirement"
    assert first["proposal_fallback_used"] is False
    assert first["safety_stop"] is True


def test_timeout_records_provider_failure_and_deterministic_fallback():
    extraction, coverage, relation, _ = _inputs()

    def timeout(_prompt):
        raise TimeoutError("provider timeout")

    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected, llm_call=timeout,
        mode="llm", policy={"max_tool_calls": 1},
    )
    first = result["actions"][0]
    assert first["proposal_status"] == "PROVIDER_TIMEOUT"
    assert first["validator_called"] is False
    assert first["proposal_fallback_used"] is True
    assert first["fallback_reason_code"] == "PROVIDER_FAILURE"


@pytest.mark.parametrize("response", [
    "not-json",
    json.dumps({"action": "UNKNOWN", "reason_code": "LEGAL_RULE_GAP", "target_claim_index": 0}),
    json.dumps({"action": RETRIEVE_LEGAL_EVIDENCE,
                "reason_code": "LEGAL_RULE_GAP", "target_claim_index": 99}),
])
def test_invalid_proposal_falls_back_to_deterministic_safe_action(response):
    extraction, coverage, relation, _ = _inputs()
    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected, llm_call=lambda _prompt: response,
        mode="llm", policy={"max_tool_calls": 1},
    )
    first = result["actions"][0]
    assert first["claim_index"] == 0
    assert first["proposal_fallback_used"] is True
    assert first["validator_allowed"] is False


def test_provider_timeout_falls_back_without_escaping():
    extraction, coverage, relation, _ = _inputs()

    def timeout(_prompt):
        raise TimeoutError("offline timeout")

    result = run_legal_action_loop(
        extraction, coverage, relation, RAG,
        retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
        relation_call=_relation_for_selected, llm_call=timeout,
        mode="llm", policy={"max_tool_calls": 1},
    )
    assert result["actions"][0]["validator_reason_code"] == "timeout"
    assert result["actions"][0]["proposal_fallback_used"] is True


def test_validator_rejects_safety_boundary_and_budget_bypass():
    mixed = [{"claim": "尚未核验的混合声明", "requires_legal_rule": True,
              "requires_case_fact": True}]
    extraction, coverage, _, recommendations = _inputs(claims=mixed, relation={
        "legal_claim_relations": [
            {"claim_index": 0, "evidence_ref": "guidance", "relation": "no_rule_match"}],
        "relation_status": "ok",
    })
    eligible = compute_eligible_actions(
        extraction, coverage, recommendations, remaining_rounds=1,
        remaining_tool_calls=1, max_same_action_per_gap=1,
    )
    unresolved = validate_action_proposal(
        {"action": STOP_RESOLVED, "reason_code": "REQUIREMENTS_RESOLVED",
         "target_claim_index": 0}, eligible, extraction, coverage,
        remaining_rounds=1, remaining_tool_calls=1, max_same_action_per_gap=1,
        previous_observation={"verification_status": "human_asserted"},
    )
    assert unresolved == {"allowed": False, "reason_code": "unresolved_requirement",
                          "safety_violation": True}
    exhausted = validate_action_proposal(
        {"action": RETRIEVE_LEGAL_EVIDENCE, "reason_code": "LEGAL_RULE_GAP",
         "target_claim_index": 0}, eligible, extraction, coverage,
        remaining_rounds=1, remaining_tool_calls=0, max_same_action_per_gap=1,
    )
    assert exhausted["reason_code"] == "tool_budget_exhausted"
    assert exhausted["safety_violation"] is True
    no_round = validate_action_proposal(
        {"action": RETRIEVE_LEGAL_EVIDENCE, "reason_code": "LEGAL_RULE_GAP",
         "target_claim_index": 0}, eligible, extraction, coverage,
        remaining_rounds=0, remaining_tool_calls=1, max_same_action_per_gap=1,
    )
    assert no_round["reason_code"] == "round_budget_exhausted"
    assert no_round["safety_violation"] is True


def test_validator_rejects_noneligible_pair_and_missing_retrieval_prerequisite():
    claims = [CLAIMS[0], {"claim": "已有候选规则", "requires_legal_rule": True,
                          "requires_case_fact": False}]
    extraction = {"legal_claims": claims}
    coverage = {"claim_coverage": [
        {"claim_index": 0, "legal_rule_status": "no_candidate", "case_fact_status": "not_required"},
        {"claim_index": 1, "legal_rule_status": "candidate_found", "case_fact_status": "not_required"},
    ]}
    eligible = [{"action": RETRIEVE_LEGAL_EVIDENCE,
                 "target_claim_index": 0, "reason_code": "LEGAL_RULE_GAP"}]
    result = validate_action_proposal(
        {"action": RETRIEVE_LEGAL_EVIDENCE, "reason_code": "LEGAL_RULE_GAP",
         "target_claim_index": 1}, eligible, extraction, coverage,
        remaining_rounds=1, remaining_tool_calls=1, max_same_action_per_gap=1,
    )
    assert result["reason_code"] == "retrieval_prerequisite_missing"
    assert result["safety_violation"] is True


def test_validator_rejects_duplicate_retrieval_and_human_fact():
    extraction, coverage, _, recommendations = _inputs()
    eligible = compute_eligible_actions(
        extraction, coverage, recommendations, attempted_actions={0: 0},
        remaining_rounds=1, remaining_tool_calls=1, max_same_action_per_gap=1,
    )
    duplicate = validate_action_proposal(
        {"action": RETRIEVE_LEGAL_EVIDENCE, "reason_code": "LEGAL_RULE_GAP",
         "target_claim_index": 0}, eligible, extraction, coverage,
        attempted_actions={0: 1}, remaining_rounds=1, remaining_tool_calls=1,
        max_same_action_per_gap=1,
    )
    assert duplicate["reason_code"] == "duplicate_action_without_information_gain"

    fact_claim = [{"claim": "待确认事实", "requires_legal_rule": False,
                   "requires_case_fact": True}]
    fact_extraction, fact_coverage, _, fact_recommendations = _inputs(
        claims=fact_claim, relation={"legal_claim_relations": [], "relation_status": "skipped"})
    fact_eligible = compute_eligible_actions(
        fact_extraction, fact_coverage, fact_recommendations,
        remaining_rounds=1, remaining_tool_calls=1, max_same_action_per_gap=1,
    )
    repeated = validate_action_proposal(
        {"action": "REQUEST_HUMAN_FACT", "reason_code": "CASE_FACT_GAP",
         "target_claim_index": 0}, fact_eligible, fact_extraction, fact_coverage,
        requested_fact_gaps=[0], consumed_request_ids=["request-1"],
        remaining_rounds=1, remaining_tool_calls=1, max_same_action_per_gap=1,
    )
    assert repeated["reason_code"] == "human_fact_already_consumed"


def test_decision_context_and_safe_trace_exclude_business_content():
    extraction, coverage, relation, recommendations = _inputs()
    eligible = compute_eligible_actions(
        extraction, coverage, recommendations, remaining_rounds=2,
        remaining_tool_calls=2, max_same_action_per_gap=2,
    )
    secret = "SENSITIVE-HUMAN-FACT"
    context = build_legal_decision_context(
        extraction, coverage, relation, RAG, eligible,
        previous_observation={"type": "fact_provided", "response_text": secret,
                              "whether_new_information": True},
        attempted_actions={}, requested_fact_gaps=[], round_count=1,
        remaining_rounds=2, remaining_tool_calls=2, risk_level="high",
    )
    serialized = json.dumps(context, ensure_ascii=False)
    assert secret not in serialized
    assert all(claim["claim"] not in serialized for claim in CLAIMS)
    assert "query" not in serialized and "text" not in serialized

    trace = sanitize_trace_metadata({
        "event": "SENSITIVE-EVENT", "claim": CLAIMS[0]["claim"],
        "evidence_text": "SENSITIVE-EVIDENCE", "prompt": "SENSITIVE-PROMPT",
        "action": RETRIEVE_LEGAL_EVIDENCE, "eligible_action_count": 2,
        "validator_allowed": True,
    })
    assert "SENSITIVE" not in str(trace)
    assert trace["action"] == RETRIEVE_LEGAL_EVIDENCE


def test_proposal_schema_rejects_free_query_and_reasoning_fields():
    result = request_legal_action_proposal(
        {"eligible_actions": [{"action": RETRIEVE_LEGAL_EVIDENCE,
                                "target_claim_index": 0}]},
        llm_call=lambda _prompt: json.dumps({
            "action": RETRIEVE_LEGAL_EVIDENCE,
            "reason_code": "LEGAL_RULE_GAP",
            "target_claim_index": 0,
            "query": "free query",
            "reasoning": "hidden reasoning",
        }),
    )
    assert result["status"] == "fallback"
    assert result["proposal"] is None


def test_previous_observation_can_change_valid_proposal_selection():
    mixed_claims = [
        {"claim": "公司是否已向监管机构报告；法律规定何时需要向监管机构报告",
         "requires_legal_rule": True, "requires_case_fact": True},
        CLAIMS[1],
    ]
    mixed_relation = {
        "legal_claim_relations": [
            {"claim_index": 0, "evidence_ref": "guidance", "relation": "no_rule_match"},
            {"claim_index": 1, "evidence_ref": "guidance", "relation": "no_rule_match"},
        ], "relation_status": "ok",
    }
    extraction, coverage, relation, _ = _inputs(mixed_claims, mixed_relation)

    def first_loop():
        return run_legal_action_loop(
            extraction, coverage, relation, RAG,
            retrieve_call=lambda *_a, **_kw: pytest.fail("must pause"), mode="mock",
            policy={"max_tool_calls": 1},
        )

    selected = []

    def proposal(prompt):
        target = 1 if '"type":"fact_provided"' in prompt else 0
        selected.append(target)
        return json.dumps({"action": RETRIEVE_LEGAL_EVIDENCE,
                           "reason_code": "OBSERVATION_CHANGED_PRIORITY",
                           "target_claim_index": target})

    for response_type in ("FACT_UNAVAILABLE", "FACT_PROVIDED"):
        first = first_loop()
        first["cursor"]["mode"] = "llm"
        observation = {
            "observation_type": "fact_provided" if response_type == "FACT_PROVIDED" else "fact_unavailable",
            "request_id": f"request-{response_type}", "claim_index": 0,
            "response_type": response_type,
            "verification_status": "human_asserted" if response_type == "FACT_PROVIDED" else "unresolved",
            "whether_new_information": response_type == "FACT_PROVIDED", "consumed": True,
        }
        resumed = run_legal_action_loop(
            extraction, first["claim_coverage"], first["claim_evidence_relation"], RAG,
            retrieve_call=lambda *_a, **_kw: {"chunks": [RULE], "sources": []},
            relation_call=_relation_for_selected, llm_call=proposal,
            cursor=first["cursor"], human_observation=observation,
            policy={"max_tool_calls": 1},
        )
        retrieval = next(row for row in resumed["actions"]
                         if row.get("selected_action") == RETRIEVE_LEGAL_EVIDENCE)
        assert retrieval["eligible_action_count"] == 2
        assert retrieval["claim_index"] == selected[-1]
    assert selected == [0, 1]

