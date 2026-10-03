import json
from pathlib import Path

import pytest

from evaluation.real_llm_eval_harness import RealLLMEvalRun, read_case_records, rebuild_summary


def _metadata():
    return {
        "frozen_file": "fixtures/frozen.json", "frozen_sha256": "abc123",
        "selected_case_ids": [f"case-{i}" for i in range(1, 6)],
        "AGENT_MODE": "llm", "OFFLINE_EVAL": "0", "provider": "fake",
        "model": "fake-model", "external_provider_allowed": True,
        "other_external_network_allowed": False, "git_branch": "test",
        "git_commit": "deadbeef", "working_tree_dirty": True,
        "evaluation_started_at": None,
        "api_key": "must-not-persist", "prompt": "must-not-persist",
    }


def _result(case):
    return {
        "case_id": case["case_id"], "ground_truth": {"expected_fact_gap": True},
        "model_provider": "fake", "model_name": "fake-model",
        "runtime_final_state": "COMPLETED", "fact_gap": {"expected": True, "detected": True,
        "claim_count": 1, "claim_indices": [0], "requires_case_fact_count": 1,
        "requires_legal_rule_count": 0},
        "human_fact": {}, "legal": {}, "loop": {"observation_types": ["gap_found"]},
        "reliability": {"llm_call_count": 2, "fallback_count": 1,
                        "fallback_agents": ["legal"]},
        "trace": {"trace_available": True},
        "usage": {"usage_available": False, "prompt_tokens": 9000},
        # These fields are deliberately outside the schema and must be dropped.
        "event": "secret event body", "prompt": "secret prompt", "authorization": "secret",
    }


def _cases():
    return [{"case_id": f"case-{i}", "ground_truth": {"expected_fact_gap": True}}
            for i in range(1, 6)]


