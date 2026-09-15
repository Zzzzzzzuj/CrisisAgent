import copy
import pytest

from backend.harness.policy_guardrails import analyze_policy_diff, evaluate_policy_safety_gate, validate_policy_diff
from backend.harness.spec import build_default_harness_spec
from backend.evaluation.harness_comparison import compare_harnesses, evaluate_comparison_gate


def test_retry_and_timeout_increase_are_safe():
    base = build_default_harness_spec()
    candidate = copy.deepcopy(base)
    candidate["skills_tools"]["timeout_ms"] = 4000
    candidate["skills_tools"]["max_retries"] = 1
    diff = analyze_policy_diff(base, candidate)
    assert diff["safety_weakening"] is False
    assert {item["category"] for item in diff["changes"]} == {"safe"}


@pytest.mark.parametrize("field", [
    "review_policy.triggers.evidence_low_confidence",
    "review_policy.triggers.evidence_conflict",
    "review_policy.triggers.review_scope_mismatch",
])
def test_disabling_review_trigger_is_safety_weakening(field):
    base = build_default_harness_spec()
    candidate = copy.deepcopy(base)
    node, key = candidate, field.split(".")
    for part in key[:-1]:
        node = node[part]
    node[key[-1]] = False
    diff = analyze_policy_diff(base, candidate)
    assert diff["safety_weakening"] is True
    if field != "review_policy.triggers.evidence_low_confidence":
        assert field in diff["blocked_fields"]


def test_policy_diff_is_included_in_golden_and_gate_cannot_ignore_weakening():
    base = build_default_harness_spec()
    candidate = copy.deepcopy(base)
    candidate["retrieval_policy"]["min_score"] = 0.01
    comparison = compare_harnesses(base, candidate, [{"case_id": "one"}])
    assert comparison["policy_diff"]["safety_weakening"] is True
    comparison["baseline"]["cases"] = [{"human_review_required": True}]
    comparison["candidate"]["cases"] = [{"human_review_required": False}]
    assert evaluate_policy_safety_gate(comparison)["passed"] is False
    assert evaluate_comparison_gate(comparison)["passed"] is False


def test_critical_review_weakening_is_rejected():
    base = build_default_harness_spec()
    candidate = copy.deepcopy(base)
    candidate["review_policy"]["triggers"]["evidence_conflict"] = False
    diff = analyze_policy_diff(base, candidate)
    with pytest.raises(ValueError, match="critical"):
        validate_policy_diff(diff)
