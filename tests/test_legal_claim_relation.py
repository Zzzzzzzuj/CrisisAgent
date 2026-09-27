import json
from copy import deepcopy
from pathlib import Path

import pytest

from backend.agents import legal_agent
from backend.agents.legal_claim_relation import build_legal_claim_relations, evidence_ref
from backend.config import get_config
from backend.core.executor import execute
from backend.core.state import AgentState
from backend.schemas import CrisisRunRequest
from backend.storage import get_session
from backend.workflow import run_crisis_workflow
from evaluation.legal_claim_relation import evaluate_relation_cases


RULE = "食品生产经营者不得使用超过保质期的食品原料。"
GUIDANCE = "企业危机回应应当说明核查进展，并保持对公众担忧的回应。"
CLAIM = "使用过期原料可能违反食品安全规定"


def _claim(text=CLAIM, legal=True, fact=False):
    return {"claim": text, "requires_legal_rule": legal, "requires_case_fact": fact}


def _chunk(text=RULE, chunk_id="rule-1", **extra):
    return {"chunk_id": chunk_id, "source": "food_safety.md", "text": text, **extra}


def _rows(claims=None, chunks=None, **kwargs):
    result = build_legal_claim_relations(
        [_claim()] if claims is None else claims,
        [_chunk()] if chunks is None else chunks,
        **kwargs,
    )
    return result["legal_claim_relations"]


@pytest.mark.parametrize("text,expected", [
    (RULE, "candidate_rule_relevant"),
    ("餐饮经营者禁止使用过期食材。", "candidate_rule_relevant"),
    ("处理个人信息必须遵守相关隐私规定。", "no_rule_match"),
    (GUIDANCE, "no_rule_match"),
])
def test_deterministic_rule_relation(text, expected):
    assert _rows(chunks=[_chunk(text)])[0]["relation"] == expected


def test_mixed_claim_is_not_case_fact_verification():
    rows = _rows(claims=[_claim("使用过期原料可能违反食品安全规定", fact=True)])
    assert rows == [{"claim_index": 0, "evidence_ref": "rule-1", "relation": "candidate_rule_relevant"}]


def test_case_fact_only_claim_is_skipped():
    assert _rows(claims=[_claim("经调查，本批次未使用过期原料", legal=False, fact=True)]) == []


def test_vague_non_violation_claim_is_uncertain():
    assert _rows(claims=[_claim("目前不存在违法行为", fact=True)])[0]["relation"] == "uncertain"


def test_duplicate_evidence_ref_is_deduplicated():
    assert len(_rows(chunks=[_chunk(), _chunk()])) == 1


def test_conflicting_duplicate_ref_cannot_be_relevant():
    assert _rows(chunks=[_chunk(), _chunk(GUIDANCE)])[0]["relation"] == "uncertain"


def test_no_evidence_skips():
    assert build_legal_claim_relations([_claim()], [])["relation_status"] == "skipped"


def test_missing_ref_source_or_text_is_not_candidate():
    assert _rows(chunks=[{"source": "file.md", "text": ""}]) == []


def test_ref_hash_uses_full_original_text_not_preview():
    raw = _chunk(RULE + "后缀" * 200, chunk_id=None)
    altered = _chunk(RULE + "后缀" * 199, chunk_id=None)
    assert evidence_ref(raw).startswith("content:")
    assert evidence_ref(raw) != evidence_ref(altered)
    assert _rows(chunks=[raw])[0]["evidence_ref"] == evidence_ref(raw)


def _llm(raw, claims=None, chunks=None):
    return build_legal_claim_relations(
        [_claim()] if claims is None else claims,
        [_chunk()] if chunks is None else chunks,
        mode="llm", llm_call=lambda _: raw,
    )


