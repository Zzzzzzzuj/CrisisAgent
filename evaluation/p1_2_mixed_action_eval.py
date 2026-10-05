"""Frozen P1.2 controlled Legal action evaluation; real mode is explicit only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from backend.agents.legal_action_policy import (
    classify_legal_query_dependency, compute_eligible_actions,
    recommend_legal_actions, validate_action_proposal,
)
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_claim_relation import build_legal_claim_relations
from backend.agents.legal_targeted_search import run_legal_action_loop
from backend.env import load_project_env
from backend.llm.config import get_llm_config
from backend.llm.offline_guard import assert_external_model_call_allowed
from backend.rag import document_loader
from backend.rag.retriever import retrieve
from scripts.run_real_llm_semantic_validation import _network_guard

DATASET = ROOT / "evaluation" / "p1_2_mixed_action_frozen.json"
DATASET_SHA256 = "d6533fc9aa36c250f9b0ff7199213a5a6f142f67ca3291fb6c1af86355a9975f"
REPORT_DIR = ROOT / "evaluation" / "reports"
EXPECTED_ACTIONS = ["REQUEST_HUMAN_FACT", "RETRIEVE_LEGAL_EVIDENCE"]
SAFE_ACTION_KEYS = (
    "round_index", "selected_action", "claim_index", "eligible_actions", "eligible_action_count",
    "proposal_called", "proposal_status", "proposal_action", "proposal_reason_code",
    "proposal_target_claim_index", "validator_called", "validator_allowed", "validator_reason_code",
    "executed_action", "status", "observation_type", "before_legal_rule_status",
    "after_legal_rule_status", "previous_observation_type", "previous_observation_changed_state",
    "tool_calls_used", "remaining_budget", "stop_reason", "proposal_fallback_used",
)


def _frozen_data() -> tuple[dict, str]:
    raw = DATASET.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != DATASET_SHA256:
        raise ValueError("P1.2 frozen dataset SHA mismatch; no Provider request was made.")
    return json.loads(raw.decode("utf-8")), digest


def _inputs(case: dict) -> tuple[dict, dict, dict, dict]:
    claim = {key: case[key] for key in ("claim", "requires_case_fact", "requires_legal_rule")}
    extraction = {"legal_claims": [claim], "claim_extraction_status": "ok"}
    relation = {"legal_claim_relations": [{"claim_index": 0, "evidence_ref": "frozen-prior-broad-retrieval",
                                             "relation": case["initial_relation"]}], "relation_status": "ok"}
    coverage = build_claim_coverage([claim], relation)
    rag = {"query": "frozen broad retrieval", "retrieval_status": case["initial_retrieval_status"],
           "retrieval_executed": True, "fallback_used": False}
    return extraction, coverage, relation, rag


def qualify(case: dict) -> dict:
    extraction, coverage, relation, rag = _inputs(case)
    dependency = classify_legal_query_dependency(extraction["legal_claims"][0])
    recommendations = recommend_legal_actions(extraction, coverage, relation, rag)
    eligible = compute_eligible_actions(
        extraction, coverage, recommendations, requested_fact_gaps=[], attempted_actions={},
        remaining_rounds=3, remaining_tool_calls=2, max_same_action_per_gap=2,
        claim_relation=relation, rag_info=rag,
    )
    actions = [row["action"] for row in eligible]
    qualified = (coverage["claim_coverage"][0]["case_fact_status"] == "unresolved"
                 and coverage["claim_coverage"][0]["legal_rule_status"] == "no_candidate"
                 and dependency["dependency_type"] == case["expected_dependency"] == "INDEPENDENT"
                 and actions == case["expected_initial_eligible_actions"] == EXPECTED_ACTIONS)
    return {"case_id": case["case_id"], "qualified": qualified,
            "dependency": dependency["dependency_type"], "initial_case_fact_gap": "unresolved",
            "initial_legal_rule_gap": "no_candidate", "eligible_actions": eligible}


def negative_controls(case: dict) -> dict:
    extraction, coverage, _, _ = _inputs(case)
    valid = [{"action": "REQUEST_HUMAN_FACT", "target_claim_index": 0, "reason_code": "CASE_FACT_GAP"}]
    retrieve_proposal = {"action": "RETRIEVE_LEGAL_EVIDENCE", "target_claim_index": 0,
                         "reason_code": "LEGAL_RULE_GAP"}
    dependent = {**extraction, "legal_claims": [{**extraction["legal_claims"][0],
        "claim": "公司尚未确认产品具体类别；该类别适用哪些法定报告规定"}]}
    forged = [retrieve_proposal]
    dependent_verdict = validate_action_proposal(retrieve_proposal, forged, dependent, coverage,
        remaining_rounds=3, remaining_tool_calls=2, max_same_action_per_gap=2)
    outside_verdict = validate_action_proposal(retrieve_proposal, valid, extraction, coverage,
        remaining_rounds=3, remaining_tool_calls=2, max_same_action_per_gap=2)
    budget_verdict = validate_action_proposal(retrieve_proposal, forged, extraction, coverage,
        remaining_rounds=3, remaining_tool_calls=0, max_same_action_per_gap=2)
    return {"fact_dependent_retrieval_denied": not dependent_verdict["allowed"],
            "outside_eligibility_denied": not outside_verdict["allowed"],
            "budget_exhausted_denied": not budget_verdict["allowed"],
            "reason_codes": [dependent_verdict["reason_code"], outside_verdict["reason_code"],
                             budget_verdict["reason_code"]]}


def preflight() -> dict:
    data, digest = _frozen_data()
    qualifications = [qualify(case) for case in data["controlled_cases"]]
    controls = negative_controls(data["controlled_cases"][0])
    if not all(row["qualified"] for row in qualifications) or not all(
        controls[key] for key in ("fact_dependent_retrieval_denied", "outside_eligibility_denied",
                                  "budget_exhausted_denied")
    ):
        raise RuntimeError("P1.2 offline qualification or negative control failed; no Provider request was made.")
    return {"dataset_sha256": digest, "controlled_qualifications": qualifications,
            "negative_controls": controls,
            "natural_case_ids": [row["case_id"] for row in data["natural_cases"]]}


def _provider_config() -> dict:
    if os.environ.get("AGENT_MODE", "").strip().casefold() != "llm":
        raise RuntimeError("Real mode requires explicit process AGENT_MODE=llm.")
    if os.environ.get("OFFLINE_EVAL", "0").strip().casefold() in {"1", "true", "yes", "on"}:
        raise RuntimeError("Real mode refuses OFFLINE_EVAL=true.")
    load_project_env()
    get_llm_config.cache_clear()
    config = get_llm_config()
    parsed = urlparse(config.base_url)
    if (config.mock_enabled or config.provider != "openai_compatible"
            or config.model != "deepseek-v4-flash" or parsed.scheme != "https"
            or parsed.hostname != "api.deepseek.com"):
        raise RuntimeError("Real mode requires openai_compatible deepseek-v4-flash at api.deepseek.com with credential available.")
    assert_external_model_call_allowed(provider=config.provider, operation="P1.2 preflight")
    return {"provider": config.provider, "model": config.model, "logical_host": parsed.hostname}


def _safe_action(action: dict) -> dict:
    return {key: action[key] for key in SAFE_ACTION_KEYS if key in action}


def _human_observation(case: dict, request_id: str) -> dict:
    provided = case["human_response"]["response_type"] == "FACT_PROVIDED"
    return {"observation_type": "fact_provided" if provided else "fact_unavailable",
            "request_id": request_id, "claim_index": 0,
            "response_type": case["human_response"]["response_type"],
            "verification_status": "human_asserted" if provided else "unresolved",
            "source": "human_provided" if provided else "human_response",
            "whether_new_information": provided, "consumed": True}


def _execute_controlled(case: dict, request_attempts: list[dict], stage: dict) -> dict:
    from backend.agents import legal_agent

    extraction, coverage, relation, rag = _inputs(case)
    retrievals: list[dict] = []
    llm_call_count = 0
    def llm_call(prompt: str) -> str:
        nonlocal llm_call_count
        llm_call_count += 1
        stage["name"] = ("action_proposal" if "受控动作提议器" in prompt else "legal_relation")
        try:
            return legal_agent.call_llm(prompt)
        finally:
            stage["name"] = "unknown"

    def retrieve_call(query: str, top_k: int) -> dict:
        result = retrieve(query, top_k=top_k)
        retrievals.append({"status": "hit" if result.get("chunks") else "no_hit",
                           "source_count": len(result.get("sources", [])),
                           "sources": [{key: source.get(key) for key in ("chunk_id", "source", "score", "rerank_score")}
                                       for source in result.get("sources", []) if isinstance(source, dict)],
                           "fallback_used": any(source.get("retrieval_fallback") is True
                                                for source in result.get("sources", []) if isinstance(source, dict))})
        return result

    before_count = len(request_attempts)
    started = perf_counter()
    first = run_legal_action_loop(extraction, coverage, relation, rag,
        retrieve_call=retrieve_call, relation_call=build_legal_claim_relations,
        llm_call=llm_call, mode="llm", risk_level="high")
    result = first
    response_type = None
    if first.get("phase") == "WAITING_HUMAN":
        response_type = case["human_response"]["response_type"]
        result = run_legal_action_loop(extraction, first["claim_coverage"], first["claim_evidence_relation"], rag,
            retrieve_call=retrieve_call, relation_call=build_legal_claim_relations,
            llm_call=llm_call, mode="llm", risk_level="high", cursor=first["cursor"],
            human_observation=_human_observation(case, f"frozen-{case['case_id']}"))
    actions = [_safe_action(row) for row in result.get("actions", [])]
    operational = [row for row in actions if row.get("selected_action") in EXPECTED_ACTIONS]
    first_action = operational[0] if operational else {}
    next_action = operational[1] if len(operational) > 1 else {}
    next_eligible = next_action.get("eligible_actions", [])
    initial_row = coverage["claim_coverage"][0]
    final_row = result.get("claim_coverage", {}).get("claim_coverage", [{}])[0]
    if first_action.get("selected_action") == "RETRIEVE_LEGAL_EVIDENCE":
        observed_gap_changed = (first_action.get("before_legal_rule_status") == "no_candidate"
                                and first_action.get("after_legal_rule_status") == "candidate_found")
    else:
        observed_gap_changed = final_row.get("case_fact_input_status") == "human_asserted"
    next_types = [row.get("action") for row in next_eligible]
    transition = (first_action.get("proposal_called") is True
                  and first_action.get("validator_allowed") is True
                  and observed_gap_changed
                  and first_action.get("selected_action") not in next_types
                  and next_action.get("selected_action") in EXPECTED_ACTIONS
                  and next_action.get("selected_action") != first_action.get("selected_action"))
    return {"case_id": case["case_id"], "controlled_fixture": True,
            "claim_extraction_real_provider": False,
            "action_proposal_real_provider": bool(first_action.get("proposal_called") and
                                                  any(row["stage"] == "action_proposal"
                                                      for row in request_attempts[before_count:])),
            "actions": actions, "first_action": first_action.get("selected_action"),
            "next_action": next_action.get("selected_action"), "eligible_after_observation": next_eligible,
            "observation_driven_strategy_change": transition,
            "first_observation_changed_gap": observed_gap_changed,
            "case_fact_status_before": initial_row.get("case_fact_status"),
            "case_fact_status_after": final_row.get("case_fact_status"),
            "case_fact_input_status_after": final_row.get("case_fact_input_status"),
            "verification_status_after": final_row.get("verification_status"),
            "legal_rule_status_before": initial_row.get("legal_rule_status"),
            "legal_rule_status_after": final_row.get("legal_rule_status"),
            "human_response_type": response_type, "retrievals": retrievals,
            "stop_reason": result.get("stop_reason"), "rounds": result.get("rounds"),
            "tool_calls_used": result.get("tool_calls_used"),
            "remaining_budget": result.get("remaining_budget"),
            "provider_request_attempts": len(request_attempts) - before_count,
            "logical_llm_calls": llm_call_count,
            "technical_retry_count": max(0, len(request_attempts) - before_count - llm_call_count),
            "latency_ms": round((perf_counter() - started) * 1000, 2)}


def _remaining_cases(cases: list[dict], output_dir: Path, parent_run_id: str | None) -> list[dict]:
    if parent_run_id is None:
        return cases
    if not parent_run_id.replace("-", "").isalnum():
        raise ValueError("Invalid infrastructure parent run id.")
    prefix = output_dir / f"p1_2_mixed_action_{parent_run_id}"
    summary = json.loads(prefix.with_name(prefix.name + "_summary.json").read_text(encoding="utf-8"))
    metadata = json.loads(prefix.with_name(prefix.name + "_metadata.json").read_text(encoding="utf-8"))
    if (summary.get("status") != "NETWORK_GUARD_BLOCKED"
            or metadata.get("dataset_sha256") != DATASET_SHA256):
        raise ValueError("Only a matching infrastructure-blocked run may be continued.")
    rows = [json.loads(line) for line in prefix.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()]
    finished_ids = [row.get("case_id") for row in rows]
    expected_prefix = [case["case_id"] for case in cases[:len(finished_ids)]]
    if not finished_ids or finished_ids != expected_prefix:
        raise ValueError("Parent results must be a non-empty prefix of frozen cases.")
    return cases[len(finished_ids):]


def run(*, confirm_real_provider: bool = False, output_dir: Path = REPORT_DIR,
        resume_after_infra_run_id: str | None = None) -> tuple[dict, dict]:
    before = preflight()
    if not confirm_real_provider:
        raise RuntimeError("Real Provider request requires --confirm-real-provider.")
    config = _provider_config()
    data, _ = _frozen_data()
    remaining_cases = _remaining_cases(data["controlled_cases"], output_dir, resume_after_infra_run_id)
    if not remaining_cases:
        raise ValueError("No frozen controlled cases remain; no Provider request was made.")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / f"p1_2_mixed_action_{run_id}"
    paths = {kind: prefix.with_name(prefix.name + suffix) for kind, suffix in (
        ("jsonl", ".jsonl"), ("metadata", "_metadata.json"), ("summary", "_summary.json"),
        ("network_diagnostic", "_network_diagnostic.jsonl"))}
    metadata = {"run_id": run_id, "status": "RUNNING", "dataset_sha256": before["dataset_sha256"],
                "dataset_frozen_before_provider_request": True, "provider": config,
                "controlled_case_ids": [case["case_id"] for case in remaining_cases],
                "natural_case_ids": before["natural_case_ids"], "paths": {k: str(v) for k, v in paths.items()},
                "parent_infrastructure_run_id": resume_after_infra_run_id,
                "retrieval_corpus": "repository_local_markdown_kb",
                "production_retriever_used": True, "database_kb_lookup_disabled_in_evaluation": True,
                "qualification": before["controlled_qualifications"],
                "negative_controls": before["negative_controls"]}
    paths["metadata"].write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["jsonl"].write_text("", encoding="utf-8")
    paths["network_diagnostic"].write_text("", encoding="utf-8")
    attempts: list[dict] = []
    provider_attempts: list[dict] = []
    rows: list[dict] = []
    original_post = httpx.Client.post
    current_stage = {"name": "unknown"}

    def guarded_post(client, url, *args, **kwargs):
        host = urlparse(str(url)).hostname
        if host != "api.deepseek.com":
            raise RuntimeError("P1.2 blocked a non-DeepSeek logical destination.")
        provider_attempts.append({"logical_host": host, "stage": current_stage["name"]})
        return original_post(client, url, *args, **kwargs)

    def diagnostic_sink(item):
        with paths["network_diagnostic"].open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    status = "COMPLETE"
    try:
        with ExitStack() as stack:
            _network_guard(stack, "real", "api.deepseek.com", attempts, diagnostic_sink)
            stack.enter_context(patch.object(httpx.Client, "post", guarded_post))
            stack.enter_context(patch.object(document_loader, "_load_database_chunks_if_available", lambda: []))
            stack.enter_context(patch.object(document_loader, "_load_database_documents_if_available", lambda: []))
            for case in remaining_cases:
                try:
                    row = _execute_controlled(case, provider_attempts, current_stage)
                except Exception as exc:
                    row = {"case_id": case["case_id"], "status": "ERROR", "failure_type": exc.__class__.__name__}
                    status = "COMPLETE_WITH_CASE_ERRORS"
                rows.append(row)
                with paths["jsonl"].open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                if attempts:
                    status = "NETWORK_GUARD_BLOCKED"
                    break
    except Exception as exc:
        status = "INFRASTRUCTURE_ERROR"
        metadata["failure_type"] = exc.__class__.__name__
    retries = sum(row.get("technical_retry_count", 0) for row in rows)
    metadata.update(status=status, provider_request_count=len(provider_attempts),
                    technical_retry_count=retries, network_block_count=len(attempts))
    paths["metadata"].write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"run_id": run_id, "status": status, "controlled_case_count": len(rows),
               "strategy_type_selection_proven": any(
                   row.get("action_proposal_real_provider") and row.get("actions", [{}])[0].get("validator_allowed")
                   for row in rows),
               "observation_driven_strategy_change_proven": any(
                   row.get("observation_driven_strategy_change") for row in rows),
               "provider_request_count": len(provider_attempts), "technical_retry_count": retries,
               "network_block_count": len(attempts), "paths": {k: str(v) for k, v in paths.items()}}
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary, metadata


def run_natural(*, confirm_real_provider: bool = False, output_dir: Path = REPORT_DIR) -> dict:
    before = preflight()
    if not confirm_real_provider:
        raise RuntimeError("Natural Real Provider request requires --confirm-real-provider.")
    config = _provider_config()
    from scripts.run_real_llm_semantic_validation import run_validation

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / f"p1_2_natural_{run_id}"
    jsonl_path = prefix.with_suffix(".jsonl")
    metadata_path = prefix.with_name(prefix.name + "_metadata.json")
    summary_path = prefix.with_name(prefix.name + "_summary.json")
    metadata = {"run_id": run_id, "status": "RUNNING", "dataset_sha256": before["dataset_sha256"],
                "dataset_frozen_before_provider_request": True, "provider": config,
                "natural_case_ids": before["natural_case_ids"],
                "retrieval_corpus": "repository_local_markdown_kb",
                "production_retriever_used": True, "database_kb_lookup_disabled_in_evaluation": True,
                "jsonl_path": str(jsonl_path), "summary_path": str(summary_path)}
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    jsonl_path.write_text("", encoding="utf-8")
    rows = []
    total_attempts = 0
    original_post = httpx.Client.post

    for case_id in before["natural_case_ids"]:
        attempt_hosts = []

        def guarded_post(client, url, *args, **kwargs):
            host = urlparse(str(url)).hostname
            if host != "api.deepseek.com":
                raise RuntimeError("P1.2 natural run blocked a non-DeepSeek logical destination.")
            attempt_hosts.append(host)
            return original_post(client, url, *args, **kwargs)

        try:
            with patch.object(document_loader, "_load_database_chunks_if_available", lambda: []), \
                    patch.object(document_loader, "_load_database_documents_if_available", lambda: []), \
                    patch.object(httpx.Client, "post", guarded_post):
                _, case_jsonl_path, network_blocks = run_validation(
                    mode="real", confirm_real_provider=True, case_id=case_id, output_dir=output_dir,
                )
            case_records = [json.loads(line) for line in case_jsonl_path.read_text(encoding="utf-8").splitlines()]
            record = case_records[0] if case_records else {}
            extraction = record.get("claim_extraction") or {}
            diagnosis = record.get("diagnosis") or {}
            claims = diagnosis.get("claims") if isinstance(diagnosis.get("claims"), list) else []
            decisions = (record.get("loop") or {}).get("decision_telemetry") or []
            mixed_indices = {row.get("claim_index") for row in claims if isinstance(row, dict)
                             and row.get("requires_case_fact") is True and row.get("requires_legal_rule") is True}
            qualified_rows = [row for row in decisions if isinstance(row, dict) and any(
                {item.get("action") for item in row.get("eligible_actions", [])
                 if isinstance(item, dict) and item.get("target_claim_index") == index}
                >= set(EXPECTED_ACTIONS) for index in mixed_indices)]
            row = {"case_id": case_id, "status": record.get("status", "NO_CASE_RECORD"),
                   "source_run_id": record.get("run_id"), "source_jsonl_path": str(case_jsonl_path),
                   "source_metadata_path": str(case_jsonl_path.with_name(case_jsonl_path.stem + "_metadata.json")),
                   "source_summary_path": str(case_jsonl_path.with_name(case_jsonl_path.stem + "_summary.json")),
                   "claim_extraction_provider_success": extraction.get("provider_status") == "SUCCESS",
                   "claim_count": extraction.get("accepted_item_count"),
                   "mixed_need_claim_found": bool(mixed_indices),
                   "dependency": "INDEPENDENT_INFERRED_FROM_ELIGIBILITY" if qualified_rows else "NOT_RECOVERABLE",
                   "qualified": bool(qualified_rows),
                   "proposal_called": any(item.get("proposal_called") is True for item in qualified_rows),
                   "decisions": qualified_rows, "loop_stop_reason": (record.get("loop") or {}).get("stop_reason"),
                   "provider_request_attempts": len(attempt_hosts), "network_block_count": len(network_blocks),
                   "gap_state_transition": "NOT_RECOVERABLE_FROM_EXISTING_SAFE_JSONL"}
        except Exception as exc:
            row = {"case_id": case_id, "status": "ERROR", "failure_type": exc.__class__.__name__,
                   "provider_request_attempts": len(attempt_hosts)}
        total_attempts += len(attempt_hosts)
        rows.append(row)
        with jsonl_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if row.get("status") == "ERROR" and row.get("provider_request_attempts") == 0:
            break

    summary = {"run_id": run_id, "status": "COMPLETE" if len(rows) == len(before["natural_case_ids"])
               and all(row.get("status") != "ERROR" for row in rows) else "PARTIAL",
               "case_count": len(rows), "provider_request_count": total_attempts,
               "qualified_case_count": sum(row.get("qualified") is True for row in rows),
               "jsonl_path": str(jsonl_path), "metadata_path": str(metadata_path)}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata.update(status=summary["status"], provider_request_count=total_attempts)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--confirm-real-provider", action="store_true")
    parser.add_argument("--resume-after-infra-run-id")
    parser.add_argument("--natural-only", action="store_true")
    args = parser.parse_args()
    if args.preflight_only:
        print(json.dumps(preflight(), ensure_ascii=False))
        return 0
    if args.natural_only:
        summary = run_natural(confirm_real_provider=args.confirm_real_provider)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["status"] == "COMPLETE" else 1
    summary, _ = run(confirm_real_provider=args.confirm_real_provider,
                     resume_after_infra_run_id=args.resume_after_infra_run_id)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
