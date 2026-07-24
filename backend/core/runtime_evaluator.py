from backend.core.state import AgentState


def evaluate_runtime_state(state: AgentState) -> dict:
    issues = []
    quality_scores = _extract_quality_scores(state)

    if state.failed_agents:
        failed_agent_names = [item["agent"] for item in state.failed_agents]
        issues.append(f"Failed agents: {', '.join(str(agent) for agent in failed_agent_names)}")

    if not state.get_result("decision"):
        issues.append("Decision result is missing.")
    else:
        issues.extend(_score_issues(quality_scores))

    return {
        "passed": not issues,
        "issues": issues,
        "quality_scores": quality_scores,
        "result_count": len(state.get_all_results()),
        "failed_agent_count": len(state.failed_agents),
    }


def _extract_quality_scores(state: AgentState) -> dict:
    decision = state.get_result("decision") or {}
    return dict(decision.get("scores", {}))


def _score_issues(scores: dict) -> list[str]:
    issues = []
    if scores.get("legal_safety", 10) < 7:
        issues.append("legal_safety score is below threshold.")
    if scores.get("empathy", 10) < 6:
        issues.append("empathy score is below threshold.")
    if scores.get("robustness", 10) < 6:
        issues.append("robustness score is below threshold.")
    return issues
