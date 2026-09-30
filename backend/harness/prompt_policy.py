from __future__ import annotations

from copy import deepcopy
from typing import Any


POLICY_PATH = "prompts.policies.writer_v2.unsupported_commitment_policy.require_case_fact_for_concrete_commitment"
DEFAULT_WRITER_V2_POLICY = {
    "policy_id": "unsupported_commitment_v1",
    "require_case_fact_for_concrete_commitment": False,
    "allow_conditional_wording": True,
    "allow_unknown_wording": True,
}


def get_writer_v2_policy(spec: dict[str, Any] | None) -> dict[str, Any]:
    prompts = spec.get("prompts", {}) if isinstance(spec, dict) else {}
    policies = prompts.get("policies", {}) if isinstance(prompts, dict) else {}
    writer = policies.get("writer_v2", {}) if isinstance(policies, dict) else {}
    policy = writer.get("unsupported_commitment_policy", {}) if isinstance(writer, dict) else {}
    return {**DEFAULT_WRITER_V2_POLICY, **policy} if isinstance(policy, dict) else deepcopy(DEFAULT_WRITER_V2_POLICY)


def validate_writer_v2_policy(spec: dict[str, Any]) -> None:
    prompts = spec.get("prompts", {})
    if not isinstance(prompts, dict):
        raise ValueError("prompts must be an object.")
    policies = prompts.get("policies")
    if policies is None:
        return
    if not isinstance(policies, dict):
        raise ValueError("prompts.policies must be an object.")
    writer = policies.get("writer_v2")
    if writer is None:
        return
    if not isinstance(writer, dict):
        raise ValueError("writer_v2 prompt policies must be an object.")
    policy = writer.get("unsupported_commitment_policy")
    if policy is None:
        return
    if not isinstance(policy, dict) or set(policy) != set(DEFAULT_WRITER_V2_POLICY):
        raise ValueError("unsupported_commitment_policy contains unsupported fields.")
    if policy.get("policy_id") != DEFAULT_WRITER_V2_POLICY["policy_id"]:
        raise ValueError("unsupported_commitment_policy policy_id is immutable.")
    if any(type(policy.get(key)) is not bool for key in DEFAULT_WRITER_V2_POLICY if key != "policy_id"):
        raise ValueError("unsupported_commitment_policy values must be booleans.")


def ensure_writer_v2_policy(spec: dict[str, Any]) -> None:
    prompts = spec.setdefault("prompts", {})
    policies = prompts.setdefault("policies", {})
    writer = policies.setdefault("writer_v2", {})
    writer.setdefault("unsupported_commitment_policy", deepcopy(DEFAULT_WRITER_V2_POLICY))


def validate_writer_v2_candidate_scope(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    left, right = deepcopy(baseline), deepcopy(candidate)
    ensure_writer_v2_policy(left)
    ensure_writer_v2_policy(right)
    validate_writer_v2_policy(left)
    validate_writer_v2_policy(right)
    for spec in (left, right):
        metadata = spec.get("metadata", {})
        for field in ("harness_id", "version", "status", "created_at", "parent_version", "change_summary", "changed_fields", "approval", "rejection", "comparison_id", "gate_result", "policy_diff"):
            metadata.pop(field, None)
    changed = _changed_paths(left, right)
    if changed != {POLICY_PATH}:
        raise ValueError("Writer V2 replay Candidate may only change unsupported_commitment_policy.")
    policy = get_writer_v2_policy(candidate)
    if policy["require_case_fact_for_concrete_commitment"] is not True:
        raise ValueError("Writer V2 trigger replay requires the Candidate policy to be enabled.")


def writer_v2_policy_overlay(spec: dict[str, Any] | None) -> str:
    policy = get_writer_v2_policy(spec)
    if not policy["require_case_fact_for_concrete_commitment"]:
        return ""
    return """
事实边界策略（高于上方通用写作要求）：
- 具体时间/期限、恢复时间、退款时限或金额、调查结论、监管报告动作、声称已完成的企业行动，必须有可信且独立核验的企业个案事实依据；没有依据时不得写成确定承诺或既成事实。
- 用户/新闻/事件描述及 human_asserted 信息不等于 independently_verified。
- 可以说明“正在核查”“事实尚待确认”；可以使用条件式表达，或明确说明暂无法确认。
- 若通用要求与本策略冲突，以本策略为准；不得为了补充行动、监管配合或后续安排而编造具体承诺。
""".strip()


def _changed_paths(left: Any, right: Any, prefix: str = "") -> set[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        changed = set()
        for key in left.keys() | right.keys():
            path = f"{prefix}.{key}" if prefix else str(key)
            changed.update(_changed_paths(left.get(key), right.get(key), path))
        return changed
    return set() if left == right else {prefix}
