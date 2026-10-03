"""Durable, fail-closed continuation for a human fact response."""

from copy import deepcopy
from threading import Lock

from backend.agents.legal_claim_relation import build_legal_claim_relations
from backend.agents.legal_targeted_search import run_legal_action_loop
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
    pause_for_claim_index,
    revision_is_safe,
)
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, FAILED, REJECTED, RUNNING, WAITING_HUMAN
from backend.rag.retriever import retrieve


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


def record_human_fact_response_for_async(session_id: str, response: dict) -> dict:
    """Persist a human response before scheduling the continuation worker."""
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
        elif not _same_response(fact.get("response"), normalized):
            raise ValueError("A different response was already recorded for this request.")
        elif fact.get("phase") not in {PHASE_RESPONSE_RECORDED, PHASE_CONTINUING}:
            raise ValueError("Human fact continuation is no longer resumable.")

        return {
            "session_id": session_id,
            "status": "queued",
            "state_status": state.status,
            "response_recorded": True,
        }


def _continue_saved_response(state) -> dict:
    fact = state.metadata[FACT_KEY]
    request = fact["request"]
    response = fact["response"]
    fact["phase"] = PHASE_CONTINUING
    save_checkpoint(state)

    if not fact.get("legal_resume_completed"):
        try:
            stop_reason = _resume_legal_loop(state)
        except Exception:
            return _finish_for_review(state, "legal_loop_resume_error")
        if stop_reason == "human_fact_required" and state.metadata.get("human_wait_type") == FACT_INPUT:
            return _result(state, stop_reason)
        if stop_reason not in {"no_information_gain", "fact_unavailable_requires_safe_revision",
                               "human_asserted_fact_requires_review"}:
            return _finish_for_review(state, stop_reason)

    if (response["response_type"] == "FACT_PROVIDED"
            or _has_human_asserted_history(state)):
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
    _update_legal_loop(state, PHASE_COMPLETED, "STOP_UNRESOLVED", "fact_unavailable_safely_revised")
    save_checkpoint(state)
    return _result(state, "unsupported_claim_removed")


def _finish_for_review(state, reason: str, policy: dict | None = None, evaluation: dict | None = None) -> dict:
    request_review(state, f"Human review required: {reason}", policy_result=policy, evaluation=evaluation)
    state.metadata["human_wait_type"] = FINAL_REVIEW
    state.metadata[FACT_KEY]["phase"] = PHASE_COMPLETED
    _update_legal_loop(state, FINAL_REVIEW, "STOP_UNRESOLVED", reason)
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


def _update_legal_loop(state, phase: str, next_action: str, stop_reason: str) -> None:
    loop = state.metadata.get("legal_action_loop")
    if not isinstance(loop, dict):
        return
    loop["phase"] = phase
    loop["next_action"] = next_action
    loop["stop_reason"] = stop_reason


