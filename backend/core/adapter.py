from backend.core.state import AgentState


def build_agent_input(agent_name: str, state: AgentState) -> dict:
    if agent_name == "sentiment":
        return {"event": state.event}
    if agent_name == "writer":
        return _build_writer_input(state)
    if agent_name == "writer_v2":
        return _build_writer_v2_input(state)
    if agent_name == "redteam":
        return _build_redteam_input(state)
    if agent_name == "legal":
        return _build_legal_input(state)
    if agent_name == "decision":
        return _build_decision_input(state)

    raise ValueError(f"Unsupported agent for adapter: {agent_name}")


def _build_writer_input(state: AgentState) -> dict:
    payload = {
        "event": state.event,
        "sentiment_analysis": state.get_result("sentiment") or {},
    }
    if "memory_context" in state.metadata:
        payload["memory_context"] = state.metadata["memory_context"]
    return payload


def _build_redteam_input(state: AgentState) -> dict:
    writer_result = state.get_result("writer") or {}
    return {
        "event": state.event,
        "draft": writer_result.get("statement", ""),
    }


def _build_legal_input(state: AgentState) -> dict:
    writer_result = state.get_result("writer") or {}
    planner_input = state.metadata.get("planner_input", {})
    return {
        "event": state.event,
        "draft": writer_result.get("statement", ""),
        "redteam_review": state.get_result("redteam") or {},
        "sentiment_analysis": state.get_result("sentiment") or {},
        "planner_input": planner_input,
        "category": planner_input.get("category") if isinstance(planner_input, dict) else None,
    }


def _build_writer_v2_input(state: AgentState) -> dict:
    return {
        "event": state.event,
        "first_draft": state.get_result("writer") or {},
        "redteam_review": state.get_result("redteam") or {},
        "legal_review": state.get_result("legal") or {},
    }


def _build_decision_input(state: AgentState) -> dict:
    writer_v2_result = state.get_result("writer_v2") or {}
    return {
        "event": state.event,
        "second_draft": writer_v2_result.get("statement", ""),
        "sentiment_analysis": state.get_result("sentiment") or {},
        "redteam_review": state.get_result("redteam") or {},
        "legal_review": state.get_result("legal") or {},
        "results": state.get_all_results(),
    }
