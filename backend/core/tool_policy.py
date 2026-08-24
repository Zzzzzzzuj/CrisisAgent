SENSITIVE_ACTIONS = {
    "publish",
    "approve",
    "reject",
    "approval",
    "rejection",
    "final_publish",
}

HIGH_RISK_REQUIRED_TOOLS = {"legal_rag_search", "guardrail_check"}


def validate_tool_plan_safety(plan: dict) -> dict:
    risk_level = str(plan.get("risk_level", "")).lower()
    required_tools = set(plan.get("required_tools", []))
    if risk_level == "high":
        missing = sorted(HIGH_RISK_REQUIRED_TOOLS - required_tools)
        if missing:
            return {
                "allow": False,
                "reason": f"high_risk_plan_missing_required_tools:{','.join(missing)}",
            }
    return {"allow": True, "reason": "plan_allowed"}


def evaluate_tool_call_policy(tool_name: str, arguments: dict, plan: dict | None = None) -> dict:
    normalized_name = str(tool_name or "").strip()
    lowered_name = normalized_name.lower()
    if lowered_name in SENSITIVE_ACTIONS or any(action in lowered_name for action in SENSITIVE_ACTIONS):
        return {
            "allow": False,
            "reason": "sensitive_action_must_not_be_called_by_llm",
        }
    if not isinstance(arguments, dict):
        return {
            "allow": False,
            "reason": "tool_arguments_must_be_object",
        }
    if plan and str(plan.get("risk_level", "")).lower() == "high":
        required_tools = set(plan.get("required_tools", []))
        if not HIGH_RISK_REQUIRED_TOOLS <= required_tools:
            return {
                "allow": False,
                "reason": "high_risk_case_cannot_skip_legal_rag_or_guardrail",
            }
    return {
        "allow": True,
        "reason": "tool_call_allowed",
    }
