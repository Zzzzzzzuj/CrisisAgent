from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MonitoringEvalCase:
    case_id: str
    signal: str
    expected_relevant: bool
    expected_risk: bool
    predicted_relevant: bool
    predicted_risk: bool
    alert_created: bool
    human_review_required: bool
    duplicate: bool = False


def load_monitoring_eval_cases(path: str | Path) -> list[MonitoringEvalCase]:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    return [MonitoringEvalCase(**item) for item in values]


def run_monitoring_eval(cases: list[MonitoringEvalCase]) -> dict[str, Any]:
    total = len(cases)
    relevant = sum(case.expected_relevant for case in cases)
    predicted_relevant = sum(case.predicted_relevant for case in cases)
    predicted_risk = sum(case.predicted_risk for case in cases)
    risk_tp = sum(case.expected_risk and case.predicted_risk for case in cases)
    alerts = [case for case in cases if case.alert_created]
    alert_tp = sum(case.expected_risk and case.alert_created for case in cases)
    missed = [case.case_id for case in cases if case.expected_risk and not case.predicted_risk]
    false_positive = [case.case_id for case in cases if not case.expected_risk and case.alert_created]
    details = []
    for case in cases:
        reasons = []
        if case.expected_relevant != case.predicted_relevant:
            reasons.append("mention_relevance_mismatch")
        if case.expected_risk != case.predicted_risk:
            reasons.append("risk_prediction_mismatch")
        if case.expected_risk != case.alert_created:
            reasons.append("alert_decision_mismatch")
        if case.duplicate:
            reasons.append("duplicate_signal")
        details.append({**asdict(case), "reasons": reasons, "passed": not reasons})
    return {
        "total_cases": total,
        "mention_relevance": _rate(sum(case.expected_relevant == case.predicted_relevant for case in cases), total),
        "risk_precision": _rate(risk_tp, predicted_risk),
        "duplicate_rate": _rate(sum(case.duplicate for case in cases), total),
        "alert_precision": _rate(alert_tp, len(alerts)),
        "human_review_rate": _rate(sum(case.human_review_required for case in cases), total),
        "false_positive_count": len(false_positive),
        "missed_risk_count": len(missed),
        "failed_cases": [detail for detail in details if not detail["passed"]],
        "case_results": details,
    }


def _rate(numerator: int | bool, denominator: int) -> float:
    return round(float(numerator) / denominator, 4) if denominator else 0.0
