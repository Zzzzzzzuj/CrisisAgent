"""Run the frozen fictional cases through the offline Dynamic Runtime API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "evaluation" / "dynamic_real_case_v1.json"
REPORT_PATH = ROOT / "evaluation" / "reports" / "dynamic_real_case_validation_v1.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.frozen_hash import canonical_text_sha256


def _set_safe_environment(temp_root: Path) -> None:
    values = {
        "AGENT_MODE": "mock",
        "OFFLINE_EVAL": "1",
        "AUTH_ENABLED": "false",
        "RUNTIME_MODE": "sync",
        "TASK_QUEUE_BACKEND": "inprocess",
        "CHECKPOINT_STORAGE": "json",
        "DATABASE_URL": f"sqlite:///{(temp_root / 'unused.sqlite').as_posix()}",
        "VECTOR_BACKEND": "json",
        "EMBEDDING_MODEL": "hash",
        "RAG_ENABLED": "true",
        "LLM_PROVIDER": "openai_compatible",
        "LLM_API_KEY": "offline-validation-placeholder",
        "LLM_BASE_URL": "mock://blocked",
        "LLM_MODEL": "offline-validation-only",
        "HARNESS_SPEC_STORE_PATH": str(temp_root / "harness_specs.json"),
        "CASE_MEMORY_STORE_PATH": str(temp_root / "case_memories.json"),
        "AUDIT_LOG_STORE_PATH": str(temp_root / "audit_logs.json"),
        "SOURCE_REGISTRY_RUNTIME_PATH": str(temp_root / "source_registry.json"),
        "INGESTION_RUN_STORE_PATH": str(temp_root / "ingestion_runs.json"),
        "CRISIS_EVENT_STORE_PATH": str(temp_root / "crisis_events.json"),
        "EVENT_AGENT_RUN_STORE_PATH": str(temp_root / "event_agent_runs.json"),
        "EVAL_RUN_STORE_PATH": str(temp_root / "eval_runs.json"),
        "ALERT_STORE_PATH": str(temp_root / "alerts.json"),
        "COLLECTED_ITEM_STORE_PATH": str(temp_root / "collected_items.json"),
        "WATCHLIST_STORE_PATH": str(temp_root / "watchlists.json"),
        "HARNESS_COMPARISON_STORE_PATH": str(temp_root / "harness_comparisons.json"),
        "HARNESS_PROPOSAL_STORE_PATH": str(temp_root / "harness_proposals.json"),
    }
    os.environ.update(values)


def _load_cases() -> tuple[dict[str, Any], str]:
    raw = CASE_PATH.read_bytes()
    return json.loads(raw.decode("utf-8")), canonical_text_sha256(raw)


def _extract_json(response) -> dict[str, Any]:
    try:
        value = response.json()
    except Exception:
        value = {"response_text": response.text[:2000]}
    return value if isinstance(value, dict) else {"response_value": value}


def _trace_project_positions() -> list[str]:
    frames = traceback.extract_stack(limit=14)
    return [f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
            for frame in frames if "CrisisAgent" in frame.filename][-8:]


def _case_summary(case: dict[str, Any], initial: dict[str, Any], final: dict[str, Any],
                  latency_ms: float, response_record: dict | None) -> dict[str, Any]:
    state = final if isinstance(final, dict) else {}
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    results = state.get("results") if isinstance(state.get("results"), dict) else initial.get("results", {})
    legal = results.get("legal") if isinstance(results.get("legal"), dict) else {}
    legal_meta = legal.get("_metadata") if isinstance(legal.get("_metadata"), dict) else {}
    rag = legal_meta.get("rag") if isinstance(legal_meta.get("rag"), dict) else {}
    extraction = metadata.get("legal_claim_extraction") or initial.get("legal_claim_extraction") or legal_meta.get("claim_extraction") or {}
    coverage = metadata.get("legal_claim_coverage") or initial.get("legal_claim_coverage") or legal_meta.get("claim_coverage") or {}
    fact_gap = metadata.get("event_fact_gap_detection") or extraction.get("event_fact_gap_detection") or {}
    loop = metadata.get("legal_action_loop") or initial.get("legal_action_loop") or legal_meta.get("legal_action_loop") or {}
    fact = metadata.get("human_fact") or initial.get("human_fact") or {}
    request = fact.get("request") if isinstance(fact, dict) else initial.get("human_fact_request")
    trace = state.get("trace") if isinstance(state.get("trace"), list) else initial.get("execution_trace", [])
    claims = extraction.get("legal_claims", []) if isinstance(extraction, dict) else []
    actions = loop.get("actions", []) if isinstance(loop, dict) else []
    human_actions = [item for item in trace if isinstance(item, dict) and item.get("agent") == "human_fact"]
    all_actions = [item for item in actions if isinstance(item, dict)] + human_actions
    redteam_trace = next((item for item in trace if isinstance(item, dict) and item.get("agent") == "redteam"), {})
    triage_results = ((redteam_trace.get("skills") or {}).get("results") or [])
    triage_result = next((item for item in triage_results if item.get("skill_id") == "event_risk_triage"), {})
    triage_output = triage_result.get("output") if isinstance(triage_result, dict) else {}

    duplicates = Counter()
    for action in all_actions:
        label = action.get("executed_action") or action.get("action") or action.get("selected_action")
        if label and label not in {"STOP_RESOLVED", "STOP_UNRESOLVED", "STOP", "CONTINUE"}:
            duplicates[(action.get("claim_index"), label)] += 1
    duplicate_count = sum(count - 1 for count in duplicates.values() if count > 1)

    transitions = []
    for index, action in enumerate(actions):
        if action.get("selected_action") != "RETRIEVE_LEGAL_EVIDENCE":
            continue
        next_row = next((row for row in actions[index + 1:] if row.get("selected_action")), None)
        transitions.append({
            "round": action.get("round_index"),
            "gap": loop.get("current_gap"),
            "action": action.get("selected_action"),
            "observation": {
                "type": action.get("observation_type"),
                "status": action.get("status"),
                "legal_rule_status": action.get("after_legal_rule_status"),
                "evidence_refs": action.get("targeted_evidence_refs", []),
            },
            "state_change": {
                "before_legal_rule_status": action.get("before_legal_rule_status"),
                "after_legal_rule_status": action.get("after_legal_rule_status"),
            },
            "next_action": (next_row or {}).get("selected_action") or action.get("next_recommended_action"),
            "previous_observation_changed_next_action": bool(
                next_row and next_row.get("selected_action") != action.get("selected_action")
            ),
        })
    for item in human_actions:
        transitions.append({
            "round": item.get("round"), "gap": item.get("evidence_gap"),
            "action": item.get("action"), "observation": item.get("observation"),
            "state_change": None,
            "next_action": "WRITER_V2_OR_FINAL_REVIEW" if item.get("action") == "HUMAN_FACT_RESPONSE" else "FACT_RESPONSE",
            "previous_observation_changed_next_action": item.get("action") == "HUMAN_FACT_RESPONSE",
        })

    context_pack_ref_agents = sorted({
        str(item.get("context_pack", {}).get("target_agent"))
        for item in trace if isinstance(item, dict) and isinstance(item.get("context_pack"), dict)
        and item.get("context_pack", {}).get("target_agent")
    })
    packs = metadata.get("context_pack_snapshots") if isinstance(metadata.get("context_pack_snapshots"), dict) else {}
    if not packs:
        # The API's completed-run checkpoint currently keeps ContextPack refs in
        # Trace but may omit the full state snapshots; recover observed packs
        # from the actual Context Retrieval Skill output for measurement only.
        for item in trace:
            if not isinstance(item, dict):
                continue
            skill_bundle = item.get("skills") or {}
            for skill_result in skill_bundle.get("results", []) if isinstance(skill_bundle, dict) else []:
                output = skill_result.get("output") if isinstance(skill_result, dict) else None
                pack = output.get("context_pack") if isinstance(output, dict) else None
                if isinstance(pack, dict) and isinstance(pack.get("target_agent"), str):
                    packs.setdefault(pack["target_agent"], pack)
    packs_by_agent = {}
    for agent, pack in packs.items():
        if isinstance(pack, dict):
            rendered = str(pack.get("rendered_context", ""))
            packs_by_agent[agent] = {
                "context_pack_chars": len(rendered),
                "estimated_chars": pack.get("estimated_chars"),
                "compression_level": pack.get("compression_level"),
                "degraded": pack.get("degraded", False),
                "dropped_fields": pack.get("dropped_fields", []),
            }

    order = ("sentiment", "writer", "redteam", "legal", "writer_v2", "decision")
    prior = {}
    for agent in order:
        if agent not in packs_by_agent:
            continue
        prior_results = {key: results[key] for key in order[:order.index(agent)] if key in results}
        full_state_proxy = {"event": case["event"], "prior_results": prior_results}
        packs_by_agent[agent]["prior_state_proxy_chars"] = len(json.dumps(full_state_proxy, ensure_ascii=False, default=str))
        packs_by_agent[agent]["pack_to_proxy_ratio"] = round(
            packs_by_agent[agent]["context_pack_chars"] / max(1, packs_by_agent[agent]["prior_state_proxy_chars"]), 4
        )

    final_statement = ""
    for key in ("writer_v2", "writer"):
        value = results.get(key)
        if isinstance(value, dict) and value.get("statement"):
            final_statement = str(value["statement"])
            break
    coverage_rows = coverage.get("claim_coverage", []) if isinstance(coverage, dict) else []
    sentiment_risk = (results.get("sentiment") or {}).get("risk_level")
    planner_risk = (initial.get("planner_input") or {}).get("risk_level")
    harness_spec = initial.get("harness_spec") if isinstance(initial.get("harness_spec"), dict) else {}
    spec_loop_policy = ((harness_spec.get("retrieval_policy") or {}).get("legal_action_loop") or {})
    remaining = loop.get("remaining_budget", {}) if isinstance(loop, dict) else {}
    unresolved = {row.get("claim_index") for row in coverage_rows if isinstance(row, dict)
                  and row.get("case_fact_status") == "unresolved"}
    unsupported_count = sum(
        1 for index in unresolved if isinstance(index, int) and 0 <= index < len(claims)
        and str(claims[index].get("claim", "")).strip()
        and str(claims[index]["claim"]).strip() in final_statement
    )
    fact_detected = bool(fact_gap.get("candidate_count", 0))
    human_request_count = 1 if isinstance(request, dict) else 0
    expected_gap = bool(case.get("expected_fact_gap"))
    failure_category = None
    possible_root = None
    failure_categories = []
    observed_issues = []
    if expected_gap and not fact_detected:
        failure_category = "MOCK_SEMANTIC_LIMITATION"
        possible_root = "Mock extraction recognizes a narrow phrase-and-risk heuristic; the natural-language gap did not meet it."
        failure_categories.append(failure_category)
        observed_issues.append("expected_material_fact_gap_not_detected")
    elif expected_gap and fact_detected and not human_request_count:
        failure_category = "ACTION_SELECTION"
        possible_root = "A fact gap was surfaced, but it did not reach the Human Fact request path."
        failure_categories.append(failure_category)
        observed_issues.append("fact_gap_not_promoted_to_human_request")
    elif not expected_gap and human_request_count:
        failure_category = "GAP_DETECTION"
        possible_root = "A human fact request was emitted for a case whose frozen review expectation did not require one."
        failure_categories.append(failure_category)
        observed_issues.append("unexpected_human_fact_request")

    cross_domain_food_template = case.get("category") != "food_safety" and any(
        marker in final_statement for marker in ("食品安全", "食品", "涉事批次", "相關原料", "相关原料")
    )
    if cross_domain_food_template:
        failure_categories.append("WRITER_REVISION")
        observed_issues.append("mock_final_statement_uses_food_specific_content_for_non_food_case")
        if failure_category is None:
            failure_category = "WRITER_REVISION"
            possible_root = "Deterministic Writer V2 mock emits a fixed food-safety-oriented template across unrelated crisis categories."

    source_conflict_expected = "冲突" in (case.get("event", "") + str(case.get("expected_gap_note", "")))
    source_conflict_detected = bool(triage_output.get("source_conflict")) if isinstance(triage_output, dict) else False
    if source_conflict_expected and not source_conflict_detected:
        failure_categories.append("GAP_DETECTION")
        observed_issues.append("source_conflict_not_flagged_by_runtime_triage")
        if failure_category is None:
            failure_category = "GAP_DETECTION"
            possible_root = "Runtime triage receives no multi-source items for these direct-input cases; its conflict signal remains false."

    return {
        "case_id": case["case_id"], "category": case["category"], "event": case["event"],
        "expected_fact_gap": expected_gap, "expected_gap_note": case.get("expected_gap_note"),
        "expected_source_conflict_from_frozen_text": source_conflict_expected,
        "triage_source_conflict_detected": source_conflict_detected,
        "risk_level": sentiment_risk or planner_risk,
        "planner_risk_level": planner_risk,
        "sentiment_risk_level": sentiment_risk,
        "inferred_runtime_category": (initial.get("planner_input") or {}).get("category"),
        "claims_detected": claims,
        "fact_gap_detected": fact_detected, "fact_gap_detail": fact_gap,
        "gap_type": [row.get("case_fact_reason", "") for row in coverage_rows if isinstance(row, dict)
                     and row.get("case_fact_status") == "unresolved"],
        "actions_taken": all_actions,
        "observations": [item.get("observation") for item in human_actions]
                       + [item.get("observation_type") for item in actions],
        "action_observation_next_action": transitions,
        "round_count": loop.get("rounds", 0) if isinstance(loop, dict) else 0,
        "tool_call_count": loop.get("tool_calls_used", 0) if isinstance(loop, dict) else 0,
        "harness_budget_observed": {
            "configured_max_rounds": spec_loop_policy.get("max_rounds"),
            "configured_max_tool_calls": spec_loop_policy.get("max_tool_calls"),
            "configured_context_budget_chars": spec_loop_policy.get("context_budget"),
            "configured_max_same_action_per_gap": spec_loop_policy.get("max_same_action_per_gap"),
            "runtime_context_budget_chars": loop.get("context_budget") if isinstance(loop, dict) else None,
            "runtime_remaining_budget": remaining,
            "budget_exhaustion_exercised": (loop.get("stop_reason") in {
                "tool_budget_exhausted", "context_budget_exhausted", "max_rounds_reached"
            }) if isinstance(loop, dict) else False,
            "budget_pressure_tested": bool(actions and any(
                row.get("selected_action") == "RETRIEVE_LEGAL_EVIDENCE" for row in actions
            )),
        },
        "duplicate_action_count": duplicate_count,
        "human_request_count": human_request_count,
        "human_request_reasonable": (human_request_count > 0 and expected_gap) if human_request_count else None,
        "human_request_reason": request.get("missing_fact") if isinstance(request, dict) else None,
        "human_response_ground_truth": case.get("human_response"),
        "human_response_used": response_record,
        "retrieval_triggered": bool(rag.get("retrieval_executed")) or any(
            row.get("selected_action") == "RETRIEVE_LEGAL_EVIDENCE" for row in actions
        ),
        "retrieval_result": {
            "status": rag.get("retrieval_status"), "count": rag.get("count"),
            "fallback_used": rag.get("fallback_used"),
            "targeted": [row for row in actions if row.get("selected_action") == "RETRIEVE_LEGAL_EVIDENCE"],
        },
        "context_chars_per_round": [row.get("context_chars") for row in actions if "context_chars" in row],
        "context_pack_by_agent": packs_by_agent,
        "context_pack_ref_agents": context_pack_ref_agents,
        "context_pack_size_unavailable_agents": sorted(set(context_pack_ref_agents) - set(packs_by_agent)),
        "context_pack_snapshot_persisted_in_checkpoint": isinstance(metadata.get("context_pack_snapshots"), dict)
                                                         and bool(metadata.get("context_pack_snapshots")),
        "context_pack_full_output_present_in_trace": bool(packs_by_agent),
        "estimated_tokens": None,
        "estimated_tokens_note": "No production token estimate is emitted by deterministic mock agent paths; reported as null.",
        "latency_ms": round(latency_ms, 2),
        "stop_reason": loop.get("stop_reason") if isinstance(loop, dict) else None,
        "human_fact_phase": fact.get("phase") if isinstance(fact, dict) else None,
        "final_review_required": metadata.get("human_wait_type") == "FINAL_REVIEW"
                                  or bool((metadata.get("policy") or {}).get("required")),
        "unsupported_claim_count": unsupported_count,
        "unsupported_claim_count_method": "Exact-phrase lower bound: unresolved case-fact claims appearing verbatim in final statement.",
        "final_statement": final_statement,
        "cross_domain_food_template_mismatch": cross_domain_food_template,
        "runtime_status": initial.get("status") or initial.get("state_status") or state.get("status"),
        "final_state_status": state.get("status"),
        "failure_category": failure_category,
        "failure_categories": list(dict.fromkeys(failure_categories)),
        "observed_issues": list(dict.fromkeys(observed_issues)),
        "possible_root_cause": possible_root,
        "initial_http_status": initial.get("_http_status"),
    }


async def _execute_cases(cases: list[dict[str, Any]], temp_root: Path, config_summary: dict[str, Any], dataset_hash: str) -> dict[str, Any]:
    import httpx
    from backend.core.checkpoint import JSONCheckpointRepository
    import backend.main as main_module
    import backend.core.human_fact_resume as resume_module
    import backend.llm.client as llm_client_module
    import backend.llm_client as legacy_llm_module
    from backend.llm.offline_guard import OfflineNetworkBlockedError, assert_external_model_call_allowed

    repo = JSONCheckpointRepository(temp_root / "checkpoints.json")
    main_module.save_checkpoint = repo.save_checkpoint
    main_module.load_checkpoint = repo.load_checkpoint
    resume_module.save_checkpoint = repo.save_checkpoint
    resume_module.load_checkpoint = repo.load_checkpoint

    outbound_attempts: list[dict[str, Any]] = []
    def guard_spy(*, provider: str, operation: str) -> None:
        outbound_attempts.append({"kind": "offline_model_guard", "provider": provider,
                                  "operation": operation, "callsite": _trace_project_positions()})
        assert_external_model_call_allowed(provider=provider, operation=operation)

    llm_client_module.assert_external_model_call_allowed = guard_spy
    legacy_llm_module.assert_external_model_call_allowed = guard_spy
    original_post = httpx.Client.post
    def block_provider_http(client, url, *args, **kwargs):
        outbound_attempts.append({"kind": "sync_http_post", "host": getattr(url, "host", None),
                                  "callsite": _trace_project_positions()})
        raise OfflineNetworkBlockedError("Offline validation blocked an outbound HTTP POST before network I/O.")
    httpx.Client.post = block_provider_http

    from fastapi.testclient import TestClient
    # TestClient only uses the in-process ASGI app; the patched synchronous POST
    # boundary prevents a provider client from reaching the network.
    client = TestClient(main_module.app)
    case_results = []
    stopped_for_network_attempt = False
    try:
        for case in cases:
            started = time.perf_counter()
            before_attempts = len(outbound_attempts)
            response_record = None
            initial_response = client.post("/api/dynamic/run", json={"event": case["event"]})
            initial = _extract_json(initial_response)
            initial["_http_status"] = initial_response.status_code
            final = initial
            if initial_response.status_code == 200 and initial.get("session_id"):
                request = initial.get("human_fact_request")
                if isinstance(request, dict):
                    truth = case.get("human_response")
                    if not isinstance(truth, dict):
                        response_record = {"error": "No pre-frozen ground truth exists; no response synthesized."}
                    else:
                        response_record = {
                            "request_id": request.get("request_id"),
                            "response_type": truth.get("response_type"),
                            "fact_text": truth.get("fact_text", ""),
                            "source": "frozen_case_fixture",
                        }
                        fact_response = client.post(
                            f"/api/dynamic/{initial['session_id']}/fact-response",
                            json={key: value for key, value in response_record.items()
                                  if key in {"request_id", "response_type", "fact_text"}},
                        )
                        final = _extract_json(fact_response)
                        final["_http_status"] = fact_response.status_code
                session_response = client.get(f"/api/dynamic/{initial['session_id']}")
                if session_response.status_code == 200:
                    final = _extract_json(session_response)
                    final["status"] = final.get("status")
                elif final is initial:
                    final = {"session_read_error": session_response.status_code,
                             "status": initial.get("status"), "metadata": {}, "results": {}, "trace": []}
            latency_ms = (time.perf_counter() - started) * 1000
            summary = _case_summary(case, initial, final, latency_ms, response_record)
            summary["initial_response"] = initial
            summary["final_session_snapshot"] = final
            case_results.append(summary)
            if len(outbound_attempts) > before_attempts:
                stopped_for_network_attempt = True
                case_results[-1]["failure_category"] = "OTHER"
                case_results[-1]["possible_root_cause"] = "An outbound model/provider request was attempted and blocked; remaining cases were not run."
                break
    finally:
        httpx.Client.post = original_post
        client.close()

    return {
        "config_summary": config_summary,
        "dataset_sha256": dataset_hash,
        "dataset_path": "evaluation/dynamic_real_case_v1.json",
        "case_count_frozen": len(cases),
        "case_count_executed": len(case_results),
        "stopped_for_external_attempt": stopped_for_network_attempt,
        "blocked_external_attempts": outbound_attempts,
        "case_results": case_results,
        "tool_failure_fixtures": [] if stopped_for_network_attempt else _run_tool_failure_fixtures(),
    }


def _run_tool_failure_fixtures() -> list[dict[str, Any]]:
    from backend.agents.legal_action_policy import recommend_legal_actions
    from backend.agents.legal_claim_coverage import build_claim_coverage
    from backend.agents.legal_claim_relation import build_legal_claim_relations
    from backend.agents.legal_targeted_search import run_legal_action_loop

    claim = {"claim": "个人信息泄露可能违反相关法律法规", "requires_legal_rule": True, "requires_case_fact": False}
    extraction = {"legal_claims": [claim], "claim_extraction_status": "ok"}
    chunks = [{"chunk_id": "fixture-food-rule", "source": "food_safety.md",
               "text": "食品原料不得使用超过保质期的原料。"}]
    relation = build_legal_claim_relations([claim], chunks, mode="mock")
    coverage = build_claim_coverage([claim], relation)
    rag_info = {"retrieval_status": "executed_with_hits", "retrieval_executed": True,
                "fallback_used": False, "query": "个人信息安全法律规则", "count": 1}
    seed_recommendation = recommend_legal_actions(extraction, coverage, relation, rag_info)
    policy = {"max_rounds": 3, "max_tool_calls": 2, "context_budget": 6000,
              "max_same_action_per_gap": 2}
    fixtures = {
        "NO_HIT": lambda query, top_k: {"chunks": [], "sources": []},
        "TIMEOUT": lambda query, top_k: (_ for _ in ()).throw(TimeoutError("fixture timeout")),
        "TOOL_ERROR": lambda query, top_k: (_ for _ in ()).throw(RuntimeError("fixture tool error")),
        "INVALID_OUTPUT": lambda query, top_k: "not-a-tool-result",
    }
    output = []
    for name, retrieve_call in fixtures.items():
        started = time.perf_counter()
        result = run_legal_action_loop(
            extraction, coverage, relation, rag_info, retrieve_call=retrieve_call,
            relation_call=build_legal_claim_relations, mode="mock", event="fixture-only",
            risk_level="high", policy=policy,
        )
        output.append({"fixture": name, "fixture_only": True,
                       "seed_action_recommendation": seed_recommendation,
                       "status": result.get("status"), "stop_reason": result.get("stop_reason"),
                       "rounds": result.get("rounds"), "tool_calls_used": result.get("tool_calls_used"),
                       "actions": result.get("actions"),
                       "latency_ms": round((time.perf_counter() - started) * 1000, 2)})
    return output


def _aggregate(report: dict[str, Any]) -> dict[str, Any]:
    cases = report["case_results"]
    count = len(cases)
    category_counts = Counter(category for case in cases for category in case.get("failure_categories", []))
    def rate(predicate) -> float | None:
        return round(sum(bool(predicate(case)) for case in cases) / count, 4) if count else None
    completed = sum(case.get("runtime_status") == "completed" or case.get("final_state_status") == "COMPLETED" for case in cases)
    final_review = sum(case.get("final_review_required") is True for case in cases)
    failed = sum(case.get("runtime_status") == "failed" or case.get("final_state_status") == "FAILED" for case in cases)
    retrieved = [case for case in cases if case.get("retrieval_triggered")]
    return {
        "total_cases": report["case_count_frozen"], "executed_cases": count,
        "completed_cases": completed, "final_review_cases": final_review, "failed_cases": failed,
        "fact_gap_expected_cases": sum(case.get("expected_fact_gap") is True for case in cases),
        "fact_gap_detected_cases": sum(case.get("fact_gap_detected") is True for case in cases),
        "fact_gap_detection_rate": (
            round(sum(case.get("expected_fact_gap") is True and case.get("fact_gap_detected") is True
                      for case in cases) / sum(case.get("expected_fact_gap") is True for case in cases), 4)
            if any(case.get("expected_fact_gap") is True for case in cases) else None
        ),
        "reasonable_human_request_rate": (
            round(sum(case.get("human_request_reasonable") is True for case in cases)
                  / sum(case.get("human_request_count", 0) > 0 for case in cases), 4)
            if any(case.get("human_request_count", 0) > 0 for case in cases) else None
        ),
        "human_request_cases": sum(case.get("human_request_count", 0) > 0 for case in cases),
        "duplicate_action_cases": sum(case.get("duplicate_action_count", 0) > 0 for case in cases),
        "unsupported_claim_cases": sum(case.get("unsupported_claim_count", 0) > 0 for case in cases),
        "unsupported_claim_count_total": sum(case.get("unsupported_claim_count", 0) for case in cases),
        "retrieval_trigger_rate": round(len(retrieved) / count, 4) if count else None,
        "retrieval_hit_rate": (round(sum((case.get("retrieval_result") or {}).get("count", 0) > 0 for case in retrieved) / len(retrieved), 4)
                               if retrieved else None),
        "average_round_count": round(sum(case.get("round_count", 0) for case in cases) / count, 3) if count else None,
        "average_tool_call_count": round(sum(case.get("tool_call_count", 0) for case in cases) / count, 3) if count else None,
        "average_context_chars": (
            round(sum(pack.get("context_pack_chars", 0)
                      for case in cases for pack in case.get("context_pack_by_agent", {}).values())
                  / sum(len(case.get("context_pack_by_agent", {})) for case in cases), 2)
            if any(case.get("context_pack_by_agent") for case in cases) else None
        ),
        "average_legal_loop_context_chars": (
            round(sum(sum(case.get("context_chars_per_round", [])) for case in cases)
                  / sum(len(case.get("context_chars_per_round", [])) for case in cases), 2)
            if any(case.get("context_chars_per_round") for case in cases) else None
        ),
        "average_context_pack_to_prior_state_proxy_ratio": (
            round(sum(pack.get("pack_to_proxy_ratio", 0)
                      for case in cases for pack in case.get("context_pack_by_agent", {}).values())
                  / sum(len(case.get("context_pack_by_agent", {})) for case in cases), 4)
            if any(case.get("context_pack_by_agent") for case in cases) else None
        ),
        "budget_exhaustion_count": sum(case.get("stop_reason") in {"tool_budget_exhausted", "context_budget_exhausted", "max_rounds_reached"} for case in cases),
        "tool_failure_recovery_count": sum(any(item.get("status") in {"failed", "fallback"}
                                                for item in case.get("actions_taken", [])) for case in cases),
        "mock_semantic_limitation_cases": sum(case.get("failure_category") == "MOCK_SEMANTIC_LIMITATION" for case in cases),
        "cross_domain_template_mismatch_cases": sum(case.get("cross_domain_food_template_mismatch") is True for case in cases),
        "expected_source_conflict_cases": sum(case.get("expected_source_conflict_from_frozen_text") is True for case in cases),
        "source_conflict_detected_cases": sum(case.get("triage_source_conflict_detected") is True for case in cases),
        "failure_category_counts": dict(sorted(category_counts.items())),
        "human_fact_ground_truth_matches": sum(
            bool(case.get("human_response_used"))
            and case.get("human_response_used", {}).get("response_type") == (case.get("human_response_ground_truth") or {}).get("response_type")
            for case in cases
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", help="Assert offline mock configuration without running cases.")
    args = parser.parse_args()
    cases_doc, dataset_hash = _load_cases()
    cases = cases_doc.get("cases", [])
    with tempfile.TemporaryDirectory(prefix="crisisagent-real-case-") as temp_name:
        temp_root = Path(temp_name)
        _set_safe_environment(temp_root)
        from backend.llm.offline_guard import assert_offline_eval_startup
        summary = assert_offline_eval_startup()
        if (summary.get("agent_mode") != "mock" or summary.get("offline_eval") is not True
                or summary.get("external_llm_allowed") is not False):
            raise SystemExit("Offline startup assertion failed; no cases executed.")
        safe_summary = {
            "agent_mode": summary["agent_mode"], "offline_eval": summary["offline_eval"],
            "external_llm_allowed": summary["external_llm_allowed"],
            "provider": summary.get("model_provider"),
            "network_policy": summary.get("network_policy"),
            "vector_backend": os.environ["VECTOR_BACKEND"],
            "embedding_model": os.environ["EMBEDDING_MODEL"],
            "runtime_mode": os.environ["RUNTIME_MODE"],
            "checkpoint_store": "isolated temporary JSON",
            "other_runtime_stores": "isolated temporary paths",
        }
        print(json.dumps({"offline_config": safe_summary, "dataset_sha256": dataset_hash,
                          "frozen_cases": len(cases), "preflight_only": args.preflight}, ensure_ascii=False))
        if args.preflight:
            return 0
        report = asyncio.run(_execute_cases(cases, temp_root, safe_summary, dataset_hash))
        report["aggregate_metrics"] = _aggregate(report)
        report["evaluation_limitations"] = [
            "All agents use deterministic mock behavior; findings do not establish real-model quality.",
            "The Dynamic Runtime's category inference is narrower than the frozen business categories.",
            "Human Fact resumption continues Writer V2/Decision or final review; it does not re-enter the Legal loop.",
            "Context reduction compares role ContextPack size with a reconstructed prior-state proxy, not measured provider tokens.",
            "Targeted retrieval is exercised only when real claims and policy make it eligible; tool-failure fixtures are not product-case outcomes.",
        ]
        report["report_version"] = "v1"
        report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report_path": str(REPORT_PATH), "aggregate_metrics": report["aggregate_metrics"],
                          "stopped_for_external_attempt": report["stopped_for_external_attempt"],
                          "executed_cases": report["case_count_executed"]}, ensure_ascii=False))
        return 2 if report["stopped_for_external_attempt"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
