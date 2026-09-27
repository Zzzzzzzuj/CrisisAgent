"""Durable, fail-closed continuation for a human fact response."""

from copy import deepcopy
from threading import Lock

from backend.core.checkpoint import load_checkpoint, save_checkpoint
from backend.core.dynamic_runtime import _build_runtime_registry, build_dynamic_result
from backend.core.executor import execute
from backend.core.human import request_review
from backend.core.human_fact_runtime import (
    FACT_INPUT,
    FACT_KEY,
    FINAL_REVIEW,
    PHASE_COMPLETED,
    PHASE_CONTINUING,
    PHASE_RESPONSE_RECORDED,
    record_action,
    record_response,
    revision_is_safe,
)
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, FAILED, REJECTED, RUNNING, WAITING_HUMAN


# This prevents duplicate continuations within one API process. The JSON checkpoint
# repository does not provide a cross-process compare-and-swap transaction.
_RESPONSE_LOCK = Lock()


def submit_human_fact_response(session_id: str, response: dict) -> dict:
    with _RESPONSE_LOCK:
        state = load_checkpoint(session_id)
        if state is None:
            raise LookupError("Dynamic session not found.")
        fact = state.metadata.get(FACT_KEY)
        if state.metadata.get("human_wait_type") != FACT_INPUT or not isinstance(fact, dict):
            raise ValueError("Session is not waiting for a human fact response.")

        normalized = _normalize_response(response)
        if fact.get("response") is None:
            record_response(state, normalized)
            save_checkpoint(state)
        else:
            if not _same_response(fact.get("response"), normalized):
                raise ValueError("A different response was already recorded for this request.")
            if fact.get("phase") not in {PHASE_RESPONSE_RECORDED, PHASE_CONTINUING}:
                raise ValueError("Human fact continuation is no longer resumable.")

        return _continue_saved_response(state)


def _continue_saved_response(state) -> dict:
    fact = state.metadata[FACT_KEY]
    request = fact["request"]
    response = fact["response"]
    fact["phase"] = PHASE_CONTINUING
    save_checkpoint(state)

    if response["response_type"] == "FACT_PROVIDED":
        _record_action_once(state, 1, "STOP", "human_asserted_fact_requires_review",
                            {"case_fact_status": "unresolved", "verification_status": "human_asserted"})
        return _finish_for_review(state, "human_asserted_fact_requires_review")

    if not _valid_resume_cursor(fact.get("remaining_plan")):
        _record_action_once(state, 1, "STOP", "resume_cursor_invalid", {"unsupported_claim_removed": False})
        return _finish_for_review(state, "resume_cursor_invalid")

    remaining = fact["remaining_plan"]
    writer_result = state.get_result("writer_v2")
    if writer_result is None:
        if fact.get("revision_attempted"):
            _record_action_once(state, 2, "STOP", "revision_interrupted_without_saved_result",
                                {"unsupported_claim_removed": False})
            return _finish_for_review(state, "revision_interrupted_without_saved_result")
        fact["revision_attempted"] = True
        _record_action_once(state, 1, "REVISE_UNVERIFIED_CLAIM",
                            "human_fact_unavailable_requires_safe_revision", fact["observation"])
        save_checkpoint(state)
        execute(_single_step_plan(state, remaining[0]), state, agent_registry=_build_runtime_registry())
        save_checkpoint(state)
        writer_result = state.get_result("writer_v2")

    if not isinstance(writer_result, dict):
        _record_action_once(state, 2, "STOP", "revision_failed", {"unsupported_claim_removed": False})
        return _finish_for_review(state, "revision_failed")

    statement = str(writer_result.get("statement", ""))
    if not revision_is_safe(request["claim"], statement):
        _record_action_once(state, 2, "STOP", "unsupported_claim_remains_after_revision",
                            {"unsupported_claim_removed": False})
        return _finish_for_review(state, "unsupported_claim_remains_after_revision")
    _record_action_once(state, 2, "CONTINUE", "unsupported_claim_removed",
                        {"unsupported_claim_removed": True})
    save_checkpoint(state)

    decision_result = state.get_result("decision")
    if decision_result is None:
        if fact.get("decision_attempted"):
            _record_action_once(state, 3, "STOP", "decision_interrupted_without_saved_result",
                                {"decision_completed": False})
            return _finish_for_review(state, "decision_interrupted_without_saved_result")
        fact["decision_attempted"] = True
        save_checkpoint(state)
        decision_step = next((step for step in remaining if step.get("agent") == "decision"), None)
        if decision_step is None:
            return _finish_for_review(state, "resume_cursor_invalid")
        execute(_single_step_plan(state, decision_step), state, agent_registry=_build_runtime_registry())
        save_checkpoint(state)
        decision_result = state.get_result("decision")
    if not isinstance(decision_result, dict):
        _record_action_once(state, 3, "STOP", "decision_failed", {"decision_completed": False})
        return _finish_for_review(state, "decision_failed")

    evaluation = evaluate_runtime_state(state)
    policy = evaluate_human_policy(state, evaluation)
    state.metadata["evaluation"] = evaluation
    state.metadata["policy"] = policy
    if policy.get("required"):
        return _finish_for_review(state, policy.get("reason", "Human review required."),
                                  policy=policy, evaluation=evaluation)

    state.set_status(COMPLETED)
    state.metadata.pop("human_wait_type", None)
    fact["phase"] = PHASE_COMPLETED
    save_checkpoint(state)
    return _result(state, "unsupported_claim_removed")


