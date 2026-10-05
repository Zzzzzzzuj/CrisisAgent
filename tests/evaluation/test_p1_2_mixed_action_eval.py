"""Offline checks for the frozen P1.2 evaluation boundary."""

import json

import pytest

from evaluation import p1_2_mixed_action_eval as eval_runner


def test_all_frozen_controlled_cases_qualify_without_provider():
    result = eval_runner.preflight()
    assert result["dataset_sha256"] == eval_runner.DATASET_SHA256
    assert len(result["controlled_qualifications"]) == 3
    assert all(row["qualified"] for row in result["controlled_qualifications"])
    assert all([item["action"] for item in row["eligible_actions"]] == eval_runner.EXPECTED_ACTIONS
               for row in result["controlled_qualifications"])
    assert result["natural_case_ids"] == ["privacy-01", "quality-02"]


def test_validator_negative_controls_are_offline_and_denied():
    result = eval_runner.preflight()["negative_controls"]
    assert result["fact_dependent_retrieval_denied"] is True
    assert result["outside_eligibility_denied"] is True
    assert result["budget_exhausted_denied"] is True
    assert result["reason_codes"] == ["fact_dependent_legal_query", "action_not_eligible",
                                      "tool_budget_exhausted"]


def test_real_mode_requires_explicit_process_intent(monkeypatch):
    monkeypatch.delenv("AGENT_MODE", raising=False)
    monkeypatch.setenv("OFFLINE_EVAL", "1")
    with pytest.raises(RuntimeError, match="explicit process AGENT_MODE=llm"):
        eval_runner._provider_config()


def test_no_confirmation_cannot_create_provider_run(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("OFFLINE_EVAL", "1")
    with pytest.raises(RuntimeError, match="confirm-real-provider"):
        eval_runner.run(output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_natural_run_also_requires_explicit_confirmation(tmp_path):
    with pytest.raises(RuntimeError, match="confirm-real-provider"):
        eval_runner.run_natural(output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_frozen_human_response_is_not_treated_as_independent_verification():
    data, _ = eval_runner._frozen_data()
    provided = data["controlled_cases"][1]
    observation = eval_runner._human_observation(provided, "frozen-c2")
    assert observation["verification_status"] == "human_asserted"
    assert observation["source"] == "human_provided"
    assert "fact_text" not in observation


def test_report_action_allowlist_excludes_sensitive_content():
    action = {"selected_action": "REQUEST_HUMAN_FACT", "claim": "private claim",
              "query": "private query", "prompt": "private prompt", "text": "private evidence"}
    assert eval_runner._safe_action(action) == {"selected_action": "REQUEST_HUMAN_FACT"}


def test_controlled_runner_records_observation_transition_without_real_network(monkeypatch):
    from backend.agents import legal_agent

    data, _ = eval_runner._frozen_data()
    case = data["controlled_cases"][0]
    monkeypatch.setattr(legal_agent, "call_llm", lambda _prompt: (
        '{"action":"RETRIEVE_LEGAL_EVIDENCE","reason_code":"LEGAL_RULE_GAP","target_claim_index":0}'
    ))
    monkeypatch.setattr(eval_runner, "retrieve", lambda _query, top_k: {
        "chunks": [{"chunk_id": "rule", "source": "frozen-kb", "text": "法律规定不得使用过期食品原料。"}],
        "sources": [{"chunk_id": "rule", "source": "frozen-kb", "score": 0.8}],
    })
    monkeypatch.setattr(eval_runner, "build_legal_claim_relations", lambda _claims, _chunks, **_kw: {
        "legal_claim_relations": [{"claim_index": 0, "evidence_ref": "rule",
                                   "relation": "candidate_rule_relevant"}], "relation_status": "ok",
    })
    result = eval_runner._execute_controlled(case, [], {"name": "unknown"})
    assert result["first_action"] == "RETRIEVE_LEGAL_EVIDENCE"
    assert result["next_action"] == "REQUEST_HUMAN_FACT"
    assert result["legal_rule_status_after"] == "candidate_found"
    assert result["case_fact_status_after"] == "unresolved"
    assert result["observation_driven_strategy_change"] is True
    assert result["action_proposal_real_provider"] is False


def test_no_hit_is_not_counted_as_strategy_success(monkeypatch):
    from backend.agents import legal_agent

    data, _ = eval_runner._frozen_data()
    case = data["controlled_cases"][0]
    monkeypatch.setattr(legal_agent, "call_llm", lambda _prompt: (
        '{"action":"RETRIEVE_LEGAL_EVIDENCE","reason_code":"LEGAL_RULE_GAP","target_claim_index":0}'
    ))
    monkeypatch.setattr(eval_runner, "retrieve", lambda _query, top_k: {"chunks": [], "sources": []})
    result = eval_runner._execute_controlled(case, [], {"name": "unknown"})
    assert result["retrievals"][0]["status"] == "no_hit"
    assert result["first_observation_changed_gap"] is False
    assert result["observation_driven_strategy_change"] is False


def test_infrastructure_resume_skips_completed_prefix_without_resampling(tmp_path):
    data, _ = eval_runner._frozen_data()
    run_id = "frozen-infrastructure-run"
    prefix = tmp_path / f"p1_2_mixed_action_{run_id}"
    prefix.with_name(prefix.name + "_summary.json").write_text(
        json.dumps({"status": "NETWORK_GUARD_BLOCKED"}), encoding="utf-8")
    prefix.with_name(prefix.name + "_metadata.json").write_text(
        json.dumps({"dataset_sha256": eval_runner.DATASET_SHA256}), encoding="utf-8")
    prefix.with_suffix(".jsonl").write_text(json.dumps({"case_id": "C1-food-expiry"}) + "\n", encoding="utf-8")
    remaining = eval_runner._remaining_cases(data["controlled_cases"], tmp_path, run_id)
    assert [case["case_id"] for case in remaining] == ["C2-privacy-notification", "C3-product-recall"]
    with pytest.raises(ValueError, match="Invalid infrastructure parent"):
        eval_runner._remaining_cases(data["controlled_cases"], tmp_path, "../escape")
