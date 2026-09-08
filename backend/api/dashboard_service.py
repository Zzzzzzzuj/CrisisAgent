from __future__ import annotations

from collections import defaultdict
from typing import Any


SEVERITIES = ("SEV-1", "SEV-2", "SEV-3", "SEV-4")


def build_urgency(event: dict[str, Any]) -> dict[str, Any]:
    """Turn persisted event metadata into an explainable, read-only priority."""
    score = 0
    reasons: list[str] = []

    risk_level = str(event.get("risk_level", "")).lower()
    if risk_level == "high":
        score += 40
        reasons.append("high_risk")
    elif risk_level == "medium":
        score += 25
        reasons.append("medium_risk")
    elif risk_level == "low":
        score += 10
        reasons.append("low_risk")

    fact_status = str(event.get("fact_status", "")).lower()
    if fact_status == "conflicting":
        score += 25
        reasons.append("conflicting_facts")
    elif fact_status == "unverified":
        score += 15
        reasons.append("unverified_facts")

    event_status = str(event.get("event_status", "")).lower()
    if event_status == "current":
        score += 15
        reasons.append("current_event")
    elif event_status == "uncertain":
        score += 10
        reasons.append("uncertain_event")
    elif event_status == "historical":
        score -= 20
        reasons.append("historical_event")

    source_count = max(0, int(event.get("source_count", 0) or 0))
    if source_count >= 5:
        score += 15
        reasons.append("five_or_more_sources")
    elif source_count >= 2:
        score += 8
        reasons.append("multiple_sources")

    human_review_required = bool(event.get("human_review_required", False))
    if human_review_required:
        score += 15
        reasons.append("human_review_required")

    status = str(event.get("status", "new")).lower()
    if status == "waiting_human":
        score += 10
        reasons.append("waiting_human")
    elif status == "failed":
        score += 10
        reasons.append("agent_run_failed")
    elif status == "completed":
        score -= 10
        reasons.append("agent_run_completed")
    elif status == "archived":
        score -= 30
        reasons.append("archived")

    urgency_score = min(100, max(0, score))
    severity = _severity_for_score(urgency_score)
    return {
        "event_id": str(event.get("event_id", "")),
        "title": str(event.get("title", "未命名危机事件")),
        "company": str(event.get("company", "")),
        "risk_level": risk_level,
        "fact_status": fact_status,
        "event_status": event_status,
        "human_review_required": human_review_required,
        "source_count": source_count,
        "status": status,
        "urgency_score": urgency_score,
        "severity": severity,
        "priority_reasons": reasons,
        "recommended_action": _recommended_action(severity),
    }


def build_overview(events: list[dict[str, Any]]) -> dict[str, Any]:
    urgency_items = [build_urgency(event) for event in events]
    counts = {severity: 0 for severity in SEVERITIES}
    for item in urgency_items:
        counts[item["severity"]] += 1

    active_items = [item for item in urgency_items if item["status"] != "archived"]
    return {
        "total_events": len(urgency_items),
        "sev1_count": counts["SEV-1"],
        "sev2_count": counts["SEV-2"],
        "sev3_count": counts["SEV-3"],
        "sev4_count": counts["SEV-4"],
        "waiting_human_count": sum(item["status"] == "waiting_human" for item in urgency_items),
        "unverified_count": sum(item["fact_status"] == "unverified" for item in urgency_items),
        "conflicting_count": sum(item["fact_status"] == "conflicting" for item in urgency_items),
        "high_risk_count": sum(item["risk_level"] == "high" for item in urgency_items),
        "active_event_count": len(active_items),
        "top_urgent_events": _sort_by_priority(active_items)[:5],
        "automatic_publish": False,
    }


def build_severity_groups(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = {severity: [] for severity in SEVERITIES}
    for event in events:
        item = build_urgency(event)
        grouped[item["severity"]].append(item)
    return [
        {"severity": severity, "events": _sort_by_priority(grouped[severity])}
        for severity in SEVERITIES
    ]


def build_trends(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "high_risk": 0, "waiting_human": 0})
    for event in events:
        bucket = str(event.get("created_at", ""))[:10] or "unknown"
        current = buckets[bucket]
        current["total"] += 1
        current["high_risk"] += str(event.get("risk_level", "")).lower() == "high"
        current["waiting_human"] += str(event.get("status", "")).lower() == "waiting_human"
    return [{"bucket": bucket, **buckets[bucket]} for bucket in sorted(buckets)]


def build_source_health(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for run in runs:
        for result in run.get("source_results", []) or []:
            if not isinstance(result, dict):
                continue
            source_id = str(result.get("source_id", ""))
            if not source_id:
                continue
            item = grouped.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "latest_status": str(result.get("status", "unknown")),
                    "total_runs": 0,
                    "collected_count": 0,
                    "no_match_count": 0,
                    "failed_count": 0,
                    "skipped_by_robots_count": 0,
                    "disabled_count": 0,
                },
            )
            # IngestionRun store lists newest records first, so keep its first status.
            if item["total_runs"] == 0:
                item["latest_status"] = str(result.get("status", "unknown"))
            item["total_runs"] += 1
            status = str(result.get("status", "unknown"))
            if status == "collected":
                item["collected_count"] += 1
            elif status == "no_match":
                item["no_match_count"] += 1
            elif status == "failed":
                item["failed_count"] += 1
            elif status == "skipped_by_robots":
                item["skipped_by_robots_count"] += 1
            elif status == "disabled":
                item["disabled_count"] += 1

    health = []
    for item in grouped.values():
        attempted = (
            item["collected_count"]
            + item["no_match_count"]
            + item["failed_count"]
            + item["skipped_by_robots_count"]
        )
        item["failure_rate"] = round(
            (item["failed_count"] + item["skipped_by_robots_count"]) / attempted,
            4,
        ) if attempted else 0.0
        health.append(item)
    return sorted(health, key=lambda item: item["source_id"])


def build_review_queue(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = []
    for event in events:
        item = build_urgency(event)
        if item["status"] == "archived":
            continue
        if (
            item["human_review_required"]
            or item["status"] == "waiting_human"
            or item["fact_status"] in {"unverified", "conflicting"}
            or item["event_status"] == "uncertain"
        ):
            queue.append(item)
    return _sort_by_priority(queue)


def _severity_for_score(score: int) -> str:
    if score >= 80:
        return "SEV-1"
    if score >= 60:
        return "SEV-2"
    if score >= 35:
        return "SEV-3"
    return "SEV-4"


def _recommended_action(severity: str) -> str:
    return {
        "SEV-1": "立即人工审核并启动危机响应",
        "SEV-2": "尽快审核并准备声明草稿",
        "SEV-3": "持续观察并补充来源",
        "SEV-4": "记录归档或低频观察",
    }[severity]


def _sort_by_priority(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (item["status"] == "archived", -item["urgency_score"], item["event_id"]),
    )
