from uuid import uuid4

from backend.agents import decision_agent, planner_agent
from backend.core.executor import AGENT_REGISTRY, execute
from backend.core.guardrail_runtime import apply_guardrails_to_state
from backend.core.plan_validator import validate_plan
from backend.core.reasoning_mode import apply_reasoning_mode_to_state
from backend.core.state import RUNNING, AgentState


def run_dynamic_agent(event: str, agent_registry: dict | None = None) -> dict:
    planner_input = {
        "event": event,
        "category": _infer_category(event),
        "risk_level": _infer_risk_level(event),
    }
    raw_plan = planner_agent.run(planner_input)
    validated_plan = validate_plan(raw_plan)
    state = AgentState(
        session_id=str(uuid4()),
        plan_id=validated_plan["plan_id"],
        event=event,
        metadata={"planner_input": planner_input},
    )
    apply_reasoning_mode_to_state(state)
    execution_result = execute_dynamic_plan_for_state(
        state=state,
        raw_plan=raw_plan,
        validated_plan=validated_plan,
        agent_registry=agent_registry,
    )
    apply_guardrails_to_state(state)
    apply_reasoning_mode_to_state(state)

    return {
        "session_id": state.session_id,
        "plan_id": state.plan_id,
        "event": state.event,
        "planner_input": planner_input,
        "raw_plan": raw_plan,
        "validated_plan": validated_plan,
        "executed_agents": execution_result["executed_agents"],
        "results": state.get_all_results(),
        "failed_agents": list(state.failed_agents),
        "execution_trace": list(state.trace),
        **_reasoning_mode_response(state),
    }


def initialize_dynamic_state(event: str, session_id: str | None = None) -> AgentState:
    planner_input = {
        "event": event,
        "category": _infer_category(event),
        "risk_level": _infer_risk_level(event),
    }
    state = AgentState(
        session_id=session_id or str(uuid4()),
        plan_id="",
        event=event,
        metadata={"planner_input": planner_input},
    )
    apply_guardrails_to_state(state)
    apply_reasoning_mode_to_state(state)
    return state


def execute_dynamic_state(state: AgentState, agent_registry: dict | None = None) -> dict:
    planner_input = state.metadata.get("planner_input") or {
        "event": state.event,
        "category": _infer_category(state.event),
        "risk_level": _infer_risk_level(state.event),
    }
    state.metadata["planner_input"] = planner_input
    raw_plan = planner_agent.run(planner_input)
    validated_plan = validate_plan(raw_plan)
    execution_result = execute_dynamic_plan_for_state(
        state=state,
        raw_plan=raw_plan,
        validated_plan=validated_plan,
        agent_registry=agent_registry,
    )
    apply_guardrails_to_state(state)
    apply_reasoning_mode_to_state(state)
    return build_dynamic_result(
        state=state,
        raw_plan=raw_plan,
        validated_plan=validated_plan,
        execution_result=execution_result,
    )


def execute_dynamic_plan_for_state(
    state: AgentState,
    raw_plan: dict,
    validated_plan: dict,
    agent_registry: dict | None = None,
) -> dict:
    state.set_status(RUNNING)
    state.plan_id = validated_plan["plan_id"]
    execution_result = execute(
        validated_plan,
        state,
        agent_registry=agent_registry or _build_runtime_registry(),
    )
    state.metadata["raw_plan"] = raw_plan
    state.metadata["validated_plan"] = validated_plan
    return execution_result


def build_dynamic_result(
    state: AgentState,
    raw_plan: dict | None = None,
    validated_plan: dict | None = None,
    execution_result: dict | None = None,
) -> dict:
    planner_input = state.metadata.get("planner_input", {})
    raw_plan = raw_plan if raw_plan is not None else state.metadata.get("raw_plan", {})
    validated_plan = (
        validated_plan
        if validated_plan is not None
        else state.metadata.get("validated_plan", {})
    )
    execution_result = execution_result or {
        "executed_agents": [
            item.get("agent")
            for item in state.trace
            if item.get("agent") and item.get("status") == "success"
        ],
    }
    return {
        "session_id": state.session_id,
        "plan_id": state.plan_id,
        "event": state.event,
        "planner_input": planner_input,
        "raw_plan": raw_plan,
        "validated_plan": validated_plan,
        "executed_agents": execution_result.get("executed_agents", []),
        "results": state.get_all_results(),
        "failed_agents": list(state.failed_agents),
        "execution_trace": list(state.trace),
        **_reasoning_mode_response(state),
    }


def _reasoning_mode_response(state: AgentState) -> dict:
    reasoning = state.metadata.get("reasoning_mode", {})
    return {
        "selected_reasoning_mode": reasoning.get("selected_reasoning_mode"),
        "reasoning_mode_reason": reasoning.get("reasoning_mode_reason", []),
        "recommended_execution_policy": reasoning.get("recommended_execution_policy", {}),
    }


def _build_runtime_registry() -> dict:
    registry = dict(AGENT_REGISTRY)
    registry["decision"] = _run_decision_from_dynamic_results
    return registry


def _run_decision_from_dynamic_results(payload: dict) -> dict:
    results = payload.get("results", {})
    writer_v2_result = results.get("writer_v2", {})
    decision_payload = {
        "event": payload.get("event", ""),
        "second_draft": payload.get("second_draft") or writer_v2_result.get("statement", ""),
        "sentiment_analysis": results.get("sentiment", {}),
        "redteam_review": results.get("redteam", {}),
        "legal_review": results.get("legal", {}),
    }
    return decision_agent.run(decision_payload)


def _infer_category(event: str) -> str:
    if any(term in event for term in ("食品", "过期", "原料", "生产")):
        return "food_safety"
    if any(term in event for term in ("数据", "隐私", "泄露", "用户信息", "App")):
        return "data_privacy"
    if any(term in event for term in ("违法", "监管", "赔偿", "责任", "合规")):
        return "legal_risk"
    return "general"


def _infer_risk_level(event: str) -> str:
    if any(term in event for term in ("监管", "泄露", "过期", "抵制", "热搜", "违法")):
        return "high"
    if any(term in event for term in ("质疑", "投诉", "网友", "传播", "舆情", "担心")):
        return "medium"
    return "low"
