from backend.agents import planner_agent
from backend.core.agent_loop import _build_loop_result, _build_planner_input, _record_loop_trace
from backend.core.checkpoint import CHECKPOINT_PATH, load_checkpoint, save_checkpoint
from backend.core.executor import execute
from backend.core.human import request_review
from backend.core.plan_validator import validate_plan
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, FAILED, RUNNING, WAITING_HUMAN


def resume_agent_loop(
    session_id: str,
    max_iterations: int = 2,
    checkpoint_path=CHECKPOINT_PATH,
    planner=None,
    validator=None,
    executor=None,
    evaluator=None,
    policy=None,
    agent_registry: dict | None = None,
) -> dict:
    if max_iterations <= 0:
        raise ValueError("max_iterations must be greater than 0.")

    state = load_checkpoint(session_id, checkpoint_path)
    if state is None:
        return {
            "session_id": session_id,
            "status": "error",
            "state": None,
            "stopped_reason": "checkpoint_not_found",
            "error": f"Checkpoint not found for session_id: {session_id}",
        }

    decision = state.approval.get("decision")
    if decision == "rejected":
        state.status = FAILED
        save_checkpoint(state, checkpoint_path)
        return _build_loop_result(
            state=state,
            iterations=[],
            status="failed",
            stopped_reason="human_rejected",
        )

    if not _is_approved_for_resume(state.status, decision):
        return _build_loop_result(
            state=state,
            iterations=[],
            status="waiting_human",
            stopped_reason="human_approval_required",
        )

    planner = planner or planner_agent.run
    validator = validator or validate_plan
    executor = executor or execute
    evaluator = evaluator or evaluate_runtime_state
    policy = policy or _approved_resume_policy

    state.status = RUNNING
    state.approval["required"] = False
    planner_input = state.metadata.get("planner_input") or _build_planner_input(state.event)
    state.metadata["planner_input"] = planner_input

    result = _continue_agent_loop(
        state=state,
        planner_input=planner_input,
        max_iterations=max_iterations,
        planner=planner,
        validator=validator,
        executor=executor,
        evaluator=evaluator,
        policy=policy,
        agent_registry=agent_registry,
    )
    save_checkpoint(state, checkpoint_path)
    return result


def _continue_agent_loop(
    state,
    planner_input: dict,
    max_iterations: int,
    planner,
    validator,
    executor,
    evaluator,
    policy,
    agent_registry: dict | None,
) -> dict:
    iterations = []
    start_iteration = _next_iteration_number(state)

    for offset in range(max_iterations):
        iteration = start_iteration + offset
        state.status = RUNNING
        raw_plan = planner(planner_input)
        validated_plan = validator(raw_plan)
        state.plan_id = validated_plan.get("plan_id", state.plan_id)

        execution_result = executor(
            validated_plan,
            state,
            agent_registry=agent_registry,
        )
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


def _is_approved_for_resume(status: str, decision: str | None) -> bool:
    return decision == "approved" and status in {WAITING_HUMAN, RUNNING}


def _approved_resume_policy(state, evaluation: dict) -> dict:
    if state.approval.get("decision") == "approved":
        return {"required": False, "reason": "", "triggers": []}
    return evaluate_human_policy(state, evaluation)


def _next_iteration_number(state) -> int:
    existing_iterations = [
        item.get("output", {}).get("iteration")
        for item in state.trace
        if item.get("agent") == "agent_loop"
    ]
    numeric_iterations = [item for item in existing_iterations if isinstance(item, int)]
    return max(numeric_iterations, default=0) + 1