def _finish_for_review(state, reason: str, policy: dict | None = None, evaluation: dict | None = None) -> dict:
    request_review(state, f"Human review required: {reason}", policy_result=policy, evaluation=evaluation)
    state.metadata["human_wait_type"] = FINAL_REVIEW
    state.metadata[FACT_KEY]["phase"] = PHASE_COMPLETED
    save_checkpoint(state)
    return _result(state, reason)


def _record_action_once(state, round_index: int, action: str, reason: str, observation: dict) -> None:
    fact = state.metadata[FACT_KEY]
    request_id = fact["request"]["request_id"]
    if any(item.get("agent") == "human_fact" and item.get("request_id") == request_id
           and item.get("action") == action and item.get("reason") == reason for item in state.trace):
        return
    record_action(state, round_index, action, reason, observation)
    save_checkpoint(state)


def _single_step_plan(state, step: dict) -> dict:
    return {"plan_id": state.plan_id, "plan": [deepcopy(step)]}


def _valid_resume_cursor(plan) -> bool:
    return (isinstance(plan, list) and bool(plan) and isinstance(plan[0], dict)
            and plan[0].get("agent") == "writer_v2"
            and any(isinstance(step, dict) and step.get("agent") == "decision" for step in plan))


def _normalize_response(response: dict) -> dict:
    if not isinstance(response, dict):
        raise ValueError("Response must be an object.")
    request_id = response.get("request_id")
    response_type = response.get("response_type")
    fact_text = response.get("fact_text", "")
    if not isinstance(request_id, str) or not isinstance(response_type, str):
        raise ValueError("request_id and response_type must be strings.")
    if response_type not in {"FACT_PROVIDED", "FACT_UNAVAILABLE"}:
        raise ValueError("response_type must be FACT_PROVIDED or FACT_UNAVAILABLE.")
    if not isinstance(fact_text, str) or (response_type == "FACT_PROVIDED" and not fact_text.strip()):
        raise ValueError("FACT_PROVIDED requires non-empty fact_text.")
    return {"request_id": request_id, "response_type": response_type,
            "fact_text": fact_text.strip() if response_type == "FACT_PROVIDED" else ""}


def _same_response(saved: dict, incoming: dict) -> bool:
    return all(saved.get(key, "") == incoming.get(key, "") for key in ("request_id", "response_type", "fact_text"))


def _result(state, reason: str) -> dict:
    status = {
        WAITING_HUMAN: "waiting_human",
        COMPLETED: "completed",
        REJECTED: "rejected",
        FAILED: "failed",
        RUNNING: "running",
    }.get(state.status, str(state.status).lower())
    return {**build_dynamic_result(state), "status": status, "state_status": state.status,
            "approval": deepcopy(state.approval), "human_fact_request": deepcopy(state.metadata[FACT_KEY]["request"]),
            "observation": deepcopy(state.metadata[FACT_KEY]["observation"]),
            "evaluation": deepcopy(state.metadata.get("evaluation")),
            "policy": deepcopy(state.metadata.get("policy")), "stopped_reason": reason}
