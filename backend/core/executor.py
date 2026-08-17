from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable

from backend.agents import decision_agent, legal_agent, redteam_agent, sentiment_agent, writer_agent
from backend.core.adapter import build_agent_input
from backend.core.state import AgentState
from backend.llm.client import get_last_llm_trace, reset_last_llm_trace


AgentRunner = Callable[[dict], dict]
AGENT_REGISTRY: dict[str, AgentRunner] = {
    "sentiment": sentiment_agent.run,
    "writer": writer_agent.run,
    "writer_v2": writer_agent.generate_second_draft,
    "redteam": redteam_agent.run,
    "legal": legal_agent.run,
    "decision": decision_agent.run,
}


def execute(plan: dict, state, agent_registry: dict[str, AgentRunner] | None = None) -> dict:
    registry = agent_registry or AGENT_REGISTRY
    plan_id = plan.get("plan_id")
    agent_state = _ensure_state(plan_id, state)
    executed_agents = []

    for item in plan.get("plan", []):
        agent_name = item.get("agent")
        reason = item.get("reason", "")
        agent_state.current_agent = agent_name
        start_time = _now_iso()

        if agent_name not in registry:
            error = "Agent is not registered."
            agent_state.mark_failed(agent_name, error)
            agent_state.add_trace(
                _build_trace_item(agent_name, reason, start_time, _now_iso(), "failed", None, error)
            )
            continue

        try:
            reset_last_llm_trace()
            payload = build_agent_input(agent_name, agent_state)
            output = registry[agent_name](_adapt_payload_for_runner(agent_name, payload))
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            agent_state.mark_failed(agent_name, error)
            trace_item = _build_trace_item(agent_name, reason, start_time, _now_iso(), "failed", None, error)
            trace_item.update(_collect_llm_metadata())
            agent_state.add_trace(trace_item)
            continue

        executed_agents.append(agent_name)
        agent_state.set_result(agent_name, output)
        trace_item = _build_trace_item(agent_name, reason, start_time, _now_iso(), "success", output, None)
        trace_item.update(_collect_llm_metadata())
        trace_item.update(_collect_agent_metadata(agent_name))
        agent_state.add_trace(trace_item)

    agent_state.current_agent = None
    return {
        "plan_id": plan_id,
        "executed_agents": executed_agents,
        "results": agent_state.get_all_results(),
        "failed_agents": list(agent_state.failed_agents),
        "execution_trace": list(agent_state.trace),
    }


def _ensure_state(plan_id: str | None, state) -> AgentState:
    if isinstance(state, AgentState):
        return state

    context = state if isinstance(state, dict) else {}
    return AgentState(
        session_id=str(context.get("session_id", "")),
        plan_id=str(plan_id or context.get("plan_id", "")),
        event=str(context.get("event", "")),
        results=dict(context.get("results", {})),
        trace=list(context.get("trace", [])),
        metadata=dict(context.get("metadata", {})),
    )


def _adapt_payload_for_runner(agent_name: str, payload: dict):
    if agent_name == "sentiment":
        return payload["event"]
    return payload


def _build_trace_item(
    agent: str | None,
    reason: str,
    start_time: str,
    end_time: str,
    status: str,
    output,
    error: str | None,
) -> dict:
    return {
        "agent": agent,
        "reason": reason,
        "start_time": start_time,
        "end_time": end_time,
        "status": status,
        "output": output,
        "error": error,
    }


def _collect_agent_metadata(agent_name: str | None) -> dict:
    if agent_name != "legal":
        return {}

    try:
        rag_info = legal_agent.get_last_rag_info()
    except Exception:
        return {}

    return {"rag": deepcopy(rag_info)}


def _collect_llm_metadata() -> dict:
    llm_trace = get_last_llm_trace()
    if not llm_trace:
        return {}
    return {"llm": deepcopy(llm_trace)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
