"""Retrieval-qualified paired OFF/ON generation validation for P2.3b."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

import httpx

from backend.agents import context_pack, writer_agent
from backend.agents.context_pack import build_context_pack
from backend.env import load_project_env
from backend.llm.client import get_last_llm_trace, reset_last_llm_trace
from backend.llm.config import get_llm_config
from backend.llm.offline_guard import assert_external_model_call_allowed
from backend.llm.parser import parse_json_response, validate_required_fields

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "p2_3b_retrieval_qualified_holdout.json"
REPORT_DIR = ROOT / "evaluation" / "reports"
FROZEN_SHA256 = "c040100ed5325b2d0bac821ffe51cd68996f0d655b2311683f9a9f1e1e2fd3e6"
REQUIRED_FIELDS = ("statement", "strategy", "tone", "revisions")


def load_frozen_dataset(path: Path = DATASET) -> tuple[dict, str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FROZEN_SHA256:
        raise ValueError("P2.3b frozen dataset SHA-256 mismatch; no provider request was made.")
    return json.loads(raw.decode("utf-8")), digest


def qualify_cases(data: dict) -> list[dict]:
    rows = []
    for case in data["cases"]:
        retrieved = context_pack.retrieve_memories(case["event"], case["memories"], top_k=data["memory_top_k"])
        expected_id = case["expected_memory_id"]
        expected = next((item for item in retrieved if item.get("memory_id") == expected_id), None)
        rows.append({
            "case_id": case["case_id"], "expected_memory_id": expected_id,
            "retrieved_memory_ids": [item.get("memory_id") for item in retrieved],
            "expected_memory_retrieved": expected is not None,
            "retrieval_score": expected.get("score") if expected else None,
            "matched_reasons": expected.get("matched_reasons", []) if expected else [],
            "historical_marker_present": expected is not None and expected.get("historical_experience") is True,
            "source_case_id": expected.get("source_case_id") if expected else None,
            "source_case_id_present": bool(expected and expected.get("source_case_id")),
            "qualification_status": "QUALIFIED" if expected else "NOT_QUALIFIED_FOR_GENERATION_EVIDENCE",
        })
    return rows


def _human_fact_status(case: dict) -> dict | None:
    facts = case.get("human_facts") or []
    if not facts:
        return None
    fact = facts[0]
    provided = fact.get("response_type") == "FACT_PROVIDED"
    return {"response_type": fact.get("response_type"),
            "source": "human_provided" if provided else fact.get("source", "human_response"),
            "verification_status": "human_asserted" if provided else "unresolved",
            "case_fact_status": "resolved" if provided else "unresolved",
            "human_verification_attempted": True,
            "fact_currently_unavailable": not provided}


def build_prompt(case: dict, *, memory_enabled: bool) -> tuple[str, dict]:
    memories = case["memories"] if memory_enabled else []
    pack = build_context_pack(
        event=case["event"], case_memories=memories, target_agent="writer_v2" if case["route"] == "writer_v2" else "writer",
        human_fact_status=_human_fact_status(case), token_budget_hint=3000,
    )
    context_text = pack.get("rendered_context") or json.dumps(pack, ensure_ascii=False, default=str, separators=(",", ":"))
    if case["route"] == "writer_v2":
        human = case["human_facts"][0]
        payload = {
            "event": case["event"]["event_summary"],
            "first_draft": {"statement": "我们关注到异常登录反馈，相关账号和影响范围仍在核查。"},
            "redteam_review": {"findings": [], "suggestions": []},
            "legal_review": {"revision_advice": [], "integrated_revision_tasks": []},
            # Evaluation-only adapter exposes the frozen assertion with its source/status; production state is unchanged.
            "human_fact_revision": {
                "target_claim": human["claim"], "assertion": human["response"],
                "source": "human_response", "verification_status": "human_asserted",
                "constraint": "可归因引用该人工信息，但不得表述为独立核实结论。",
            },
            "context_pack_text": context_text,
        }
        return writer_agent._build_writer_v2_prompt(payload), pack
    payload = {"event": case["event"]["event_summary"], "sentiment_analysis": case["sentiment_analysis"],
               "context_pack": pack, "context_pack_text": context_text}
    context = writer_agent._build_context(payload, context_text)
    return writer_agent._build_writer_prompt(payload, context_text, context), pack


def validate_provider_config() -> dict[str, str]:
    if os.environ.get("AGENT_MODE", "").strip().lower() != "llm":
        raise RuntimeError("Real evaluation requires process AGENT_MODE=llm; no request was made.")
    if os.environ.get("OFFLINE_EVAL", "0").strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("Real evaluation is blocked while OFFLINE_EVAL is enabled; no request was made.")
    load_project_env()
    config = get_llm_config()
    parsed = urlparse(config.base_url)
    if (config.mock_enabled or config.provider != "openai_compatible"
            or config.model != "deepseek-v4-flash" or parsed.scheme != "https"
            or parsed.hostname != "api.deepseek.com"):
        raise RuntimeError("P2.3b permits only openai_compatible deepseek-v4-flash at HTTPS api.deepseek.com.")
    assert_external_model_call_allowed(provider=config.provider, operation="P2.3b paired evaluation preflight")
    return {"provider": config.provider, "model": config.model, "host": parsed.hostname}


def _execute(case: dict, memory_enabled: bool) -> dict:
    prompt, pack = build_prompt(case, memory_enabled=memory_enabled)
    config = get_llm_config()
    assert_external_model_call_allowed(provider=config.provider, operation="P2.3b paired case request")
    reset_last_llm_trace()
    started = datetime.now(timezone.utc).isoformat()
    timer = perf_counter()
    result = None
    failure = None
    destinations: list[str] = []
    original_post = httpx.Client.post

    def guarded_post(client, url, *args, **kwargs):
        host = urlparse(str(url)).hostname or ""
        if host != "api.deepseek.com":
            raise RuntimeError("P2.3b blocked a non-DeepSeek logical destination.")
        destinations.append(host)
        return original_post(client, url, *args, **kwargs)

    httpx.Client.post = guarded_post
    try:
        raw = writer_agent.call_llm(prompt)
        result = parse_json_response(raw)
        validate_required_fields(result, REQUIRED_FIELDS)
    except Exception as exc:
        failure = exc.__class__.__name__
    finally:
        httpx.Client.post = original_post
    elapsed = round((perf_counter() - timer) * 1000)
    trace = get_last_llm_trace() or {}
    return {
        "case_id": case["case_id"], "condition": "MEMORY_ON" if memory_enabled else "MEMORY_OFF",
        "status": "SUCCESS" if result is not None else "FAILURE", "failure_category": failure,
        "started_at_utc": started, "provider": trace.get("provider"), "model": trace.get("model"),
        "latency_ms": elapsed, "provider_latency_ms": trace.get("latency_ms"),
        "fallback_used": bool(trace.get("fallback_used", False)),
        "provider_error": trace.get("failure_type"), "provider_attempt_count": int(trace.get("retry_count", 0)) + 1 if trace else None,
        "logical_destinations": sorted(set(destinations)), "observed_http_attempt_count": len(destinations),
        "parse_status": "PASS" if result is not None else "FAIL",
        "prompt_characters": len(prompt), "context_characters": len(context_text := json.dumps(pack, ensure_ascii=False, default=str, separators=(",", ":"))),
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "provider_usage_raw_available": False, "retrieved_memory_ids": list(pack.get("selected_case_ids", [])),
        "source_case_ids": sorted({str(m.get("source_case_id")) for m in pack.get("related_case_memories", []) if m.get("source_case_id")}),
        "historical_marker_present": any(m.get("historical_experience") is True for m in pack.get("related_case_memories", [])),
        "human_fact_status": pack.get("human_fact_status"), "output": result,
    }


def run(dataset_path: Path = DATASET, *, output_base: Path | None = None) -> dict:
    data, digest = load_frozen_dataset(dataset_path)
    qualifications = qualify_cases(data)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    base = output_base or REPORT_DIR / f"p2_3b_grounding_{run_id}"
    base.parent.mkdir(parents=True, exist_ok=True)
    qualification_path = base.with_name(base.name + "_qualification.json")
    jsonl_path = base.with_suffix(".jsonl")
    summary_path = base.with_name(base.name + "_summary.json")
    metadata_path = base.with_name(base.name + "_metadata.json")
    qualified_ids = {row["case_id"] for row in qualifications if row["qualification_status"] == "QUALIFIED"}
    qualification_path.write_text(json.dumps({"run_id": run_id, "dataset_sha256": digest,
        "frozen_before_retrieval": True, "qualified_case_count": len(qualified_ids),
        "qualifications": qualifications}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if len(qualified_ids) < 2:
        result = {"run_id": run_id, "dataset_sha256": digest, "qualification_path": str(qualification_path),
                  "qualified_case_count": len(qualified_ids), "request_count": 0,
                  "status": "STOPPED_NO_PROVIDER_REQUEST_INSUFFICIENT_QUALIFIED_CASES"}
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    provider = validate_provider_config()
    metadata = {"run_id": run_id, "status": "RUNNING", "dataset_sha256": digest,
                "frozen_before_retrieval": True, "provider_config": provider,
                "logical_destination_allowlist": ["api.deepseek.com"], "qualification_path": str(qualification_path),
                "input_tokens": None, "output_tokens": None, "cost_evaluation": "NOT_AVAILABLE"}
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    jsonl_path.write_text("", encoding="utf-8")
    rows = []
    with jsonl_path.open("a", encoding="utf-8", newline="\n") as stream:
        for case in data["cases"]:
            if case["case_id"] not in qualified_ids:
                continue
            for enabled in (False, True):
                row = _execute(case, enabled)
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
    summary = {"run_id": run_id, "dataset_sha256": digest, "frozen_before_retrieval": True,
               "experiment_type": "EXPLORATORY_PAIRED_REAL_PROVIDER_EVALUATION",
               "provider_config": provider, "qualified_case_count": len(qualified_ids),
               "qualification_path": str(qualification_path), "request_count": len(rows),
               "real_provider_request_count": sum(r["observed_http_attempt_count"] for r in rows),
               "rows": rows, "jsonl_path": str(jsonl_path), "metadata_path": str(metadata_path),
               "input_token_evaluation": "NOT_AVAILABLE", "cost_evaluation": "NOT_AVAILABLE",
               "causal_claim": "NOT_SUPPORTED; exploratory single sample per condition",
               "manual_case_adjudication_required": True}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata.update({"status": "COMPLETE", "completed_condition_count": len(rows),
                     "real_provider_request_count": summary["real_provider_request_count"],
                     "summary_path": str(summary_path), "jsonl_path": str(jsonl_path)})
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-real-provider", action="store_true")
    args = parser.parse_args()
    if not args.confirm_real_provider:
        parser.error("Real replay requires --confirm-real-provider.")
    result = run()
    print(json.dumps({key: result.get(key) for key in
        ("run_id", "dataset_sha256", "qualified_case_count", "request_count", "real_provider_request_count", "status", "summary_path", "qualification_path")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
