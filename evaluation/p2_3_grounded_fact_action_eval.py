"""One-pass controlled Real Provider replay for frozen P2.3 grounding cases."""

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

from backend.agents import context_pack, legal_agent, writer_agent
from backend.agents.context_pack import build_context_pack
from backend.env import load_project_env
from backend.llm.client import get_last_llm_trace, reset_last_llm_trace
from backend.llm.config import get_llm_config
from backend.llm.offline_guard import assert_external_model_call_allowed
from backend.llm.parser import parse_json_response, validate_required_fields

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "p2_3_grounding_replay_holdout.json"
REPORT_DIR = ROOT / "evaluation" / "reports"
FROZEN_SHA256 = "2485f1b5fcae1ad7b9d0266453ea387bb63be673e921e29467a0dab6fe6c076a"
WRITER_FIELDS = ("statement", "strategy", "tone", "notes")
LEGAL_FIELDS = ("legal_risks", "safe_points", "revision_advice", "public_opinion_suggestions", "integrated_revision_tasks")


def validate_provider_config() -> dict[str, str]:
    if os.environ.get("AGENT_MODE", "").strip().lower() != "llm":
        raise RuntimeError("Real evaluation requires process AGENT_MODE=llm; no request was made.")
    if os.environ.get("OFFLINE_EVAL", "0").strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("Real evaluation is blocked while OFFLINE_EVAL is enabled; no request was made.")
    load_project_env()
    config = get_llm_config()
    parsed = urlparse(config.base_url)
    if (config.mock_enabled or config.provider != "openai_compatible"
            or not config.model.casefold().startswith("deepseek")
            or parsed.scheme != "https" or parsed.hostname != "api.deepseek.com"):
        raise RuntimeError("P2.3 permits only an explicitly configured openai_compatible DeepSeek HTTPS endpoint.")
    assert_external_model_call_allowed(provider=config.provider, operation="P2.3 real provider preflight")
    return {"provider": config.provider, "model": config.model, "host": parsed.hostname}


def _build_case_prompt(case: dict) -> tuple[str, dict, str]:
    event = case["event"]
    memories = case.get("memories", []) if case["condition"] == "memory_on" else []
    human = case.get("human_facts", [])
    human_status = None
    if human:
        item = human[0]
        human_status = {
            "response_type": item["response_type"], "source": item["source"],
            "verification_status": item["verification_status"],
            "case_fact_status": "unresolved" if item["response_type"] == "FACT_UNAVAILABLE" else "resolved",
            "fact_currently_unavailable": item["response_type"] == "FACT_UNAVAILABLE",
            "human_verification_attempted": True,
        }
    pack = build_context_pack(event=event, case_memories=memories, target_agent="writer",
                              human_fact_status=human_status, token_budget_hint=3000)
    pack_text = pack.get("rendered_context") or json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    if case["case_id"] in {"HC-03", "HC-06"}:
        # Exercise the existing Legal prompt with its production-safe human-status envelope.
        legal_pack = build_context_pack(event=event, case_memories=memories, target_agent="legal",
                                        human_fact_status=human_status, token_budget_hint=3000)
        draft = "据人工提供信息，相关访问已暂停。" if case["case_id"] == "HC-03" else "影响范围尚未确认。"
        payload = {"event": event["event_summary"], "draft": draft,
                   "sentiment_analysis": case["sentiment_analysis"],
                   "redteam_review": {"findings": [], "suggestions": []},
                   "context_pack_text": legal_pack.get("rendered_context") or json.dumps(legal_pack, ensure_ascii=False, separators=(",", ":"))}
        return legal_agent._build_legal_prompt(payload, ""), legal_pack, "legal"
    payload = {"event": event["event_summary"], "sentiment_analysis": case["sentiment_analysis"],
               "context_pack": pack, "context_pack_text": pack_text}
    context = writer_agent._build_context(payload, pack_text)
    return writer_agent._build_writer_prompt(payload, pack_text, context), pack, "writer"


