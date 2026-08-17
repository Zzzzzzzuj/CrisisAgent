from backend.guardrails.prompt_injection import detect_prompt_injection


def evaluate_input_guardrail(event: str) -> dict:
    prompt_injection = detect_prompt_injection(event)
    issues = []
    if prompt_injection["hit"]:
        issues.append(
            {
                "category": "prompt_injection",
                "severity": prompt_injection["severity"],
                "reason": prompt_injection["reason"],
                "matched_signals": prompt_injection["matched_signals"],
            }
        )

    return {
        "hit": bool(issues),
        "severity": _resolve_severity(issues),
        "issues": issues,
        "prompt_injection": prompt_injection,
    }


def _resolve_severity(issues: list[dict]) -> str:
    if any(issue.get("severity") == "high" for issue in issues):
        return "high"
    if issues:
        return "medium"
    return "none"
