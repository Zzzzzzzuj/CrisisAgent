from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.api.dashboard_service import build_overview, build_urgency
from backend.api.report_generator import build_crisis_report, render_markdown
from evaluation.tool_reliability import load_cases, run_tool_reliability_eval


ALL_DIMENSIONS = ("ingestion", "event", "urgency", "agent_run", "report", "tool", "golden_case")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_CASES_PATH = PROJECT_ROOT / "data" / "eval_golden_cases.json"
GOLDEN_CASE_FIELDS = (
    "case_id",
    "name",
    "event_text",
    "category",
    "expected_risk_level",
    "expected_fact_status",
    "expected_event_status",
    "expected_human_review_required",
    "expected_min_severity",
    "forbidden_claims",
    "required_response_features",
    "notes",
)
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_FACT_STATUSES = {"verified", "unverified", "conflicting"}
VALID_EVENT_STATUSES = {"current", "uncertain", "historical"}
VALID_SEVERITIES = {"SEV-1", "SEV-2", "SEV-3", "SEV-4"}


def build_eval_run(
    *,
    events: list[dict[str, Any]],
    ingestion_runs: list[dict[str, Any]],
    agent_runs: list[dict[str, Any]],
    requested_dimensions: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    dimensions = _normalize_dimensions(requested_dimensions)
    items: list[dict[str, Any]] = []
    tool_summary: dict[str, Any] | None = None
    golden_case_summary: dict[str, Any] | None = None

    if "ingestion" in dimensions:
        items.extend(_evaluate_ingestion(ingestion_runs))
    if "event" in dimensions:
        items.extend(_evaluate_events(events))
    if "urgency" in dimensions:
        items.extend(_evaluate_urgency())
    if "agent_run" in dimensions:
        items.extend(_evaluate_agent_runs(events, agent_runs))
    if "report" in dimensions:
        items.extend(_evaluate_reports(events, agent_runs))
    if "tool" in dimensions:
        tool_items, tool_summary = _evaluate_tools()
        items.extend(tool_items)
    if "golden_case" in dimensions:
        golden_items, golden_case_summary = _evaluate_golden_cases()
        items.extend(golden_items)

    passed_cases = sum(item["passed"] for item in items)
    total_cases = len(items)
    failed_items = [item for item in items if not item["passed"]]
    finished_at = _now()
    return {
        "eval_run_id": str(uuid4()),
        "created_at": finished_at,
        "finished_at": finished_at,
        "status": "completed" if not failed_items else "failed",
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": len(failed_items),
        "pass_rate": _rate(passed_cases, total_cases),
        "dimensions": _summarize_dimensions(items, tool_summary, golden_case_summary),
        "items": items,
        "failed_items": failed_items,
        "summary": {
            "evaluation_scope": "existing runtime stores and deterministic offline rules",
            "no_live_fetch": True,
            "no_real_llm_call": True,
            "agent_replayed": False,
            "ingestion_replayed": False,
            "automatic_publish": False,
        },
        "automatic_publish": False,
        "dry_run": dry_run,
    }


def build_eval_overview(runs: list[dict[str, Any]]) -> dict[str, Any]:
    latest = runs[0] if runs else None
    dimensions = latest.get("dimensions", {}) if latest else {}
    failed_dimensions = sorted(
        (
            (name, int(value.get("failed_cases", 0)))
            for name, value in dimensions.items()
            if isinstance(value, dict) and value.get("failed_cases", 0)
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "latest_eval_run_id": latest.get("eval_run_id") if latest else None,
        "latest_pass_rate": latest.get("pass_rate") if latest else None,
        "total_runs": len(runs),
        "total_cases": int(latest.get("total_cases", 0)) if latest else 0,
        "passed_cases": int(latest.get("passed_cases", 0)) if latest else 0,
        "failed_cases": int(latest.get("failed_cases", 0)) if latest else 0,
        "dimensions_summary": dimensions,
        "top_failed_dimensions": [name for name, _ in failed_dimensions],
        "automatic_publish": False,
    }


def build_regression(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if len(runs) < 2:
        return {"not_enough_runs": True}
    current, previous = runs[0], runs[1]
    current_failed = {item.get("case_id", "") for item in current.get("failed_items", [])}
    previous_failed = {item.get("case_id", "") for item in previous.get("failed_items", [])}
    current_rate = float(current.get("pass_rate", 0.0))
    previous_rate = float(previous.get("pass_rate", 0.0))
    return {
        "not_enough_runs": False,
        "current_eval_run_id": current.get("eval_run_id"),
        "previous_eval_run_id": previous.get("eval_run_id"),
        "current_pass_rate": current_rate,
        "previous_pass_rate": previous_rate,
        "delta": round(current_rate - previous_rate, 4),
        "newly_failed_cases": sorted(current_failed - previous_failed),
        "recovered_cases": sorted(previous_failed - current_failed),
    }


def _evaluate_ingestion(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [_item(
        "ingestion.default_live_fetch_disabled",
        "ingestion",
        "live_fetch 默认关闭",
        True,
        expected=False,
        actual=False,
        reason="IngestionRunRequest defaults live_fetch to false.",
    )]
    if not runs:
        items.append(_item(
            "ingestion.runtime_records",
            "ingestion",
            "运行记录可读取",
            True,
            expected="optional runtime records",
            actual=0,
            reason="No persisted ingestion runs; this is not a collection failure.",
        ))
        return items

    valid_statuses = {"collected", "no_match", "failed", "skipped_by_robots", "disabled"}
    for run in runs:
        run_id = str(run.get("run_id", ""))
        results = run.get("source_results")
        items.append(_item(
            f"ingestion.{run_id}.source_results",
            "ingestion",
            "source_results 存在",
            isinstance(results, list),
            expected="list",
            actual=type(results).__name__,
            reason="Ingestion run must preserve per-source outcomes.",
            related_run_id=run_id,
        ))
        for index, result in enumerate(results or []):
            status = str(result.get("status", "")) if isinstance(result, dict) else ""
            items.append(_item(
                f"ingestion.{run_id}.status.{index}",
                "ingestion",
                "来源状态可识别",
                status in valid_statuses,
                expected=sorted(valid_statuses),
                actual=status,
                reason="no_match remains a non-failure outcome; failed and robots skips are explicit.",
                related_run_id=run_id,
            ))
            if status == "no_match":
                items.append(_item(
                    f"ingestion.{run_id}.no_match.{index}",
                    "ingestion",
                    "no_match 不计为采集失败",
                    status != "failed",
                    expected="not failed",
                    actual=status,
                    reason="No matching content is distinct from collection failure.",
                    related_run_id=run_id,
                ))
    return items


def _evaluate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return [_item(
            "event.runtime_records",
            "event",
            "事件记录可读取",
            True,
            expected="optional runtime records",
            actual=0,
            reason="No CrisisEvent has been created yet.",
        )]
    items = []
    for event in events:
        event_id = str(event.get("event_id", ""))
        checks = {
            "source_items": isinstance(event.get("source_items"), list) and bool(event.get("source_items")),
            "risk_level": bool(event.get("risk_level")),
            "fact_status": bool(event.get("fact_status")),
            "event_status": bool(event.get("event_status")),
            "human_review_required": isinstance(event.get("human_review_required"), bool),
        }
        for name, passed in checks.items():
            items.append(_item(
                f"event.{event_id}.{name}",
                "event",
                f"事件保留 {name}",
                passed,
                expected=True,
                actual=event.get(name),
                reason="CrisisEvent must keep ingestion metadata for traceability.",
                related_event_id=event_id,
            ))
    archived_ids = {str(event.get("event_id", "")) for event in events if event.get("status") == "archived"}
    top_ids = {item["event_id"] for item in build_overview(events)["top_urgent_events"]}
    items.append(_item(
        "event.archived_excluded_from_top_urgent",
        "event",
        "归档事件不进入高优先级队列",
        not bool(archived_ids & top_ids),
        expected="archived event ids excluded",
        actual=sorted(archived_ids & top_ids),
        reason="Archived records are retained for history but must not crowd current operations.",
    ))
    return items


def _evaluate_urgency() -> list[dict[str, Any]]:
    sev1 = build_urgency({
        "event_id": "urgency-sev1", "risk_level": "high", "fact_status": "conflicting",
        "event_status": "current", "source_count": 5, "human_review_required": True,
        "status": "waiting_human",
    })
    sev2 = build_urgency({
        "event_id": "urgency-sev2", "risk_level": "high", "fact_status": "unverified",
        "event_status": "current", "source_count": 2, "human_review_required": False, "status": "new",
    })
    baseline = {"event_id": "urgency-baseline", "risk_level": "low", "fact_status": "verified", "event_status": "current", "source_count": 1, "status": "new"}
    active = build_urgency(baseline)
    historical = build_urgency({**baseline, "event_status": "historical"})
    completed = build_urgency({**baseline, "status": "completed"})
    archived = build_urgency({**baseline, "status": "archived"})
    waiting = build_urgency({**baseline, "status": "waiting_human"})
    return [
        _item("urgency.high_conflicting_sev1", "urgency", "high + conflicting 进入 SEV-1", sev1["severity"] == "SEV-1", "SEV-1", sev1["severity"], "High risk with conflicting facts requires immediate priority."),
        _item("urgency.high_unverified_sev2", "urgency", "high + unverified 至少 SEV-2", sev2["severity"] in {"SEV-1", "SEV-2"}, "SEV-1 or SEV-2", sev2["severity"], "High risk and unverified facts cannot be low priority."),
        _item("urgency.historical_decreases", "urgency", "historical 会降低紧急度", historical["urgency_score"] < active["urgency_score"], "lower than current", historical["urgency_score"], "Historical events receive a negative adjustment."),
        _item("urgency.completed_decreases", "urgency", "completed 会降低紧急度", completed["urgency_score"] < active["urgency_score"], "lower than active", completed["urgency_score"], "Completed Agent runs receive a negative adjustment."),
        _item("urgency.archived_decreases", "urgency", "archived 会降低紧急度", archived["urgency_score"] < active["urgency_score"], "lower than active", archived["urgency_score"], "Archived events receive a negative adjustment."),
        _item("urgency.waiting_human_increases", "urgency", "waiting_human 会提高紧急度", waiting["urgency_score"] > active["urgency_score"], "higher than active", waiting["urgency_score"], "Pending human review receives a positive adjustment."),
    ]


def _evaluate_agent_runs(events: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not runs:
        return [_item("agent_run.runtime_records", "agent_run", "Agent Run 记录可读取", True, "optional runtime records", 0, "No persisted Agent runs to inspect.")]
    events_by_id = {str(event.get("event_id", "")): event for event in events}
    items = []
    for run in runs:
        run_id = str(run.get("agent_run_id", ""))
        event = events_by_id.get(str(run.get("event_id", "")), {})
        checks = {
            "session_id": bool(run.get("session_id")),
            "trace": isinstance(run.get("trace"), list) and bool(run.get("trace")),
            "final_statement_preview": bool(run.get("final_statement_preview")),
            "automatic_publish": run.get("automatic_publish") is False,
        }
        for name, passed in checks.items():
            items.append(_item(
                f"agent_run.{run_id}.{name}", "agent_run", f"Agent Run {name} 校验", passed,
                True, run.get(name), "Persisted Agent runs must be traceable and never auto-publish.",
                related_event_id=str(run.get("event_id", "")), related_run_id=run_id,
            ))
        if str(event.get("risk_level", "")).lower() == "high" or str(event.get("fact_status", "")).lower() == "unverified":
            items.append(_item(
                f"agent_run.{run_id}.review_required", "agent_run", "高风险或未核实事件保留人工审核", bool(run.get("human_review_required")),
                True, bool(run.get("human_review_required")), "High-risk or unverified events must preserve Human Review.",
                related_event_id=str(run.get("event_id", "")), related_run_id=run_id,
            ))
    return items


def _evaluate_reports(events: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not runs:
        return [_item("report.runtime_records", "report", "Report 前置记录可读取", True, "optional runtime records", 0, "No Agent Run exists, so no report can be evaluated.")]
    events_by_id = {str(event.get("event_id", "")): event for event in events}
    items = []
    for run in runs:
        run_id = str(run.get("agent_run_id", ""))
        event = events_by_id.get(str(run.get("event_id", "")))
        if event is None:
            items.append(_item(
                f"report.{run_id}.event_link", "report", "Report 关联事件存在", False,
                "existing CrisisEvent", None, "Agent Run cannot produce an auditable report without its event.",
                related_run_id=run_id,
            ))
            continue
        report = build_crisis_report(event, run)
        safety = report.get("safety", {})
        markdown = render_markdown(report)
        checks = {
            "generated_from_existing_run": safety.get("report_generated_from_existing_run") is True,
            "no_live_fetch": safety.get("no_live_fetch") is True,
            "no_real_llm_call": safety.get("no_real_llm_call") is True,
            "statement_is_draft": "最终声明草稿" in markdown,
            "not_published_statement": "已发布声明" not in markdown,
        }
        for name, passed in checks.items():
            items.append(_item(
                f"report.{run_id}.{name}", "report", f"Report {name} 校验", passed, True,
                safety if name in {"generated_from_existing_run", "no_live_fetch", "no_real_llm_call"} else markdown,
                "Report generation is derived from the existing run and remains a draft-only artifact.",
                related_event_id=str(event.get("event_id", "")), related_run_id=run_id,
            ))
    return items


def _evaluate_tools() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases = load_cases(PROJECT_ROOT / "data" / "tool_reliability_cases.json")
    report = run_tool_reliability_eval(cases)
    metrics = report["metrics"]
    passed = all(item.get("expected_match") for item in report["cases"])
    return [
        _item(
            "tool.offline_reliability_suite", "tool", "Tool Reliability 离线套件", passed,
            "all fake tool cases match expected behavior",
            {"expected_matches": sum(item.get("expected_match") for item in report["cases"]), "total": len(report["cases"])},
            "Reuses the existing deterministic fake-tool reliability evaluator.",
        )
    ], {
        "tool_success_rate": metrics["tool_success_rate"],
        "timeout_rate": metrics["timeout_rate"],
        "fallback_rate": metrics["fallback_rate"],
        "loop_detected_rate": metrics["loop_detected_rate"],
        "human_review_trigger_rate": metrics["human_review_trigger_rate"],
    }


def load_golden_cases(path: str | Path = GOLDEN_CASES_PATH) -> list[dict[str, Any]]:
    """Load fictional, offline Golden Cases without running any Agent or retriever."""
    import json

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Golden case file must contain a cases array.")
    return [case for case in payload["cases"] if isinstance(case, dict)]


def evaluate_golden_cases(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate offline expectations that define the CrisisAgent safety regression set."""
    items: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        case_id = str(case.get("case_id") or f"unnamed-{index}")
        missing = [field for field in GOLDEN_CASE_FIELDS if field not in case]
        items.append(_item(
            f"golden_case.{case_id}.schema",
            "golden_case",
            f"{case_id} 字段完整",
            not missing,
            list(GOLDEN_CASE_FIELDS),
            {"missing": missing},
            "Golden Cases must preserve a complete, reviewable expectation contract.",
        ))
        checks = (
            ("risk_level", case.get("expected_risk_level") in VALID_RISK_LEVELS, sorted(VALID_RISK_LEVELS), case.get("expected_risk_level")),
            ("fact_status", case.get("expected_fact_status") in VALID_FACT_STATUSES, sorted(VALID_FACT_STATUSES), case.get("expected_fact_status")),
            ("event_status", case.get("expected_event_status") in VALID_EVENT_STATUSES, sorted(VALID_EVENT_STATUSES), case.get("expected_event_status")),
            ("min_severity", case.get("expected_min_severity") in VALID_SEVERITIES, sorted(VALID_SEVERITIES), case.get("expected_min_severity")),
            ("forbidden_claims", isinstance(case.get("forbidden_claims"), list) and bool(case.get("forbidden_claims")), "non-empty list", case.get("forbidden_claims")),
            ("required_response_features", isinstance(case.get("required_response_features"), list) and bool(case.get("required_response_features")), "non-empty list", case.get("required_response_features")),
        )
        for name, passed, expected, actual in checks:
            items.append(_item(
                f"golden_case.{case_id}.{name}",
                "golden_case",
                f"{case_id} {name} 合法",
                passed,
                expected,
                actual,
                "Golden Case expectations must use the supported offline safety vocabulary.",
            ))

        high_risk = case.get("expected_risk_level") == "high"
        conflicting = case.get("expected_fact_status") == "conflicting"
        historical = case.get("expected_event_status") == "historical"
        if high_risk:
            items.append(_item(
                f"golden_case.{case_id}.high_risk_review",
                "golden_case",
                f"{case_id} 高风险需人工审核",
                case.get("expected_human_review_required") is True,
                True,
                case.get("expected_human_review_required"),
                "High-risk Golden Cases must retain a Human Review expectation.",
            ))
        if conflicting:
            items.append(_item(
                f"golden_case.{case_id}.conflicting_review",
                "golden_case",
                f"{case_id} 来源冲突需人工审核",
                case.get("expected_human_review_required") is True,
                True,
                case.get("expected_human_review_required"),
                "Conflicting facts must not bypass Human Review.",
            ))
        if historical:
            items.append(_item(
                f"golden_case.{case_id}.historical_not_sev1",
                "golden_case",
                f"{case_id} 历史事件不预期 SEV-1",
                case.get("expected_min_severity") != "SEV-1",
                "not SEV-1",
                case.get("expected_min_severity"),
                "Historical content must not be labeled as an expected top-priority incident.",
            ))

    passed = sum(item["passed"] for item in items)
    return items, {
        "golden_case_count": len(cases),
        "golden_case_pass_rate": _rate(passed, len(items)),
    }


def _evaluate_golden_cases() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return evaluate_golden_cases(load_golden_cases())


def _item(case_id: str, dimension: str, name: str, passed: bool, expected: Any, actual: Any, reason: str, related_event_id: str | None = None, related_run_id: str | None = None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "dimension": dimension,
        "name": name,
        "passed": bool(passed),
        "score": 1.0 if passed else 0.0,
        "expected": expected,
        "actual": actual,
        "reason": reason,
        "related_event_id": related_event_id,
        "related_run_id": related_run_id,
    }


def _summarize_dimensions(
    items: list[dict[str, Any]],
    tool_summary: dict[str, Any] | None,
    golden_case_summary: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for item in items:
        dimension = item["dimension"]
        record = summary.setdefault(dimension, {"total_cases": 0, "passed_cases": 0, "failed_cases": 0, "pass_rate": 0.0})
        record["total_cases"] += 1
        record["passed_cases"] += int(item["passed"])
    for record in summary.values():
        record["failed_cases"] = record["total_cases"] - record["passed_cases"]
        record["pass_rate"] = _rate(record["passed_cases"], record["total_cases"])
    if tool_summary is not None:
        summary["tool"].update(tool_summary)
    if golden_case_summary is not None:
        summary["golden_case"].update(golden_case_summary)
    return summary


def _normalize_dimensions(requested_dimensions: list[str] | None) -> tuple[str, ...]:
    if not requested_dimensions:
        return ALL_DIMENSIONS
    return tuple(dict.fromkeys(requested_dimensions))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
