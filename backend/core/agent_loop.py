from uuid import uuid4

from backend.agents import planner_agent
from backend.core.dynamic_runtime import _infer_category, _infer_risk_level
from backend.core.executor import execute
from backend.core.guardrail_runtime import apply_guardrails_to_state
from backend.core.human import request_review
from backend.core.plan_validator import validate_plan
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, FAILED, RUNNING, AgentState


def run_agent_loop(
    event: str,
    max_iterations: int = 2,
    planner=None,
    validator=None,
    executor=None,
    evaluator=None,
    policy=None,
    agent_registry: dict | None = None,
) -> dict:
    if max_iterations <= 0:
        raise ValueError("max_iterations must be greater than 0.")

    planner = planner or planner_agent.run
    validator = validator or validate_plan
    executor = executor or execute
    evaluator = evaluator or evaluate_runtime_state
    policy = policy or evaluate_human_policy
    planner_input = _build_planner_input(event)
    state = AgentState(
        session_id=str(uuid4()),
        plan_id="",
        event=event,
        metadata={"planner_input": planner_input},
    )
    iterations = []

    for iteration in range(1, max_iterations + 1):
        state.status = RUNNING
        raw_plan = planner(planner_input)
        validated_plan = validator(raw_plan)
        state.plan_id = validated_plan.get("plan_id", state.plan_id)

        execution_result = executor(
            validated_plan,
            state,
            agent_registry=agent_registry,
        )
        apply_guardrails_to_state(state)
        evaluation = evaluator(state)
        policy_result = policy(state, evaluation)
        _record_loop_trace(state, iteration, evaluation)

        iteration_result = {
            "iteration": iteration,
            "raw_plan": raw_plan,
            "validated_plan": validated_plan,
            "execution_result": execution_result,
            "evaluation": evaluation,
            "policy": policy_result,
        }
        iterations.append(iteration_result)

        if policy_result.get("required"):
            request_review(state, policy_result.get("reason", "Human review required."))
            return _build_loop_result(
                state=state,
                iterations=iterations,
                status="waiting_human",
                stopped_reason="human_review_required",
            )

        if evaluation.get("passed"):
            state.status = COMPLETED
            return _build_loop_result(
                state=state,
                iterations=iterations,
                status="completed",
                stopped_reason="evaluation_passed",
            )

        state.metadata["last_evaluation_issues"] = list(evaluation.get("issues", []))

    state.status = FAILED
    return _build_loop_result(
        state=state,
        iterations=iterations,
        status="failed",
        stopped_reason="max_iterations_reached",
    )


def _build_planner_input(event: str) -> dict:
    return {
        "event": event,
        "category": _infer_category(event),
        "risk_level": _infer_risk_level(event),
    }


def _record_loop_trace(state: AgentState, iteration: int, evaluation: dict) -> None:
    state.add_trace(
        {
            "agent": "agent_loop",
            "reason": f"Runtime evaluation for iteration {iteration}.",
            "start_time": None,
            "end_time": None,
            "status": "success" if evaluation.get("passed") else "failed",
            "output": {
                "iteration": iteration,
                "evaluation": evaluation,
            },
            "error": None if evaluation.get("passed") else "; ".join(evaluation.get("issues", [])),
        }
    )


def _build_loop_result(
    state: AgentState,
    iterations: list[dict],
    status: str,
    stopped_reason: str,
) -> dict:
    return {
        "session_id": state.session_id,
        "plan_id": state.plan_id,
        "event": state.event,
        "status": status,
        "state": state.to_context(),
        "state_status": state.status,
        "approval": dict(state.approval),
        "stopped_reason": stopped_reason,
        "iterations": iterations,
        "results": state.get_all_results(),
        "failed_agents": list(state.failed_agents),
        "execution_trace": list(state.trace),
    }