def test_five_cases_are_incrementally_persisted_and_summary_rebuilds(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    seen_durable_counts = []

    def execute(case):
        result = _result(case)
        # Prior case lines must already be readable before the next case starts.
        seen_durable_counts.append(len(read_case_records(run.jsonl_path)))
        return result

    summary = run.run_cases(_cases(), execute)
    records = read_case_records(run.jsonl_path)
    assert seen_durable_counts == [0, 1, 2, 3, 4]
    assert len(records) == 5
    assert summary == {**rebuild_summary(run.jsonl_path), "run_id": run.run_id,
                       "generated_at": summary["generated_at"]}
    assert json.loads(run.summary_path.read_text(encoding="utf-8"))["total_cases"] == 5


def test_process_crash_keeps_prior_cases(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    calls = 0

    def crash_on_third(case):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt("simulated process crash")
        return _result(case)

    with pytest.raises(KeyboardInterrupt):
        run.run_cases(_cases(), crash_on_third)
    assert [row["case_id"] for row in read_case_records(run.jsonl_path)] == ["case-1", "case-2"]


def test_case_error_is_structured_and_other_cases_continue(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())

    def fail_second(case):
        if case["case_id"] == "case-2":
            raise RuntimeError("prompt and secret must not appear")
        return _result(case)

    summary = run.run_cases(_cases()[:3], fail_second)
    rows = read_case_records(run.jsonl_path)
    assert [row["status"] for row in rows] == ["SUCCESS", "ERROR", "SUCCESS"]
    assert rows[1]["error"] == {"type": "RuntimeError", "stage": "case_execution",
                                 "code": "CASE_EXECUTION_ERROR"}
    assert summary["error_cases"] == 1


def test_error_payload_is_allowlisted(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    run.append_case({"case_id": "safe-id", "status": "ERROR", "error": {
        "type": "ValueError", "stage": "parse", "code": "BAD_JSON",
        "message": "private prompt text", "api_key": "secret",
    }})
    error = read_case_records(run.jsonl_path)[0]["error"]
    assert error == {"type": "ValueError", "stage": "parse", "code": "BAD_JSON"}


def test_report_excludes_secrets_prompt_and_event_body(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    run.run_cases(_cases()[:1], _result)
    combined = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    assert "must-not-persist" not in combined
    assert "secret event body" not in combined
    assert "secret prompt" not in combined
    assert "api_key" not in combined


def test_diagnosis_allowlist_rejects_text_and_untrusted_identifiers(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    run.append_case({
        "case_id": "safe-id",
        "diagnosis": {
            "claims": [{"claim_index": 0, "claim_origin": "PRIVATE_EVENT_TEXT",
                        "requires_case_fact": True, "requires_legal_rule": False,
                        "coverage_status": "PRIVATE_DRAFT_TEXT",
                        "coverage_reason": "PRIVATE_EVIDENCE_TEXT",
                        "action_dependency": True, "fact_source_status": "PRIVATE_PROMPT_TEXT",
                        "claim": "PRIVATE_CLAIM_TEXT"}],
            "event_fact_gap_candidates": [{"candidate_index": 0, "claim_index": 0,
                                           "candidate_type": "PRIVATE_EVENT_TEXT"}],
            "human_fact_dependency": {"request_id": "PRIVATE_API_KEY_TEXT", "claim_index": 0,
                                      "claim_origin": "WRITER", "coverage_reason": "PRIVATE_EVIDENCE_TEXT",
                                      "question": "PRIVATE_QUESTION_TEXT"},
            "writer_introduction_status": "PRIVATE_AUTHORIZATION_TEXT",
            "event": "PRIVATE_EVENT_TEXT", "draft": "PRIVATE_DRAFT_TEXT",
        },
    })

    saved = read_case_records(run.jsonl_path)[0]["diagnosis"]
    assert saved["claims"][0]["claim_origin"] == "UNKNOWN"
    assert saved["claims"][0]["coverage_status"] is None
    assert saved["claims"][0]["coverage_reason"] is None
    assert saved["claims"][0]["fact_source_status"] == "UNKNOWN"
    assert saved["event_fact_gap_candidates"][0]["candidate_type"] == "UNKNOWN"
    assert saved["human_fact_dependency"]["request_id"] is None
    assert saved["writer_introduction_status"] == "UNKNOWN"
    persisted = run.jsonl_path.read_text(encoding="utf-8")
    for text in ("PRIVATE_EVENT_TEXT", "PRIVATE_DRAFT_TEXT", "PRIVATE_EVIDENCE_TEXT",
                 "PRIVATE_PROMPT_TEXT", "PRIVATE_CLAIM_TEXT", "PRIVATE_API_KEY_TEXT",
                 "PRIVATE_QUESTION_TEXT", "PRIVATE_AUTHORIZATION_TEXT"):
        assert text not in persisted


def test_missing_usage_is_null_not_estimated(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    run.run_cases(_cases()[:1], _result)
    usage = read_case_records(run.jsonl_path)[0]["usage"]
    assert usage == {"prompt_tokens": None, "completion_tokens": None,
                     "total_tokens": None, "usage_available": False}


def test_action_proposal_telemetry_is_persisted_without_business_text(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    result = _result({"case_id": "case-1"})
    result["loop"]["decision_telemetry"] = [{
        "round": 0,
        "previous_observation_type": None,
        "eligible_action_count": 2,
        "eligible_actions": [
            {"action": "REQUEST_HUMAN_FACT", "target_claim_index": 0},
            {"action": "REQUEST_HUMAN_FACT", "target_claim_index": 1},
        ],
        "eligible_target_claim_indices": [0, 1],
        "deterministic_baseline_action": "REQUEST_HUMAN_FACT",
        "deterministic_baseline_target_claim_index": 0,
        "proposal_called": True,
        "proposal_status": "VALID",
        "proposal_action": "REQUEST_HUMAN_FACT",
        "proposal_reason_code": "CASE_FACT_GAP",
        "proposal_target_claim_index": 1,
        "validator_called": True,
        "validator_allowed": True,
        "validator_reason_code": "eligible_action",
        "fallback_used": False,
        "fallback_reason_code": None,
        "executed_action": "REQUEST_HUMAN_FACT",
        "executed_target_claim_index": 1,
        "result_observation_type": "case_fact_unresolved",
        "result_observation_status": "human_fact_required",
        "remaining_rounds": 3,
        "remaining_tool_calls": 2,
        "event": "PRIVATE_EVENT_TEXT",
        "claim": "PRIVATE_CLAIM_TEXT",
        "prompt": "PRIVATE_PROMPT_TEXT",
    }]
    run.run_cases([{"case_id": "case-1"}], lambda _case: result)
    saved = read_case_records(run.jsonl_path)[0]["loop"]["decision_telemetry"][0]
    assert saved["eligible_action_count"] == 2
    assert saved["eligible_target_claim_indices"] == [0, 1]
    assert saved["deterministic_baseline_target_claim_index"] == 0
    assert saved["proposal_status"] == "VALID"
    assert saved["validator_called"] is True
    assert saved["validator_allowed"] is True
    assert saved["executed_target_claim_index"] == 1
    persisted = run.jsonl_path.read_text(encoding="utf-8")
    for text in ("PRIVATE_EVENT_TEXT", "PRIVATE_CLAIM_TEXT", "PRIVATE_PROMPT_TEXT"):
        assert text not in persisted


def test_multi_fact_sequence_is_allowlisted_without_business_text(tmp_path):
    run = RealLLMEvalRun(tmp_path, {
        **_metadata(),
        "human_response_strategy": "repeat_frozen_unavailable",
        "max_fact_responses": 3,
        "multi_fact_input_enabled": True,
    })
    result = _result({"case_id": "case-1"})
    result["human_fact"] = {
        "requested": True,
        "request_count": 2,
        "response_count": 2,
        "response_type": "FACT_UNAVAILABLE",
        "response_http_status": 200,
        "resume_result": "queued",
        "final_wait_type": "FINAL_REVIEW",
        "response_strategy": "repeat_frozen_unavailable",
        "multi_fact_input_enabled": True,
        "runner_stop_reason": "final_review",
        "human_asserted_present": False,
        "human_asserted_claim_count": 0,
        "human_fact_sequence": [{
            "sequence_index": 0,
            "request_present": True,
            "claim_index": 0,
            "wait_type": "FACT_INPUT",
            "response_type": "FACT_UNAVAILABLE",
            "response_http_status": 200,
            "resume_status": "queued",
            "next_wait_type": "FACT_INPUT",
            "observation_type": "fact_unavailable",
            "current_claim_index": 1,
            "claim_progress": [
                {"claim_index": 0, "status": "ATTEMPTED_UNRESOLVED"},
                {"claim_index": 1, "status": "UNTOUCHED"},
                {"claim_index": 2, "status": "PRIVATE_CLAIM_TEXT"},
            ],
            "remaining_claim_count": 1,
            "round_count": 2,
            "remaining_rounds": 1,
            "human_asserted_claim_count": 0,
            "request_id": "PRIVATE_REQUEST_ID",
            "question": "PRIVATE_QUESTION_TEXT",
            "fact_text": "PRIVATE_FACT_TEXT",
            "claim": "PRIVATE_CLAIM_TEXT",
            "event": "PRIVATE_EVENT_TEXT",
            "prompt": "PRIVATE_PROMPT_TEXT",
            "raw_response": "PRIVATE_RAW_RESPONSE",
        }],
    }
    run.run_cases([{"case_id": "case-1"}], lambda _case: result)
    saved = read_case_records(run.jsonl_path)[0]["human_fact"]
    sequence = saved["human_fact_sequence"][0]
    assert saved["response_count"] == 2
    assert saved["response_strategy"] == "repeat_frozen_unavailable"
    assert sequence["claim_progress"] == [
        {"claim_index": 0, "status": "ATTEMPTED_UNRESOLVED"},
        {"claim_index": 1, "status": "UNTOUCHED"},
    ]
    assert "request_id" not in sequence
    persisted = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    for text in ("PRIVATE_REQUEST_ID", "PRIVATE_QUESTION_TEXT", "PRIVATE_FACT_TEXT",
                 "PRIVATE_CLAIM_TEXT", "PRIVATE_EVENT_TEXT", "PRIVATE_PROMPT_TEXT",
                 "PRIVATE_RAW_RESPONSE"):
        assert text not in persisted


def test_metadata_records_explicit_multi_fact_configuration(tmp_path):
    run = RealLLMEvalRun(tmp_path, {
        **_metadata(),
        "human_response_strategy": "repeat_frozen_unavailable",
        "max_fact_responses": 3,
        "multi_fact_input_enabled": True,
    })
    saved = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert saved["human_response_strategy"] == "repeat_frozen_unavailable"
    assert saved["max_fact_responses"] == 3
    assert saved["multi_fact_input_enabled"] is True


def test_runtime_cleanup_and_stdout_truncation_do_not_affect_reports(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    run = RealLLMEvalRun(tmp_path / "reports", _metadata())
    run.run_cases(_cases()[:2], _result)
    for path in runtime.iterdir():
        path.unlink()
    runtime.rmdir()
    capsys.readouterr()
    assert len(read_case_records(run.jsonl_path)) == 2
    assert run.summary_path.exists()


def test_repeated_runs_use_distinct_ids_and_never_overwrite(tmp_path):
    first = RealLLMEvalRun(tmp_path, _metadata())
    second = RealLLMEvalRun(tmp_path, _metadata())
    assert first.run_id != second.run_id
    first.run_cases(_cases()[:1], _result)
    second.run_cases(_cases()[:2], _result)
    assert len(read_case_records(first.jsonl_path)) == 1
    assert len(read_case_records(second.jsonl_path)) == 2


def test_fixed_ground_truth_allowlist_drops_free_text(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    run.run_cases([{"case_id": "c", "ground_truth": {
        "expected_fact_gap": True, "event": "private text", "claim": "private claim"}}], _result)
    ground_truth = read_case_records(run.jsonl_path)[0]["ground_truth"]
    assert ground_truth == {"expected_fact_gap": True}


def test_metadata_writes_required_keys_without_secret_fields(tmp_path):
    run = RealLLMEvalRun(tmp_path, _metadata())
    saved = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert {"run_id", "frozen_file", "frozen_sha256", "selected_case_ids", "AGENT_MODE",
            "OFFLINE_EVAL", "provider", "model", "external_provider_allowed",
            "other_external_network_allowed", "git_branch", "git_commit",
            "working_tree_dirty", "evaluation_started_at"} <= saved.keys()
    assert "api_key" not in saved
    assert "prompt" not in saved