@pytest.mark.parametrize("raw", [
    "not json",
    '{"relations":[{"claim_index":0,"evidence_ref":"rule-1"}]}',
    '{"relations":[{"claim_index":0,"evidence_ref":"rule-1","relation":"supports"}]}',
    '{"relations":[{"claim_index":0,"evidence_ref":"unknown","relation":"candidate_rule_relevant"}]}',
    '{"relations":[{"claim_index":4,"evidence_ref":"rule-1","relation":"candidate_rule_relevant"}]}',
    '{"relations":[{"claim_index":0,"evidence_ref":"rule-1","relation":"candidate_rule_relevant","claim_true":true}]}',
    '{"relations":[{"claim_index":0,"evidence_ref":"rule-1","relation":"candidate_rule_relevant","company_illegal":false}]}',
    '{"relations":[{"claim_index":0,"evidence_ref":"rule-1","relation":"candidate_rule_relevant"},{"claim_index":0,"evidence_ref":"rule-1","relation":"no_rule_match"}]}',
])
def test_invalid_batch_response_falls_back_to_uncertain(raw):
    result = _llm(raw)
    assert result["relation_status"] == "fallback"
    assert result["legal_claim_relations"][0]["relation"] == "uncertain"


def test_llm_exception_falls_back_to_uncertain():
    def fail(_):
        raise RuntimeError("fake failure")

    result = build_legal_claim_relations([_claim()], [_chunk()], mode="llm", llm_call=fail)
    assert result["relation_status"] == "fallback"
    assert result["legal_claim_relations"][0]["relation"] == "uncertain"


def test_batch_llm_called_once_with_minimal_input():
    calls = []
    def fake(prompt):
        calls.append(prompt)
        assert "claims" in prompt and "evidence" in prompt
        assert "redteam_review" not in prompt and "context_pack" not in prompt
        return json.dumps({"relations": [
            {"claim_index": index, "evidence_ref": ref, "relation": "uncertain",
             "reason": "semantic_relation_unclear"}
            for index in (0, 1) for ref in ("rule-1", "rule-2")
        ]})

    result = build_legal_claim_relations([_claim(), _claim("食品原料不得过期")],
                                         [_chunk(), _chunk("经营者不得使用过期原料。", "rule-2")],
                                         mode="llm", llm_call=fake)
    assert len(calls) == 1
    assert len(result["legal_claim_relations"]) == 4


def test_llm_guidance_cannot_be_upgraded_to_rule():
    raw = '{"relations":[{"claim_index":0,"evidence_ref":"rule-1","relation":"candidate_rule_relevant"}]}'
    assert _llm(raw, chunks=[_chunk(GUIDANCE)])["legal_claim_relations"][0]["relation"] == "no_rule_match"


def test_fake_llm_handles_semantic_paraphrase_without_claim_verdict():
    raw = '{"relations":[{"claim_index":0,"evidence_ref":"rule-1","relation":"candidate_rule_relevant"}]}'
    result = _llm(raw, claims=[_claim("食品原料过保使用可能构成合规风险")])
    assert result["legal_claim_relations"][0]["relation"] == "candidate_rule_relevant"


def test_retrieval_and_rerank_scores_do_not_upgrade_relation():
    base = _chunk(GUIDANCE, score=0.1, rerank_score=0.1)
    high = deepcopy(base)
    high.update(score=0.99, rerank_score=0.99)
    assert _rows(chunks=[base]) == _rows(chunks=[high])


def test_deterministic_same_input_same_output():
    assert _rows() == _rows()


