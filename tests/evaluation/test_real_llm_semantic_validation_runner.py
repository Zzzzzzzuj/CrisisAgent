import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from evaluation.real_llm_eval_harness import RealLLMEvalRun, read_case_records, rebuild_summary
from scripts import run_real_llm_semantic_validation as runner

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SCRIPT = REPO_ROOT / "scripts" / "run_real_llm_semantic_validation.py"


def _prepare_isolated_project_env(monkeypatch, tmp_path, backend_text="", root_text=""):
    from backend import env as env_module

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir(exist_ok=True)
    (backend_dir / ".env").write_text(backend_text, encoding="utf-8")
    (tmp_path / ".env").write_text(root_text, encoding="utf-8")
    project_loader = env_module.load_project_env
    monkeypatch.setattr(
        runner, "load_project_env",
        lambda: project_loader(project_root=tmp_path, backend_dir=backend_dir),
    )
    # Prevent config-module imports from consulting the developer's real .env;
    # the runner's explicit loader above is the only source in these tests.
    monkeypatch.setattr(env_module, "load_project_env", lambda *args, **kwargs: None)
    for module_name in ("backend.config", "backend.llm.config"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "load_project_env"):
            monkeypatch.setattr(module, "load_project_env", lambda *args, **kwargs: None)


def _clear_llm_environment(monkeypatch):
    for name in ("AGENT_MODE", "OFFLINE_EVAL", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)


def test_real_config_loads_dummy_credential_from_project_env(monkeypatch, tmp_path):
    _clear_llm_environment(monkeypatch)
    monkeypatch.setenv("AGENT_MODE", "llm")
    _prepare_isolated_project_env(
        monkeypatch, tmp_path,
        backend_text="LLM_API_KEY=test-key\nLLM_BASE_URL=https://api.deepseek.com\n"
                     "LLM_MODEL=deepseek-v4-flash\nLLM_PROVIDER=openai_compatible\n",
    )

    app_config, llm_config, host = runner._resolve_real_provider_config()

    assert app_config.agent_mode == "llm"
    assert llm_config.api_key == "test-key"
    assert llm_config.model == "deepseek-v4-flash"
    assert host == "api.deepseek.com"


def test_dotenv_cannot_authorize_real_mode_without_process_intent(monkeypatch, tmp_path):
    _clear_llm_environment(monkeypatch)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / ".env").write_text(
        "AGENT_MODE=llm\nLLM_API_KEY=test-key\n", encoding="utf-8",
    )
    _prepare_isolated_project_env(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="requires AGENT_MODE=llm"):
        runner._resolve_real_provider_config()


def test_process_mock_blocks_real_mode_even_if_dotenv_says_llm(monkeypatch, tmp_path):
    _clear_llm_environment(monkeypatch)
    monkeypatch.setenv("AGENT_MODE", "mock")
    _prepare_isolated_project_env(
        monkeypatch, tmp_path,
        backend_text="AGENT_MODE=llm\nLLM_API_KEY=test-key\n",
    )

    with pytest.raises(RuntimeError, match="requires AGENT_MODE=llm"):
        runner._resolve_real_provider_config()


def test_real_mode_without_any_credential_is_blocked(monkeypatch, tmp_path):
    _clear_llm_environment(monkeypatch)
    monkeypatch.setenv("AGENT_MODE", "llm")
    _prepare_isolated_project_env(
        monkeypatch, tmp_path,
        backend_text="LLM_BASE_URL=https://api.deepseek.com\n"
                     "LLM_MODEL=deepseek-v4-flash\nLLM_PROVIDER=openai_compatible\n",
    )

    with pytest.raises(RuntimeError, match="requires LLM_API_KEY"):
        runner._resolve_real_provider_config()


