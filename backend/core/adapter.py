from backend.core.state import AgentState


def build_agent_input(agent_name: str, state: AgentState) -> dict:
    if agent_name == "sentiment":
        return {"event": state.event}
    if agent_name == "writer":
        return _build_writer_input(state)
    if agent_name == "redteam":
        return _build_redteam_input(state)
    if agent_name == "legal":
        return _build_legal_input(state)
    if agent_name == "decision":
        return {
            "event": state.event,
            "results": state.get_all_results(),
        }

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
    return {
        "event": state.event,
        "draft": writer_result.get("statement", ""),
        "redteam_review": state.get_result("redteam") or {},
    }
