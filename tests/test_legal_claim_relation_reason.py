import json

import pytest

from backend.agents import legal_agent, legal_claim_relation
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_claim_relation import build_legal_claim_relations
from backend.config import get_config
from backend.core.executor import _collect_trace_metadata
from backend.core.policy import evaluate_human_policy
from backend.core.state import AgentState


RULE = "食品生产经营者不得使用超过保质期的食品原料。"
CHUNK = {"chunk_id": "rule-1", "source": "food_safety.md", "text": RULE}
CLAIM = {"claim": "使用过期原料可能违反食品安全规定", "requires_legal_rule": True,
         "requires_case_fact": False}


def _result(claim=CLAIM, *, mode="mock", raw=None):
    return build_legal_claim_relations([claim], [CHUNK], mode=mode,
                                       llm_call=(lambda _: raw) if mode == "llm" else None)


def _llm_row(relation, reason=None, **extra):
    row = {"claim_index": 0, "evidence_ref": "rule-1", "relation": relation, **extra}
    if reason is not None:
        row["reason"] = reason
    return json.dumps({"relations": [row]}, ensure_ascii=False)


def test_vague_claim_has_pair_level_context_reason():
    vague = {**CLAIM, "claim": "目前不存在违法行为", "requires_case_fact": True}
    assert _result(vague)["legal_claim_relations"] == [{
        "claim_index": 0, "evidence_ref": "rule-1", "relation": "uncertain",
        "reason": "claim_context_insufficient",
    }]
    llm = _result(vague, mode="llm", raw=_llm_row("uncertain", "semantic_relation_unclear"))
    assert llm["legal_claim_relations"][0]["reason"] == "claim_context_insufficient"


def test_clear_claim_with_ambiguous_evidence_has_semantic_reason():
    chunk = {**CHUNK, "text": "企业必须遵守监管要求。"}
    result = build_legal_claim_relations([CLAIM], [chunk])
    assert result["legal_claim_relations"][0]["relation"] == "uncertain"
    assert result["legal_claim_relations"][0]["reason"] == "semantic_relation_unclear"
    llm = _result(mode="llm", raw=_llm_row("uncertain", "semantic_relation_unclear"))
    assert llm["relation_status"] == "ok"
    assert llm["legal_claim_relations"][0]["reason"] == "semantic_relation_unclear"


@pytest.mark.parametrize("relation,chunk", [
    ("candidate_rule_relevant", CHUNK),
    ("no_rule_match", {**CHUNK, "text": "企业应及时回应公众。"}),
])
def test_decided_relation_has_no_uncertain_reason(relation, chunk):
    row = build_legal_claim_relations([CLAIM], [chunk])["legal_claim_relations"][0]
    assert row["relation"] == relation
    assert "reason" not in row


@pytest.mark.parametrize("raw", [
    _llm_row("uncertain", "unsupported_reason"),
    _llm_row("uncertain"),
    _llm_row("candidate_rule_relevant", "semantic_relation_unclear"),
    _llm_row("no_rule_match", "claim_context_insufficient"),
    _llm_row("uncertain", "semantic_relation_unclear", company_illegal=False),
    "not json",
])
def test_invalid_or_overreaching_llm_reason_is_module_fallback(raw):
    result = _result(mode="llm", raw=raw)
    assert result["relation_status"] == "fallback"
    assert result["relation_status_reason"] == "invalid_output"
    assert result["legal_claim_relations"][0] == {
        "claim_index": 0, "evidence_ref": "rule-1", "relation": "uncertain",
    }


def test_invalid_evidence_ref_is_not_semantic_uncertainty():
    raw = json.dumps({"relations": [{"claim_index": 0, "evidence_ref": "not-this-retrieval",
                                    "relation": "candidate_rule_relevant"}]})
    result = _result(mode="llm", raw=raw)
    assert result["relation_status_reason"] == "invalid_evidence_ref"
    assert "reason" not in result["legal_claim_relations"][0]