def test_mock_legal_does_not_invent_rag_evidence(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    result = legal_agent.run({"event": "食品安全投诉", "draft": CLAIM, "redteam_review": {}})
    assert result["_metadata"]["claim_evidence_relation"] == {
        "legal_claim_relations": [], "relation_status": "skipped",
    }


def test_shadow_relation_does_not_change_legal_output_or_prompt(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    get_config.cache_clear()
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **_: {"need_rag": True})
    monkeypatch.setattr(legal_agent, "retrieve", lambda *_args, **_kwargs: {
        "context": RULE, "chunks": [_chunk()], "sources": [{"source": "food_safety.md"}],
    })
    prompts = []
    def fake(prompt):
        prompts.append(prompt)
        if "只判断候选规则文本" in prompt:
            return '{"relations":[{"claim_index":0,"evidence_ref":"rule-1","relation":"candidate_rule_relevant"}]}'
        if "待审核声明 draft" in prompt:
            return json.dumps({"legal_risks": [], "safe_points": ["safe"], "revision_advice": [],
                               "public_opinion_suggestions": [], "integrated_revision_tasks": []})
        return "not json"

    monkeypatch.setattr(legal_agent, "call_llm", fake)
    payload = {"event": "食品安全投诉", "draft": CLAIM, "redteam_review": {}}
    result = legal_agent.run(payload)
    assert result["safe_points"] == ["safe"]
    assert result["_metadata"]["claim_evidence_relation"]["legal_claim_relations"][0]["relation"] == "candidate_rule_relevant"
    assert result["_metadata"]["rag"]["evidence_chunks"][0]["evidence_ref"] == "rule-1"
    assert "candidate_rule_relevant" not in next(prompt for prompt in prompts if "待审核声明 draft" in prompt)


def test_relation_module_exception_does_not_interrupt_legal_review(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    get_config.cache_clear()
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **_: {"need_rag": True})
    monkeypatch.setattr(legal_agent, "retrieve", lambda *_args, **_kwargs: {
        "context": RULE, "chunks": [_chunk()], "sources": [{"source": "food_safety.md"}],
    })
    monkeypatch.setattr(legal_agent, "build_legal_claim_relations", lambda *_args, **_kwargs: 1 / 0)
    def fake(prompt):
        if "待审核声明 draft" in prompt:
            return json.dumps({"legal_risks": [], "safe_points": ["safe"], "revision_advice": [],
                               "public_opinion_suggestions": [], "integrated_revision_tasks": []})
        return "not json"

    monkeypatch.setattr(legal_agent, "call_llm", fake)
    result = legal_agent.run({"event": "食品安全投诉", "draft": CLAIM, "redteam_review": {}})
    assert result["safe_points"] == ["safe"]
    assert result["_metadata"]["claim_evidence_relation"] == {
        "legal_claim_relations": [], "relation_status": "fallback",
        "relation_status_reason": "execution_error",
    }


def test_fixed_workflow_saves_shadow_relation_in_trace_and_session(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    response = run_crisis_workflow(CrisisRunRequest(event="食品安全投诉"))
    rag = response.model_dump()["agent_trace"][3]["rag"]
    assert rag["relation_status"] == "skipped"
    assert rag["legal_claim_relations"] == []
    assert get_session(response.session_id)["legal_claim_relation"]["relation_status"] == "skipped"


def test_dynamic_executor_saves_shadow_relation_in_state_and_trace(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()
    state = AgentState("relation-test", "plan", "食品安全投诉")
    state.set_result("writer", {"statement": CLAIM})
    result = execute({"plan_id": "plan", "plan": [{"agent": "legal", "reason": "review"}]}, state)
    assert result["executed_agents"] == ["legal"]
    assert state.metadata["legal_claim_relation"]["relation_status"] == "skipped"
    assert result["execution_trace"][0]["rag"]["relation_status"] == "skipped"


def test_frozen_relation_set_has_labeled_and_skipped_cases():
    path = Path(__file__).resolve().parents[1] / "data" / "legal_claim_relation_cases.json"
    metrics = evaluate_relation_cases(path)
    assert metrics["total_cases"] == 22
    assert metrics["labeled_pairs"] == 20
    assert metrics["skipped_case_fact_only"] == 2
    assert set(metrics["per_class_total"]) == {
        "candidate_rule_relevant", "no_rule_match", "uncertain",
    }