def _resume_legal_loop(state) -> str:
    fact = state.metadata[FACT_KEY]
    request = fact["request"]
    loop = state.metadata.get("legal_action_loop")
    extraction = state.metadata.get("legal_claim_extraction")
    if not isinstance(loop, dict) or not isinstance(loop.get("cursor"), dict) or not isinstance(extraction, dict):
        return "legal_loop_cursor_invalid"
    response = fact["response"]
    observation = fact["observation"]
    human_observation = {
        "observation_type": "fact_provided" if response["response_type"] == "FACT_PROVIDED" else "fact_unavailable",
        "request_id": request["request_id"],
        "claim_index": request["claim_index"],
        "response_type": response["response_type"],
        "source": observation.get("source", "human_response"),
        "verification_status": observation.get("verification_status", "unresolved"),
        "availability": response["response_type"] == "FACT_PROVIDED",
        "whether_new_information": response["response_type"] == "FACT_PROVIDED",
        "claim_state_changed": False,
        "consumed": True,
    }
    spec = state.metadata.get("harness_spec") or {}
    policy = (spec.get("retrieval_policy") or {}).get("legal_action_loop") or {}
    from backend.agents import legal_agent

    old_action_count = len(loop.get("actions", []))
    result = run_legal_action_loop(
        extraction, loop.get("claim_coverage", {}), loop.get("claim_evidence_relation", {}),
        loop["cursor"].get("rag_info", {}), retrieve_call=retrieve,
        relation_call=build_legal_claim_relations, llm_call=legal_agent.call_llm,
        mode=loop["cursor"].get("mode", "mock"), event=state.event,
        risk_level=str((state.get_result("sentiment") or {}).get("risk_level", "unknown")),
        policy=policy, cursor=loop["cursor"], human_observation=human_observation,
    )
    waiting_for_next_fact = result["stop_reason"] == "human_fact_required"
    result["phase"] = "WAITING_HUMAN" if waiting_for_next_fact else "STOPPED"
    result["last_observation"] = deepcopy(loop.get("last_observation"))
    result["next_action"] = "REQUEST_HUMAN_FACT" if waiting_for_next_fact else "STOP_UNRESOLVED"
    state.metadata["legal_action_loop"] = result
    state.metadata["legal_claim_coverage"] = deepcopy(result.get("claim_coverage", {}))
    state.metadata["legal_claim_relation"] = deepcopy(result.get("claim_evidence_relation", {}))
    state.metadata["legal_claim_action_recommendation"] = deepcopy(result.get("claim_action_recommendation", {}))
    new_actions = result.get("actions", [])[old_action_count:]
    for index, action in enumerate(new_actions):
        before = action.get("before_legal_rule_status")
        after = action.get("after_legal_rule_status")
        state.add_trace({"agent": "legal", "status": "success", "phase": "resume",
                         "round": action.get("round_index"), "action": action.get("selected_action"),
                         "action_reason": action.get("stop_reason"),
                         "previous_observation_type": action.get("previous_observation_type"),
                         "previous_observation_changed_state": action.get("previous_observation_changed_state"),
                         "eligible_action_count": action.get("eligible_action_count"),
                         "proposal_action": action.get("proposal_action"),
                         "proposal_reason_code": action.get("proposal_reason_code"),
                         "proposal_target_claim_index": action.get("proposal_target_claim_index"),
                         "validator_allowed": action.get("validator_allowed"),
                         "validator_reason_code": action.get("validator_reason_code"),
                         "proposal_fallback_used": action.get("proposal_fallback_used"),
                         "observation_type": action.get("observation_type"),
                         "claim_state_changed": before is not None and after is not None and before != after,
                         "whether_new_information": action.get("whether_new_information"),
                         "next_action": (new_actions[index + 1].get("selected_action")
                                         if index + 1 < len(new_actions) else None),
                         "claim_index": action.get("claim_index"),
                         "tool_calls_used": action.get("tool_calls_used"),
                         "remaining_budget": action.get("remaining_budget"),
                         "remaining_claim_count": sum(
                             row.get("status") == "UNTOUCHED"
                             for row in result.get("claim_progress", []) if isinstance(row, dict)
                         )})
    if waiting_for_next_fact:
        gap = result.get("current_gap") or {}
        if not pause_for_claim_index(
            state, fact.get("remaining_plan", []), gap.get("claim_index"), replace_completed=True,
        ):
            result["phase"] = "STOPPED"
            result["next_action"] = "STOP_UNRESOLVED"
            result["stop_reason"] = "human_fact_request_invalid"
            state.metadata["legal_action_loop"] = result
            fact["legal_resume_completed"] = True
            save_checkpoint(state)
            return result["stop_reason"]
        save_checkpoint(state)
        return "human_fact_required"
    fact["legal_resume_completed"] = True
    save_checkpoint(state)
    return result["stop_reason"]


def _has_human_asserted_history(state) -> bool:
    loop = state.metadata.get("legal_action_loop")
    cursor = loop.get("cursor") if isinstance(loop, dict) else None
    actions = cursor.get("actions") if isinstance(cursor, dict) else None
    return any(
        isinstance(action, dict)
        and action.get("selected_action") == "HUMAN_FACT_RESPONSE"
        and action.get("observation_type") == "fact_provided"
        for action in (actions if isinstance(actions, list) else [])
    )