def test_process_credential_precedes_project_dotenv(monkeypatch, tmp_path):
    _clear_llm_environment(monkeypatch)
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "process-test-key")
    _prepare_isolated_project_env(
        monkeypatch, tmp_path,
        backend_text="LLM_API_KEY=backend-test-key\nLLM_BASE_URL=https://api.deepseek.com\n"
                     "LLM_MODEL=deepseek-v4-flash\nLLM_PROVIDER=openai_compatible\n",
        root_text="LLM_API_KEY=root-test-key\n",
    )

    _, llm_config, _ = runner._resolve_real_provider_config()

    assert llm_config.api_key == "process-test-key"


def test_direct_cli_help_bootstraps_repository_root_without_network():
    completed = subprocess.run(
        [sys.executable, str(RUNNER_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "PYTHONPATH": ""},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()
    assert "ModuleNotFoundError" not in completed.stderr


def test_direct_fake_cli_runs_five_cases_and_persists_offline_results(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(RUNNER_SCRIPT), "--mode", "fake", "--output-dir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": ""},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    cli_result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert cli_result["mode"] == "fake"
    assert cli_result["external_request_attempts_blocked"] == 0
    summary = cli_result["summary"]
    assert summary["total_cases"] == 5
    assert summary["error_cases"] == 0

    jsonl_path = Path(cli_result["jsonl_path"])
    metadata_path = jsonl_path.with_name(jsonl_path.stem + "_metadata.json")
    rows = read_case_records(jsonl_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert [row["case_id"] for row in rows] == list(runner.DEFAULT_CASE_IDS)
    assert metadata["frozen_sha256"] == runner.EXPECTED_FROZEN_SHA256
    assert metadata["AGENT_MODE"] == "mock"
    assert metadata["OFFLINE_EVAL"] == "1"


def test_frozen_slice_hash_and_order_are_fixed():
    cases, digest = runner.load_frozen_cases()
    assert digest == runner.EXPECTED_FROZEN_SHA256
    assert [case["case_id"] for case in cases] == list(runner.DEFAULT_CASE_IDS)


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_frozen_identity_is_stable_across_newline_formats(tmp_path, newline):
    source = runner.FROZEN_CASE_PATH.read_bytes()
    lf_bytes = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    variant = newline.join(lf_bytes.split(b"\n"))
    path = tmp_path / "frozen-cases.json"
    path.write_bytes(variant)

    cases, digest = runner.load_frozen_cases(path)

    assert digest == runner.EXPECTED_FROZEN_SHA256
    assert [case["case_id"] for case in cases] == list(runner.DEFAULT_CASE_IDS)


def test_frozen_hash_mismatch_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "modified.json"
    path.write_text('{"cases": []}\n', encoding="utf-8")
    monkeypatch.setattr(runner, "FROZEN_CASE_PATH", path)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        runner.load_frozen_cases()


def test_frozen_identity_rejects_real_json_content_change(tmp_path):
    source = runner.FROZEN_CASE_PATH.read_bytes()
    normalized = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    modified = normalized.replace(b"privacy-03", b"privacy-04", 1)
    assert modified != normalized
    path = tmp_path / "content-modified.json"
    path.write_bytes(modified)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        runner.load_frozen_cases(path)


def test_fake_five_case_run_uses_dynamic_api_and_persists_each_case(tmp_path):
    summary, jsonl_path, attempts = runner.run_validation(
        mode="fake", output_dir=tmp_path, continue_on_error=False,
    )
    rows = read_case_records(jsonl_path)
    assert len(rows) == 5
    assert [row["case_id"] for row in rows] == list(runner.DEFAULT_CASE_IDS)
    assert summary["total_cases"] == 5
    assert rebuild_summary(jsonl_path)["total_cases"] == 5
    assert attempts == []
    assert all(row["model_provider"] == "fake" for row in rows)
    metadata_path = jsonl_path.with_name(jsonl_path.stem + "_metadata.json")
    saved_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert saved_metadata["AGENT_MODE"] == "mock"
    assert saved_metadata["OFFLINE_EVAL"] == "1"
    persisted = jsonl_path.read_text(encoding="utf-8")
    assert all(case["event"] not in persisted for case in runner.load_frozen_cases()[0])


def test_targeted_fake_case_preserves_frozen_identity_and_only_runs_selected_case(tmp_path):
    summary, jsonl_path, attempts = runner.run_validation(
        mode="fake", output_dir=tmp_path, case_id="outage-02",
    )

    assert attempts == []
    assert summary["total_cases"] == 1
    assert [row["case_id"] for row in read_case_records(jsonl_path)] == ["outage-02"]
    metadata_path = jsonl_path.with_name(jsonl_path.stem + "_metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["selected_case_ids"] == ["outage-02"]
    assert metadata["frozen_sha256"] == runner.EXPECTED_FROZEN_SHA256


def test_targeted_case_outside_fixed_slice_is_rejected_before_run(tmp_path):
    with pytest.raises(ValueError, match="fixed frozen evaluation slice"):
        runner.run_validation(mode="fake", output_dir=tmp_path, case_id="outage-03")
    assert not list(tmp_path.iterdir())


def test_synthetic_claim_dependency_is_persisted_without_source_text(tmp_path):
    event = "PRIVATE_EVENT_COMPLETE_TEXT"
    draft = "PRIVATE_WRITER_DRAFT_COMPLETE_TEXT"
    prompt = "PRIVATE_PROMPT_COMPLETE_TEXT"
    evidence = "PRIVATE_EVIDENCE_COMPLETE_TEXT"
    secret = "PRIVATE_API_KEY_COMPLETE_TEXT"
    request_id = "12345678-1234-4234-8234-123456789abc"
    claims = [
        {"claim": "PRIVATE_EVENT_CANDIDATE_TEXT", "claim_origin": "event_fact_gap",
         "requires_case_fact": True, "requires_legal_rule": False},
        {"claim": "PRIVATE_WRITER_CLAIM_TEXT", "requires_case_fact": True,
         "requires_legal_rule": False},
    ]
    initial = {
        "human_fact_request": {"request_id": request_id, "claim_index": 0,
                               "claim": claims[0]["claim"], "question": "PRIVATE_QUESTION_TEXT"},
    }
    final = {
        "status": "WAITING_HUMAN", "event": event,
        "results": {"writer": {"statement": draft}},
        "metadata": {
            "legal_claim_extraction": {
                "legal_claims": claims,
                "event_fact_gap_detection": {"candidate_count": 1},
            },
            "legal_claim_coverage": {"claim_coverage": [
                {"claim_index": 0, "case_fact_status": "unresolved",
                 "case_fact_reason": "trusted_case_fact_unavailable"},
                {"claim_index": 1, "case_fact_status": "unresolved",
                 "case_fact_reason": "trusted_case_fact_unavailable"},
            ]},
            "legal_claim_action_recommendation": {"claim_action_recommendations": [
                {"claim_index": 0, "recommended_action": "REQUEST_HUMAN_FACT_VERIFICATION"},
                {"claim_index": 1, "recommended_action": "STOP_UNRESOLVED"},
            ]},
        },
        "trace": [{"agent": "legal", "event": event, "statement": draft,
                   "draft": draft, "prompt": prompt, "evidence_text": evidence,
                   "api_key": secret, "authorization": "PRIVATE_AUTHORIZATION_TEXT"}],
    }
    case = {"case_id": "synthetic-case", "event": event, "expected_fact_gap": True}
    result = runner._extract_case_result(case, initial, final, {}, 1.0)
    run = RealLLMEvalRun(tmp_path, {})
    run.append_case(result)
    saved = read_case_records(run.jsonl_path)[0]
    diagnosis = saved["diagnosis"]

    assert diagnosis["claims"] == [
        {"claim_index": 0, "claim_origin": "EVENT_FACT_GAP", "requires_case_fact": True,
         "requires_legal_rule": False, "coverage_status": "unresolved",
         "coverage_reason": "trusted_case_fact_unavailable", "action_dependency": True,
         "fact_source_status": "EVENT_ASSERTED"},
        {"claim_index": 1, "claim_origin": "WRITER", "requires_case_fact": True,
         "requires_legal_rule": False, "coverage_status": "unresolved",
         "coverage_reason": "trusted_case_fact_unavailable", "action_dependency": False,
         "fact_source_status": "UNVERIFIED"},
    ]
    assert diagnosis["event_fact_gap_candidates"] == [
        {"candidate_index": 0, "claim_index": 0, "candidate_origin": "EVENT_FACT_GAP",
         "candidate_type": "UNKNOWN", "requires_case_fact": True,
         "requires_legal_rule": False},
    ]
    assert diagnosis["human_fact_dependency"] == {
        "request_id": request_id, "claim_index": 0,
        "claim_origin": "EVENT_FACT_GAP",
        "coverage_reason": "trusted_case_fact_unavailable",
    }
    assert diagnosis["writer_introduction_status"] == "WRITER_INTRODUCTION_NOT_OBSERVABLE"
    persisted = run.jsonl_path.read_text(encoding="utf-8")
    for private_value in (event, draft, prompt, evidence, secret, "PRIVATE_AUTHORIZATION_TEXT",
                          "PRIVATE_QUESTION_TEXT", *(claim["claim"] for claim in claims)):
        assert private_value not in persisted
    assert saved["trace"] == {"trace_available": True,
                              "diagnostic_fields_available": True,
                              "trace_safety_passed": True}


def _fact_input_result():
    draft = "关于该事项的具体事实仍在核查中，我们将根据核查结果及时说明。"
    claim = "目前不存在违法行为"
    request_id = "frozen-request-id"
    return {
        "session_id": "human-fact-session", "plan_id": "plan-1",
        "event": "fictional event", "state_status": "WAITING_HUMAN",
        "results": {"writer": {"statement": draft}}, "execution_trace": [],
        "failed_agents": [], "legal_claim_extraction": {"legal_claims": [
            {"claim": claim, "requires_legal_rule": True, "requires_case_fact": True},
        ], "claim_extraction_status": "ok"},
        "legal_claim_coverage": {"claim_coverage": [{
            "claim_index": 0, "case_fact_status": "unresolved",
        }]},
        "legal_action_loop": {"phase": "WAITING_HUMAN", "actions": [], "round_count": 1},
        "human_fact": {
            "request": {"request_id": request_id, "claim_index": 0, "claim": claim,
                        "status": "pending", "question": "fixture question"},
            "draft": draft, "draft_hash": hashlib.sha256(draft.encode("utf-8")).hexdigest(),
            "remaining_plan": [{"agent": "writer_v2"}, {"agent": "decision"}],
            "response": None, "phase": "PENDING",
            "observation": {"case_fact_status": "unresolved"},
            "revision_attempted": False, "decision_attempted": False,
        },
    }


def test_human_fact_frozen_response_uses_fact_response_api(tmp_path, monkeypatch):
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"AGENT_MODE": "mock", "OFFLINE_EVAL": "1",
                                 "AUTH_ENABLED": "false", "RUNTIME_MODE": "sync",
                                 "TASK_QUEUE_BACKEND": "inprocess", "CHECKPOINT_STORAGE": "json",
                                 "LLM_PROVIDER": "openai_compatible", "LLM_API_KEY": "offline",
                                 "LLM_BASE_URL": "mock://blocked", "LLM_MODEL": "offline"}):
        import backend.main as main_module

        monkeypatch.setattr(main_module, "run_dynamic_agent", lambda event, **kwargs: _fact_input_result())
        fixture = {
            "case_id": "privacy-03", "event": "fixture only",
            "expected_fact_gap": True,
            "human_response": {"response_type": "FACT_PROVIDED",
                               "fact_text": "内部复核目前确认仅测试账号复现，范围仍在核查。"},
        }
        monkeypatch.setattr(runner, "load_frozen_cases", lambda: ([fixture], runner.EXPECTED_FROZEN_SHA256))
        summary, path, attempts = runner.run_validation(mode="fake", output_dir=tmp_path)

    row = read_case_records(path)[0]
    assert summary["total_cases"] == 1
    assert row["human_fact"]["requested"] is True
    assert row["human_fact"]["response_type"] == "FACT_PROVIDED"
    assert row["human_fact"]["response_http_status"] == 200
    assert row["human_fact"]["final_wait_type"] == "FINAL_REVIEW"
    assert attempts == []
    persisted = path.read_text(encoding="utf-8")
    assert fixture["human_response"]["fact_text"] not in persisted
    assert fixture["event"] not in persisted


def test_case_three_error_keeps_prior_results_and_default_stops(tmp_path, monkeypatch):
    from scripts import run_real_llm_semantic_validation as module

    def execute_case(_client, case):
        if case["case_id"] == "outage-01":
            raise RuntimeError("provider failure with body that must not persist")
        return {
            "case_id": case["case_id"], "runtime_final_state": "COMPLETED",
            "ground_truth": {"expected_fact_gap": case.get("expected_fact_gap")},
        }

    monkeypatch.setattr(module, "_case_executor", execute_case)
    summary, path, attempts = module.run_validation(mode="fake", output_dir=tmp_path,
                                                    continue_on_error=False)
    rows = read_case_records(path)
    assert [row["case_id"] for row in rows] == ["privacy-03", "food-03", "outage-01"]
    assert [row["status"] for row in rows] == ["SUCCESS", "SUCCESS", "ERROR"]
    assert summary["error_cases"] == 1
    assert rebuild_summary(path)["total_cases"] == 3
    assert "provider failure with body" not in path.read_text(encoding="utf-8")
    assert attempts == []


def test_continue_on_error_policy_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_case_executor", lambda client, case: (
        (_ for _ in ()).throw(RuntimeError("fixture error")) if case["case_id"] == "outage-01"
        else {"runtime_final_state": "COMPLETED"}
    ))
    summary, path, _ = runner.run_validation(mode="fake", output_dir=tmp_path,
                                             continue_on_error=True)
    rows = read_case_records(path)
    assert len(rows) == 5
    assert rows[2]["status"] == "ERROR"
    assert rows[3]["case_id"] == "complaint-02"
    assert summary["error_cases"] == 1