def test_invalid_source_ref_has_module_level_reason():
    result = build_legal_claim_relations([CLAIM], [{"source": "file.md", "text": ""}])
    assert result == {"legal_claim_relations": [], "relation_status": "fallback",
                      "relation_status_reason": "invalid_evidence_ref"}


def test_conflicting_duplicate_chunk_ref_has_module_level_reason():
    result = build_legal_claim_relations([CLAIM], [CHUNK, {**CHUNK, "text": "不同文本"}])
    assert result["relation_status_reason"] == "invalid_evidence_ref"
    assert result["legal_claim_relations"][0]["relation"] == "uncertain"
    assert "reason" not in result["legal_claim_relations"][0]


def test_llm_exception_has_execution_reason():
    def fail(_):
        raise RuntimeError("fake failure")

    result = build_legal_claim_relations([CLAIM], [CHUNK], mode="llm", llm_call=fail)
    assert result["relation_status_reason"] == "execution_error"
    assert "reason" not in result["legal_claim_relations"][0]


def test_deterministic_exception_has_execution_reason(monkeypatch):
    monkeypatch.setattr(legal_claim_relation, "_deterministic_relation", lambda *_: 1 / 0)
    result = _result()
    assert result["relation_status"] == "fallback"
    assert result["relation_status_reason"] == "execution_error"


@pytest.mark.parametrize("need_rag,chunks,status", [
    (False, [CHUNK], "skipped_by_gate"),
    (True, [], "executed_no_hit"),
])
def test_retrieval_status_stays_separate_from_relation_reason(monkeypatch, need_rag, chunks, status):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **_: {"need_rag": need_rag})
    monkeypatch.setattr(legal_agent, "retrieve", lambda *_args, **_kwargs: {
        "context": RULE if chunks else "", "chunks": chunks,
        "sources": [{"source": "food_safety.md"}] if chunks else [],
    })

    def fake_llm(prompt):
        if "待审核声明 draft" in prompt:
            return json.dumps({"legal_risks": [], "safe_points": ["safe"], "revision_advice": [],
                               "public_opinion_suggestions": [], "integrated_revision_tasks": []})
        return "not json"  # P30 uses its deterministic fallback; relation has no evidence.

    monkeypatch.setattr(legal_agent, "call_llm", fake_llm)
    result = legal_agent.run({"event": "食品投诉", "draft": "目前不存在违法行为", "redteam_review": {}})
    relation = result["_metadata"]["claim_evidence_relation"]
    assert result["_metadata"]["rag"]["retrieval_status"] == status
    assert relation == {"legal_claim_relations": [], "relation_status": "skipped"}


def test_coverage_status_unchanged_and_reason_reachable_from_trace():
    relation = _result({**CLAIM, "claim": "目前不存在违法行为"})
    coverage = build_claim_coverage([{**CLAIM, "claim": "目前不存在违法行为"}], relation)
    assert coverage["claim_coverage"][0]["legal_rule_status"] == "uncertain"
    trace = _collect_trace_metadata("legal", {"rag": {}, "claim_evidence_relation": relation,
                                             "claim_coverage": coverage})
    assert trace["rag"]["legal_claim_relations"][0]["reason"] == "claim_context_insufficient"


def test_prompt_and_review_policy_ignore_reason():
    payload = {"event": "食品投诉", "draft": "目前不存在违法行为", "redteam_review": {}}
    before = legal_agent._build_legal_prompt(payload, "法规文本")
    payload["claim_evidence_relation"] = _result({**CLAIM, "claim": "目前不存在违法行为"})
    assert legal_agent._build_legal_prompt(payload, "法规文本") == before

    state = AgentState("reason-review", "plan", "食品投诉")
    policy_before = evaluate_human_policy(state, {"passed": True})
    state.add_trace({"agent": "legal", "rag": payload["claim_evidence_relation"]})
    assert evaluate_human_policy(state, {"passed": True}) == policy_before


def test_deterministic_reason_is_repeatable_and_frozen_labels_unchanged():
    assert _result() == _result()
    assert _result({**CLAIM, "claim": "目前不存在违法行为"}) == _result({**CLAIM, "claim": "目前不存在违法行为"})
