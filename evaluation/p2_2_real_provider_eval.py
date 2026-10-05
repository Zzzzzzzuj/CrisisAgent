"""Controlled P2.2 real-provider paired evaluation; never runs during pytest."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.agents import context_pack, legal_agent, writer_agent
from backend.agents.context_pack import build_context_pack
from backend.core.context_pack_runtime import ContextPackRuntimeProvider
from backend.core.state import AgentState
from backend.env import load_project_env
from backend.llm import LLMClient
from backend.llm.client import get_last_llm_trace, reset_last_llm_trace
from backend.llm.config import get_llm_config
from backend.llm.offline_guard import assert_external_model_call_allowed
from backend.llm.parser import parse_json_response, validate_required_fields
from evaluation.frozen_hash import canonical_text_sha256


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "p2_2_real_provider_holdout.json"
REPORT_DIR = ROOT / "evaluation" / "reports"
FROZEN_SHA256 = "6d840c159ec242ac3ab81dfd0a61f361a153fa80fa4ae4e86ff57619b321117a"
WRITER_FIELDS = ("statement", "strategy", "tone", "notes")
LEGAL_FIELDS = ("legal_risks", "safe_points", "revision_advice", "public_opinion_suggestions", "integrated_revision_tasks")


def dataset_sha256(path: Path = DATASET) -> str:
    return canonical_text_sha256(path.read_bytes())


def validate_provider_config() -> dict[str, str]:
    explicit_mode = os.environ.get("AGENT_MODE", "").strip().lower()
    if explicit_mode != "llm":
        raise RuntimeError("Real evaluation requires process AGENT_MODE=llm; no request was made.")
    if os.environ.get("OFFLINE_EVAL", "0").strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("Real evaluation is blocked while OFFLINE_EVAL is enabled; no request was made.")
    load_project_env()
    config = get_llm_config()
    if config.mock_enabled:
        raise RuntimeError("Real evaluation requires provider credentials; credential value was not inspected or logged.")
    parsed = urlparse(config.base_url)
    if (config.provider != "openai_compatible" or not config.model.casefold().startswith("deepseek")
            or parsed.scheme != "https" or parsed.hostname != "api.deepseek.com"):
        raise RuntimeError("Real evaluation permits only openai_compatible DeepSeek via HTTPS api.deepseek.com.")
    # Validate the normal offline guard before creating any evaluation artifacts or requests.
    assert_external_model_call_allowed(provider=config.provider, operation="p2.2 paired evaluation preflight")
    return {"provider": config.provider, "model": config.model, "host": parsed.hostname}


@contextmanager
def _count_and_restrict_http_attempts():
    original = httpx.Client.post
    hosts: list[str] = []

    def guarded_post(client, url, *args, **kwargs):
        host = urlparse(str(url)).hostname or ""
        if host != "api.deepseek.com":
            raise RuntimeError("P2.2 evaluation blocked a non-DeepSeek logical destination.")
        hosts.append(host)
        return original(client, url, *args, **kwargs)

    httpx.Client.post = guarded_post
    try:
        yield hosts
    finally:
        httpx.Client.post = original


def _build_writer_payload(case: dict[str, Any], memories: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    event = case["event"]
    pack = build_context_pack(event=event, case_memories=memories, target_agent="writer",
                              token_budget_hint=3000, compression_mode="auto")
    payload = {"event": event["event_summary"], "sentiment_analysis": case["sentiment_analysis"],
               "context_pack": pack, "context_pack_text": json.dumps(pack, ensure_ascii=False, default=str, separators=(",", ":"))}
    return payload, pack


def _build_legal_payload(case: dict[str, Any], *, safe_reference: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    event = case["event"]
    compression_mode = "off" if safe_reference else "auto"
    pack = build_context_pack(
        event=event, legal_evidence=case.get("legal_evidence", []), target_agent="legal",
        previous_observation=case.get("previous_observation"), human_fact_status=case.get("human_fact_status"),
        token_budget_hint=case["budget_chars"], compression_mode=compression_mode,
    )
    rendered = json.dumps(pack, ensure_ascii=False, default=str, separators=(",", ":"))
    payload = {"event": event["event_summary"], "draft": case["draft"],
               "sentiment_analysis": case["sentiment_analysis"], "redteam_review": case["redteam_review"],
               "context_pack_text": rendered}
    return payload, pack


def _execute(condition_id: str, kind: str, payload: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    config = get_llm_config()
    assert_external_model_call_allowed(provider=config.provider, operation="p2.2 paired evaluation request")
    if kind == "memory":
        memory_ids = pack.get("selected_case_ids", [])
        prompt_context = pack.get("rendered_context") or payload["context_pack_text"]
        context = writer_agent._build_context(payload, prompt_context)
        prompt = writer_agent._build_writer_prompt(payload, prompt_context, context)
        fields = WRITER_FIELDS
        agent_name = "P2.2 Writer downstream"
        call = writer_agent.call_llm
    else:
        memory_ids = pack.get("selected_case_ids", [])
        prompt = legal_agent._build_legal_prompt(payload, "")
        fields = LEGAL_FIELDS
        agent_name = "P2.2 Legal prompt downstream"
        call = legal_agent.call_llm

    reset_last_llm_trace()
    started_at = datetime.now(timezone.utc).isoformat()
    timer = perf_counter()
    status = "SUCCESS"
    failure_category = None
    parsed: dict[str, Any] | None = None
    raw: str | None = None
    with _count_and_restrict_http_attempts() as hosts:
        try:
            raw = call(prompt)
            parsed = parse_json_response(raw)
            validate_required_fields(parsed, fields)
        except Exception as exc:
            status = "FAILURE"
            failure_category = exc.__class__.__name__
    wall_ms = round((perf_counter() - timer) * 1000)
    trace = get_last_llm_trace()
    actual_attempts = int(trace.get("retry_count", 0)) + 1 if trace else None
    return {
        "condition_id": condition_id, "experiment": kind, "status": status,
        "failure_category": failure_category, "started_at_utc": started_at,
        "latency_ms": wall_ms, "provider_latency_ms": trace.get("latency_ms"),
        "provider": trace.get("provider"), "model": trace.get("model"),
        "fallback_used": bool(trace.get("fallback_used", False)),
        "provider_failure_type": trace.get("failure_type"), "provider_attempt_count": actual_attempts,
        "logical_destinations": sorted(set(hosts)), "observed_http_attempt_count": len(hosts),
        "parse_schema_status": "PASS" if parsed is not None else "FAIL",
        "prompt_characters": len(prompt), "context_characters": len(payload.get("context_pack_text", "")),
        "pack_content_characters": len(json.dumps({k: v for k, v in pack.items() if k != "rendered_context"},
                                                   ensure_ascii=False, default=str, separators=(",", ":"))),
        "retrieved_memory_count": len(memory_ids), "memory_ids": list(memory_ids),
        "source_case_ids": sorted({str(item.get("source_case_id")) for item in pack.get("related_case_memories", [])
                                    if item.get("source_case_id")}),
        "historical_marker_present": any(
            item.get("historical_experience") is True for item in pack.get("related_case_memories", [])
        ),
        "current_fact_status": pack.get("fact_status"),
        "historical_fact_statuses": sorted({str(item.get("historical_fact_status"))
                                             for item in pack.get("related_case_memories", [])
                                             if item.get("historical_fact_status")}),
        # The SDK/client does not expose provider usage; its estimated_tokens field is intentionally ignored.
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "provider_usage_raw_available": False,
        "output": parsed,
    }


def run(dataset_path: Path = DATASET, *, output_path: Path | None = None) -> dict[str, Any]:
    raw_dataset = dataset_path.read_bytes()
    digest = canonical_text_sha256(raw_dataset)
    if FROZEN_SHA256 == "TO_BE_FROZEN_AFTER_FILE_CREATION" or digest != FROZEN_SHA256:
        raise ValueError("P2.2 frozen holdout SHA-256 mismatch; no request was made.")
    config = validate_provider_config()
    data = json.loads(raw_dataset.decode("utf-8"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    destination = output_path or REPORT_DIR / f"p2_2_real_provider_{run_id}_summary.json"
    jsonl_path = destination.with_name(destination.stem.replace("_summary", "") + ".jsonl")
    metadata_path = destination.with_name(destination.stem.replace("_summary", "") + "_metadata.json")
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id, "status": "RUNNING", "dataset_sha256": digest,
        "dataset_frozen_before_provider_request": True, "provider_config": config,
        "logical_destination_allowlist": ["api.deepseek.com"],
        "provider_usage_raw_available": False, "input_tokens": None, "output_tokens": None,
        "cost_evaluation": "NOT_AVAILABLE", "request_jsonl": str(jsonl_path),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    jsonl_path.write_text("", encoding="utf-8")

    def persist_condition(row: dict[str, Any]) -> None:
        with jsonl_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    rows = []
    pairs = []

    for case in data["memory_cases"]:
        selected_on = context_pack.retrieve_memories(case["event"], case["memories"], top_k=data["memory_top_k"])
        expected = set(case["expected_relevant_memory_ids"])
        actual = {item["memory_id"] for item in selected_on}
        on_input, on_pack = _build_writer_payload(case, selected_on)
        off_input, off_pack = _build_writer_payload(case, [])
        off = _execute(f"{case['case_id']}:memory-off", "memory", off_input, off_pack)
        persist_condition(off)
        on = _execute(f"{case['case_id']}:memory-on", "memory", on_input, on_pack)
        persist_condition(on)
        boundary = {
            "expected_memory_ids": sorted(expected), "retrieved_memory_ids": sorted(actual),
            "retrieval_matches_frozen_judgment": actual == expected,
            "historical_provenance_preserved": all(
                item.get("historical_experience") is True and item.get("historical_fact_status")
                for item in on_pack.get("related_case_memories", [])
            ),
            "current_fact_status": on_pack.get("fact_status"),
        }
        rows.extend([off, on])
        pairs.append({"case_id": case["case_id"], "case_type": case["case_type"], "retrieval_boundary": boundary,
                      "pair_valid_for_quality_comparison": all(x["status"] == "SUCCESS" and not x["fallback_used"] for x in (off, on)),
                      "memory_off_condition": off["condition_id"], "memory_on_condition": on["condition_id"]})

    context_pairs = []
    for case in data["context_cases"]:
        ref_input, ref_pack = _build_legal_payload(case, safe_reference=True)
        current_input, current_pack = _build_legal_payload(case, safe_reference=False)
        # Both contexts use the same Legal role, current Case, evidence, and status; only compression strategy differs.
        ref = _execute(f"{case['case_id']}:safe-reference", "context", ref_input, ref_pack)
        persist_condition(ref)
        current = _execute(f"{case['case_id']}:current-contextpack", "context", current_input, current_pack)
        persist_condition(current)
        required = {marker: bool(current_pack.get(marker)) for marker in case["required_markers"]}
        row = {"case_id": case["case_id"], "case_type": case["case_type"],
               "safe_reference_condition": ref["condition_id"], "current_contextpack_condition": current["condition_id"],
               "required_context_markers_present": required,
               "pair_valid_for_quality_comparison": all(x["status"] == "SUCCESS" and not x["fallback_used"] for x in (ref, current)),
               "safe_reference_prompt_characters": ref["prompt_characters"],
               "current_prompt_characters": current["prompt_characters"],
               "safe_reference_context_characters": ref["context_characters"],
               "current_context_characters": current["context_characters"],
               "safe_reference_pack_content_characters": ref["pack_content_characters"],
               "current_pack_content_characters": current["pack_content_characters"],
               "safe_reference_input_tokens": ref["input_tokens"], "current_input_tokens": current["input_tokens"],
               "safe_reference_output_tokens": ref["output_tokens"], "current_output_tokens": current["output_tokens"],
               "safe_reference_latency_ms": ref["latency_ms"], "current_latency_ms": current["latency_ms"],
               "safe_reference_output": ref["output"], "current_output": current["output"]}
        context_pairs.append(row)
        rows.extend([ref, current])

    report = {
        "version": data["version"], "run_id": run_id,
        "dataset_sha256": digest, "dataset_frozen_before_provider_request": True,
        "provider_config": config, "experiment_boundary": {
            "memory": "evaluation-only case_memories adapter into the unchanged production ContextPack builder and Writer prompt builder; no production Memory store mutation",
            "context": "direct Legal prompt-builder paired calls; not a full six-step workflow and not a Legal Action Loop evaluation",
            "safe_reference": "same role-allowed fields with compression_mode=off; no AgentState wholesale serialization",
            "provider_usage": "LLM client trace does not expose provider usage; token metrics are null, estimated token field excluded",
            "quality_scoring": "rubrics frozen in dataset; outputs preserved for manual/case-level scoring; no LLM judge",
        },
        "memory_pairs": pairs, "context_pairs": context_pairs, "requests": rows,
        "request_count": len(rows),
        "real_provider_request_count": sum(row["observed_http_attempt_count"] for row in rows),
        "request_jsonl": str(jsonl_path), "metadata_path": str(metadata_path),
        "input_token_evaluation": "NOT_AVAILABLE", "cost_evaluation": "NOT_AVAILABLE",
        "latency_result": "EXPLORATORY", "llm_judge_used": False,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata.update({"status": "COMPLETE", "completed_condition_count": len(rows),
                     "real_provider_request_count": report["real_provider_request_count"],
                     "summary_path": str(destination)})
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(destination)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-real-provider", action="store_true")
    args = parser.parse_args()
    if not args.confirm_real_provider:
        parser.error("Real run requires --confirm-real-provider; no request was made.")
    report = run()
    print(json.dumps({k: report[k] for k in ("run_id", "dataset_sha256", "request_count",
                                             "real_provider_request_count", "report_path")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