def test_real_mode_requires_explicit_confirmation_and_is_not_called(tmp_path):
    with pytest.raises(RuntimeError, match="explicit confirm_real_provider"):
        runner.run_validation(mode="real", output_dir=tmp_path)


def test_block_diagnostics_are_fsynced_to_run_sidecar(tmp_path, monkeypatch):
    diagnostic = {
        "block_stage": "socket_connect", "logical_host": "api.deepseek.com",
        "logical_scheme": "https", "transport_host": "127.0.0.1",
        "transport_port": 7891, "proxy_detected": True,
        "reason_code": "TRANSPORT_NOT_ALLOWED",
    }

    def simulate_guard(stack, mode, host, attempts, diagnostic_sink=None):
        attempts.append(diagnostic)
        if diagnostic_sink:
            diagnostic_sink(diagnostic)

    fsync_calls = []
    original_fsync = runner.os.fsync

    def observe_fsync(fd):
        fsync_calls.append(fd)
        return original_fsync(fd)

    monkeypatch.setattr(runner, "_network_guard", simulate_guard)
    monkeypatch.setattr(runner, "_case_executor", lambda *_: {
        "runtime_final_state": "COMPLETED", "ground_truth": {},
    })
    monkeypatch.setattr(runner.os, "fsync", observe_fsync)
    summary, jsonl_path, attempts = runner.run_validation(mode="fake", output_dir=tmp_path)

    sidecar = jsonl_path.with_name(jsonl_path.stem + "_network_diagnostics.jsonl")
    rows = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert rows == [diagnostic]
    assert attempts == [diagnostic]
    assert summary["error_cases"] == 1
    assert len(fsync_calls) >= 4
    assert json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])["status"] == "ERROR"
