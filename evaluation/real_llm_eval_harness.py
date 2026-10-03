"""Crash-safe, content-minimizing persistence for manually authorized LLM evals.

This module does not execute a model or an Agent. Callers provide one already
sanitized structured result per case; unknown fields are deliberately dropped.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping


CASE_FIELDS: dict[str, tuple[str, ...]] = {
    "fact_gap": ("expected", "detected", "claim_count", "claim_indices",
                 "requires_case_fact_count", "requires_legal_rule_count"),
    "human_fact": ("requested", "request_count", "response_type",
                   "response_http_status", "resume_result", "final_wait_type"),
    "legal": ("rag_triggered", "targeted_retrieval_triggered", "retrieval_count",
              "source_conflict_detected"),
    "loop": ("round_count", "actions", "observation_types", "next_actions",
             "stop_reason", "duplicate_action_count", "decision_telemetry"),
    "reliability": ("llm_call_count", "timeout_count", "parse_failure_count",
                    "schema_failure_count", "fallback_count", "fallback_agents",
                    "provider_error_count"),
    "trace": ("trace_available", "diagnostic_fields_available", "trace_safety_passed"),
    "usage": ("prompt_tokens", "completion_tokens", "total_tokens", "usage_available"),
    "diagnosis": ("claims", "event_fact_gap_candidates", "human_fact_dependency",
                  "writer_introduction_status"),
    "claim_extraction": ("claim_extraction_called", "provider_status", "parse_status",
                         "schema_status", "validation_status", "raw_item_count",
                         "accepted_item_count", "dropped_item_count", "fallback_used",
                         "failure_stage", "reason_code"),
}

_EXTRACTION_PROVIDER_STATUSES = {"NOT_CALLED", "SUCCESS", "ERROR", "TIMEOUT", "UNKNOWN"}
_EXTRACTION_PARSE_STATUSES = {"NOT_ATTEMPTED", "SUCCESS", "ERROR"}
_EXTRACTION_SCHEMA_STATUSES = {"NOT_ATTEMPTED", "SUCCESS", "ERROR"}
_EXTRACTION_VALIDATION_STATUSES = {"NOT_ATTEMPTED", "SUCCESS", "ERROR"}
_EXTRACTION_FAILURE_STAGES = {"NONE", "PROVIDER", "PARSE", "SCHEMA", "VALIDATION", "FALLBACK", "UNKNOWN"}
_EXTRACTION_REASON_CODES = {
    "NONE", "EMPTY_INPUT", "EMPTY_MODEL_CLAIMS", "NO_ACCEPTED_CLAIMS",
    "PROVIDER_ERROR", "PROVIDER_TIMEOUT", "JSON_PARSE_ERROR",
    "SCHEMA_VALIDATION_ERROR", "CLAIM_VALIDATION_ERROR", "FALLBACK_ERROR", "UNKNOWN",
}

_CLAIM_ORIGINS = {"EVENT", "WRITER", "MIXED", "EVENT_FACT_GAP", "UNKNOWN"}
_COVERAGE_STATUSES = {"not_required", "unresolved"}
_COVERAGE_REASONS = {"trusted_case_fact_unavailable"}
_FACT_SOURCE_STATUSES = {"EVENT_ASSERTED", "UNVERIFIED", "UNKNOWN"}
_CANDIDATE_TYPES = {"UNKNOWN"}

GROUND_TRUTH_FIELDS = (
    "expected_fact_gap", "expected_final_state", "expected_human_fact_request",
    "expected_response_type", "expected_legal_action", "expected_stop_reason",
)
METADATA_FIELDS = (
    "frozen_file", "frozen_sha256", "selected_case_ids", "AGENT_MODE",
    "OFFLINE_EVAL", "provider", "model", "external_provider_allowed",
    "other_external_network_allowed", "git_branch", "git_commit",
    "working_tree_dirty", "evaluation_started_at", "claim_extraction_telemetry_version",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_ground_truth(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in GROUND_TRUTH_FIELDS:
        item = value.get(key)
        if isinstance(item, (bool, int, float)) or _is_label(item, 80):
            result[key] = item
    return result


def _safe_group(name: str, value: Any) -> dict[str, Any]:
    allowed = CASE_FIELDS[name]
    source = value if isinstance(value, Mapping) else {}
    if name == "diagnosis":
        return _safe_diagnosis(source)
    if name == "claim_extraction":
        return _safe_claim_extraction_telemetry(source)
    result: dict[str, Any] = {}
    for key in allowed:
        item = source.get(key)
        if key.endswith("_count"):
            result[key] = item if isinstance(item, (int, float)) else None
        elif key == "decision_telemetry":
            result[key] = _safe_decision_telemetry(source.get(key))
        elif key in {"claim_indices", "actions", "observation_types", "next_actions", "fallback_agents"}:
            if key == "claim_indices" and isinstance(item, list):
                result[key] = [entry for entry in item if isinstance(entry, int)][:100]
            elif key in {"actions", "observation_types", "next_actions", "fallback_agents"} and isinstance(item, list):
                result[key] = [entry[:80] for entry in item if _is_label(entry, 80)][:100]
            else:
                result[key] = None
        elif key in {"response_type", "resume_result", "final_wait_type", "stop_reason"}:
            result[key] = item if item is None or _is_label(item, 80) else None
        elif key == "response_http_status":
            result[key] = item if isinstance(item, int) else None
        elif isinstance(item, bool):
            result[key] = item
        else:
            result[key] = None

    if name == "usage":
        result.setdefault("prompt_tokens", None)
        result.setdefault("completion_tokens", None)
        result.setdefault("total_tokens", None)
        result.setdefault("usage_available", False)
        if result["usage_available"] is not True:
            result["prompt_tokens"] = result["completion_tokens"] = result["total_tokens"] = None
    return result


def _safe_claim_extraction_telemetry(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_extraction_called": (source.get("claim_extraction_called")
                                    if type(source.get("claim_extraction_called")) is bool else None),
        "provider_status": _safe_enum(source.get("provider_status"), _EXTRACTION_PROVIDER_STATUSES),
        "parse_status": _safe_enum(source.get("parse_status"), _EXTRACTION_PARSE_STATUSES),
        "schema_status": _safe_enum(source.get("schema_status"), _EXTRACTION_SCHEMA_STATUSES),
        "validation_status": _safe_enum(source.get("validation_status"), _EXTRACTION_VALIDATION_STATUSES),
        "raw_item_count": _safe_count(source.get("raw_item_count")),
        "accepted_item_count": _safe_count(source.get("accepted_item_count")),
        "dropped_item_count": _safe_count(source.get("dropped_item_count")),
        "fallback_used": source.get("fallback_used") if type(source.get("fallback_used")) is bool else None,
        "failure_stage": _safe_enum(source.get("failure_stage"), _EXTRACTION_FAILURE_STAGES),
        "reason_code": _safe_enum(source.get("reason_code"), _EXTRACTION_REASON_CODES),
    }


def _safe_count(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 100000 else None


def _safe_decision_telemetry(value: Any) -> list[dict[str, Any]]:
    """Allowlist action-decision facts without persisting business text."""
    if not isinstance(value, list):
        return []
    rows = []
    for item in value[:100]:
        if not isinstance(item, Mapping):
            continue
        safe: dict[str, Any] = {}
        for key in ("round", "eligible_action_count", "proposal_target_claim_index",
                    "deterministic_baseline_target_claim_index",
                    "executed_target_claim_index", "remaining_rounds", "remaining_tool_calls"):
            safe[key] = _safe_index(item.get(key)) if "claim_index" in key else (
                item.get(key) if type(item.get(key)) is int and 0 <= item.get(key) <= 100000 else None
            )
        for key in ("previous_observation_type", "deterministic_baseline_action",
                    "proposal_status", "proposal_action", "proposal_reason_code",
                    "validator_reason_code", "fallback_reason_code",
                    "executed_action", "result_observation_type",
                    "result_observation_status"):
            value_item = item.get(key)
            safe[key] = value_item[:80] if _is_label(value_item, 80) else None
        for key in ("proposal_called", "validator_called", "validator_allowed",
                    "fallback_used", "proposal_fallback_used", "previous_observation_changed_state"):
            safe[key] = item.get(key) if type(item.get(key)) is bool else None
        eligible = []
        for option in item.get("eligible_actions", []) if isinstance(item.get("eligible_actions"), list) else []:
            if not isinstance(option, Mapping) or not _is_label(option.get("action"), 80):
                continue
            eligible.append({"action": option["action"],
                             "target_claim_index": _safe_index(option.get("target_claim_index"))})
        safe["eligible_actions"] = eligible[:100]
        targets = item.get("eligible_target_claim_indices")
        safe["eligible_target_claim_indices"] = (
            [_safe_index(target) for target in targets[:100] if _safe_index(target) is not None]
            if isinstance(targets, list) else []
        )
        rows.append(safe)
    return rows


def _safe_index(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value < 100 else None


def _safe_enum(value: Any, allowed: set[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _safe_diagnosis(source: Mapping[str, Any]) -> dict[str, Any]:
    """Persist only bounded decision references, never source or generated text."""
    claims = []
    for item in source.get("claims", []) if isinstance(source.get("claims"), list) else []:
        if not isinstance(item, Mapping) or _safe_index(item.get("claim_index")) is None:
            continue
        claims.append({
            "claim_index": item["claim_index"],
            "claim_origin": _safe_enum(item.get("claim_origin"), _CLAIM_ORIGINS) or "UNKNOWN",
            "requires_case_fact": item.get("requires_case_fact") if type(item.get("requires_case_fact")) is bool else None,
            "requires_legal_rule": item.get("requires_legal_rule") if type(item.get("requires_legal_rule")) is bool else None,
            "coverage_status": _safe_enum(item.get("coverage_status"), _COVERAGE_STATUSES),
            "coverage_reason": _safe_enum(item.get("coverage_reason"), _COVERAGE_REASONS),
            "action_dependency": item.get("action_dependency") if type(item.get("action_dependency")) is bool else None,
            "fact_source_status": _safe_enum(item.get("fact_source_status"), _FACT_SOURCE_STATUSES) or "UNKNOWN",
        })
        if len(claims) == 100:
            break

    candidates = []
    for item in (source.get("event_fact_gap_candidates", [])
                 if isinstance(source.get("event_fact_gap_candidates"), list) else []):
        if not isinstance(item, Mapping):
            continue
        candidate_index = _safe_index(item.get("candidate_index"))
        claim_index = _safe_index(item.get("claim_index"))
        if candidate_index is None or claim_index is None:
            continue
        candidates.append({
            "candidate_index": candidate_index,
            "claim_index": claim_index,
            "candidate_origin": _safe_enum(item.get("candidate_origin"), _CLAIM_ORIGINS) or "UNKNOWN",
            "candidate_type": _safe_enum(item.get("candidate_type"), _CANDIDATE_TYPES) or "UNKNOWN",
            "requires_case_fact": item.get("requires_case_fact") if type(item.get("requires_case_fact")) is bool else None,
            "requires_legal_rule": item.get("requires_legal_rule") if type(item.get("requires_legal_rule")) is bool else None,
        })
        if len(candidates) == 100:
            break

    dependency = source.get("human_fact_dependency")
    safe_dependency = None
    if isinstance(dependency, Mapping) and _safe_index(dependency.get("claim_index")) is not None:
        try:
            request_id = str(uuid.UUID(dependency.get("request_id")))
        except (AttributeError, TypeError, ValueError):
            request_id = None
        safe_dependency = {
            "request_id": request_id,
            "claim_index": dependency["claim_index"],
            "claim_origin": _safe_enum(dependency.get("claim_origin"), _CLAIM_ORIGINS) or "UNKNOWN",
            "coverage_reason": _safe_enum(dependency.get("coverage_reason"), _COVERAGE_REASONS),
        }

    return {
        "claims": claims,
        "event_fact_gap_candidates": candidates,
        "human_fact_dependency": safe_dependency,
        "writer_introduction_status": (
            "WRITER_INTRODUCTION_NOT_OBSERVABLE"
            if source.get("writer_introduction_status") == "WRITER_INTRODUCTION_NOT_OBSERVABLE"
            else "UNKNOWN"
        ),
    }


def _safe_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    safe = {key: metadata.get(key) for key in METADATA_FIELDS}
    selected = safe.get("selected_case_ids")
    safe["selected_case_ids"] = (
        [item[:100] for item in selected if _is_label(item, 100)][:100]
        if isinstance(selected, list) else []
    )
    for key in ("frozen_file", "frozen_sha256", "AGENT_MODE", "OFFLINE_EVAL", "provider",
                "model", "git_branch", "git_commit"):
        value = safe.get(key)
        if value is not None and not isinstance(value, (str, bool)):
            safe[key] = None
        elif isinstance(value, str):
            safe[key] = value[:500]
    for key in ("external_provider_allowed", "other_external_network_allowed", "working_tree_dirty"):
        if not isinstance(safe.get(key), bool):
            safe[key] = None
    if safe.get("claim_extraction_telemetry_version") != "v1":
        safe["claim_extraction_telemetry_version"] = None
    return safe


def _is_label(value: Any, max_length: int = 100) -> bool:
    return isinstance(value, str) and len(value) <= max_length and bool(
        re.fullmatch(r"[A-Za-z0-9_.:-]+", value)
    )


def collect_run_metadata(
    *, frozen_file: str, frozen_sha256: str, selected_case_ids: list[str],
    provider: str, model: str, external_provider_allowed: bool,
    other_external_network_allowed: bool, repo_root: Path,
) -> dict[str, Any]:
    """Capture reproducibility metadata without reading or serializing secrets."""
    def git_value(*args: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", *args], cwd=repo_root, check=True, capture_output=True,
                text=True, timeout=3,
            )
            return completed.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None

    dirty = git_value("status", "--porcelain")
    return {
        "frozen_file": frozen_file, "frozen_sha256": frozen_sha256,
        "selected_case_ids": selected_case_ids,
        "AGENT_MODE": os.getenv("AGENT_MODE"), "OFFLINE_EVAL": os.getenv("OFFLINE_EVAL"),
        "provider": provider, "model": model,
        "external_provider_allowed": external_provider_allowed,
        "other_external_network_allowed": other_external_network_allowed,
        "claim_extraction_telemetry_version": "v1",
        "git_branch": git_value("branch", "--show-current"),
        "git_commit": git_value("rev-parse", "HEAD"),
        "working_tree_dirty": bool(dirty), "evaluation_started_at": utc_now(),
    }


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


class RealLLMEvalRun:
    """A unique run directory set of artifacts with durable per-case appends."""

    def __init__(self, output_dir: Path, metadata: Mapping[str, Any], *, run_id: str | None = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        chosen = run_id or f"{stamp}-{uuid.uuid4().hex[:8]}"
        if not _is_label(chosen, 120):
            raise ValueError("run_id must contain only letters, digits, underscore, dot, colon, or hyphen")
        stem = f"deepseek_semantic_validation_v1_{chosen}"
        self.run_id = chosen
        self.jsonl_path = self.output_dir / f"{stem}.jsonl"
        self.metadata_path = self.output_dir / f"{stem}_metadata.json"
        self.summary_path = self.output_dir / f"{stem}_summary.json"
        run_metadata = {"run_id": chosen, **_safe_metadata(metadata)}
        self.metadata = run_metadata
        if not run_metadata.get("evaluation_started_at"):
            run_metadata["evaluation_started_at"] = utc_now()
        _write_json_exclusive(self.metadata_path, run_metadata)
        # Exclusive creation prevents accidentally appending to an older run.
        with self.jsonl_path.open("x", encoding="utf-8", newline="\n"):
            pass

    def append_case(self, record: Mapping[str, Any]) -> None:
        safe = _safe_case_record(self.run_id, record)
        payload = json.dumps(safe, ensure_ascii=False, sort_keys=True) + "\n"
        with self.jsonl_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def run_cases(
        self,
        cases: Iterable[Mapping[str, Any]],
        execute_case: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        *,
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        for case in cases:
            started_at = utc_now()
            start = perf_counter()
            raw_case_id = case.get("case_id", "unknown")
            case_id = raw_case_id[:100] if _is_label(raw_case_id, 100) else "invalid_case_id"
            try:
                result = execute_case(case)
                elapsed = (perf_counter() - start) * 1000
                self.append_case({
                    **dict(result), "case_id": case_id,
                    "ground_truth": result.get("ground_truth", case.get("ground_truth", {})),
                    "model_provider": result.get("model_provider") or self.metadata.get("provider"),
                    "model_name": result.get("model_name") or self.metadata.get("model"),
                    "started_at": result.get("started_at", started_at),
                    "finished_at": result.get("finished_at", utc_now()),
                    "latency_ms": result.get("latency_ms", round(elapsed, 2)),
                    "status": result.get("status", "SUCCESS"),
                })
            except Exception as exc:
                self.append_case({
                    "case_id": case_id,
                    "ground_truth": case.get("ground_truth", {}),
                    "model_provider": self.metadata.get("provider"),
                    "model_name": self.metadata.get("model"),
                    "started_at": started_at, "finished_at": utc_now(),
                    "latency_ms": round((perf_counter() - start) * 1000, 2),
                    "status": "ERROR",
                    # Never persist exception text: it may contain prompts or credentials.
                    "error": {"type": type(exc).__name__, "stage": "case_execution",
                              "code": "CASE_EXECUTION_ERROR"},
                    "reliability": {},
                })
                if not continue_on_error:
                    break
        summary = rebuild_summary(self.jsonl_path)
        summary["run_id"] = self.run_id
        summary["generated_at"] = utc_now()
        _write_json_exclusive(self.summary_path, summary)
        return summary


def _safe_case_record(run_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
    started = record.get("started_at") if isinstance(record.get("started_at"), str) else utc_now()
    finished = record.get("finished_at") if isinstance(record.get("finished_at"), str) else utc_now()
    status = record.get("status") if record.get("status") in {"SUCCESS", "ERROR"} else "SUCCESS"
    safe: dict[str, Any] = {
        "run_id": run_id,
        "case_id": record.get("case_id") if _is_label(record.get("case_id", "unknown"), 100) else "invalid_case_id",
        "ground_truth": _safe_ground_truth(record.get("ground_truth")),
        "model_provider": record.get("model_provider")[:100] if _is_label(record.get("model_provider"), 100) else None,
        "model_name": record.get("model_name")[:100] if _is_label(record.get("model_name"), 100) else None,
        "started_at": started, "finished_at": finished,
        "latency_ms": record.get("latency_ms") if isinstance(record.get("latency_ms"), (int, float)) else None,
        "runtime_final_state": record.get("runtime_final_state") if _is_label(record.get("runtime_final_state"), 80) else None,
        "status": status,
    }
    for group in CASE_FIELDS:
        safe[group] = _safe_group(group, record.get(group))
    error = record.get("error")
    safe["error"] = ({key: error[key] for key in ("type", "stage", "code", "fallback_used")
                       if key in error and _is_label(error[key], 100)}
                      if status == "ERROR" and isinstance(error, Mapping) else None)
    return safe


def read_case_records(jsonl_path: Path) -> list[dict[str, Any]]:
    records = []
    with Path(jsonl_path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            records.append(record)
    return records


def rebuild_summary(jsonl_path: Path) -> dict[str, Any]:
    records = read_case_records(jsonl_path)
    reliability_names = CASE_FIELDS["reliability"]
    reliability_values = {name: [] for name in reliability_names if name.endswith("_count")}
    fallbacks: CounterLike = {}
    extraction_status_counts: dict[str, CounterLike] = {
        key: {} for key in ("provider_status", "parse_status", "schema_status",
                            "validation_status", "failure_stage", "reason_code")
    }
    extraction_fallback_cases = 0
    extraction_cases = 0
    extraction_item_totals = {key: [] for key in (
        "raw_item_count", "accepted_item_count", "dropped_item_count",
    )}
    for record in records:
        for key in reliability_values:
            value = (record.get("reliability") or {}).get(key)
            if isinstance(value, (int, float)):
                reliability_values[key].append(value)
        for agent in ((record.get("reliability") or {}).get("fallback_agents") or []):
            if isinstance(agent, str):
                fallbacks[agent] = fallbacks.get(agent, 0) + 1
        extraction = record.get("claim_extraction") or {}
        if extraction.get("claim_extraction_called") is True:
            extraction_cases += 1
        if extraction.get("fallback_used") is True:
            extraction_fallback_cases += 1
        for key, counts in extraction_status_counts.items():
            value = extraction.get(key)
            if isinstance(value, str):
                counts[value] = counts.get(value, 0) + 1
        for key, values in extraction_item_totals.items():
            value = extraction.get(key)
            if type(value) is int:
                values.append(value)
    return {
        "total_cases": len(records),
        "success_cases": sum(item.get("status") == "SUCCESS" for item in records),
        "error_cases": sum(item.get("status") == "ERROR" for item in records),
        "final_state_counts": _count_values(item.get("runtime_final_state") for item in records),
        "observation_type_counts": _count_values(
            tag for item in records for tag in ((item.get("loop") or {}).get("observation_types") or [])
        ),
        "reliability_totals": {key: sum(values) if values else None
                                for key, values in reliability_values.items()},
        "fallback_agent_counts": fallbacks,
        "claim_extraction_telemetry": {
            "cases_observed": extraction_cases,
            "fallback_cases": extraction_fallback_cases,
            "status_counts": {key: dict(sorted(counts.items()))
                              for key, counts in extraction_status_counts.items()},
            "item_count_totals": {key: sum(values) if values else None
                                  for key, values in extraction_item_totals.items()},
        },
    }


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if isinstance(value, str) and value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


# A plain dict alias keeps the output JSON-native without exposing Counter behavior.
CounterLike = dict[str, int]