def _request(case: dict) -> dict:
    prompt, pack, role = _build_case_prompt(case)
    config = get_llm_config()
    assert_external_model_call_allowed(provider=config.provider, operation="P2.3 frozen case request")
    call = legal_agent.call_llm if role == "legal" else writer_agent.call_llm
    required = LEGAL_FIELDS if role == "legal" else WRITER_FIELDS
    reset_last_llm_trace()
    started = datetime.now(timezone.utc).isoformat()
    timer = perf_counter()
    result = None
    failure = None
    attempts: list[str] = []
    original_post = httpx.Client.post

    def guarded_post(client, url, *args, **kwargs):
        host = urlparse(str(url)).hostname or ""
        if host != "api.deepseek.com":
            raise RuntimeError("P2.3 blocked a non-DeepSeek logical destination.")
        attempts.append(host)
        return original_post(client, url, *args, **kwargs)

    httpx.Client.post = guarded_post
    try:
        raw = call(prompt)
        result = parse_json_response(raw)
        validate_required_fields(result, required)
    except Exception as exc:
        failure = exc.__class__.__name__
    finally:
        httpx.Client.post = original_post
    latency = round((perf_counter() - timer) * 1000)
    trace = get_last_llm_trace() or {}
    return {
        "case_id": case["case_id"], "condition": case["condition"], "role": role,
        "status": "SUCCESS" if result is not None else "FAILURE", "failure_category": failure,
        "started_at_utc": started, "latency_ms": latency, "provider_latency_ms": trace.get("latency_ms"),
        "provider": trace.get("provider"), "model": trace.get("model"),
        "fallback_used": bool(trace.get("fallback_used", False)),
        "provider_failure_type": trace.get("failure_type"),
        "provider_attempt_count": int(trace.get("retry_count", 0)) + 1 if trace else None,
        "logical_destinations": sorted(set(attempts)), "observed_http_attempt_count": len(attempts),
        "parse_schema_status": "PASS" if result is not None else "FAIL",
        "prompt_characters": len(prompt),
        "context_characters": len(json.dumps(pack, ensure_ascii=False, default=str, separators=(",", ":"))),
        "retrieved_memory_count": len(pack.get("selected_case_ids", [])),
        "memory_ids": list(pack.get("selected_case_ids", [])),
        "source_case_ids": sorted({str(item.get("source_case_id")) for item in pack.get("related_case_memories", []) if item.get("source_case_id")}),
        "current_fact_status": pack.get("fact_status"),
        "historical_markers": [item.get("historical_experience") for item in pack.get("related_case_memories", [])],
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "provider_usage_raw_available": False, "output": result,
    }


def run(dataset_path: Path = DATASET, *, output_path: Path | None = None) -> dict:
    raw = dataset_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FROZEN_SHA256:
        raise ValueError("P2.3 frozen dataset SHA-256 mismatch; no request was made.")
    provider = validate_provider_config()
    data = json.loads(raw.decode("utf-8"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    summary_path = output_path or REPORT_DIR / f"p2_3_grounding_{run_id}_summary.json"
    jsonl_path = summary_path.with_name(summary_path.stem.replace("_summary", "") + ".jsonl")
    metadata_path = summary_path.with_name(summary_path.stem.replace("_summary", "") + "_metadata.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"run_id": run_id, "status": "RUNNING", "dataset_sha256": digest,
                "dataset_frozen_before_provider_request": True, "provider_config": provider,
                "logical_destination_allowlist": ["api.deepseek.com"], "input_tokens": None,
                "output_tokens": None, "cost_evaluation": "NOT_AVAILABLE", "jsonl_path": str(jsonl_path)}
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    jsonl_path.write_text("", encoding="utf-8")
    rows = []
    with jsonl_path.open("a", encoding="utf-8", newline="\n") as stream:
        for case in data["cases"]:
            row = _request(case)
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    report = {"version": data["version"], "run_id": run_id, "dataset_sha256": digest,
              "dataset_frozen_before_provider_request": True, "provider_config": provider,
              "experiment_type": "EXPLORATORY_REAL_PROVIDER_REPLAY", "request_count": len(rows),
              "real_provider_request_count": sum(r["observed_http_attempt_count"] for r in rows),
              "rows": rows, "jsonl_path": str(jsonl_path), "metadata_path": str(metadata_path),
              "input_token_evaluation": "NOT_AVAILABLE", "cost_evaluation": "NOT_AVAILABLE",
              "manual_case_adjudication_required": True,
              "limitations": ["single sample per case", "not causal A/B", "no semantic validator", "provider usage unavailable"]}
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata.update({"status": "COMPLETE", "completed_case_count": len(rows),
                     "real_provider_request_count": report["real_provider_request_count"],
                     "summary_path": str(summary_path)})
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["summary_path"] = str(summary_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-real-provider", action="store_true")
    args = parser.parse_args()
    if not args.confirm_real_provider:
        parser.error("Real run requires --confirm-real-provider; no request was made.")
    result = run()
    print(json.dumps({key: result[key] for key in ("run_id", "dataset_sha256", "request_count", "real_provider_request_count", "summary_path")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
