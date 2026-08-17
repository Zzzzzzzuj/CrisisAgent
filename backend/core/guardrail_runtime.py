from backend.core.state import AgentState
from backend.guardrails import evaluate_input_guardrail, evaluate_output_guardrail


def apply_guardrails_to_state(state: AgentState) -> dict:
    guardrails = dict(state.metadata.get("guardrails", {}))
    guardrails["input"] = evaluate_input_guardrail(state.event)

    final_statement = _extract_final_statement(state)
    if final_statement:
        guardrails["output"] = evaluate_output_guardrail(final_statement)
    else:
        guardrails.setdefault("output", {"hit": False, "severity": "none", "issues": []})

    state.metadata["guardrails"] = guardrails
    return guardrails


def _extract_final_statement(state: AgentState) -> str:
    decision = state.get_result("decision") or {}
    if decision.get("final_statement"):
        return str(decision["final_statement"])
    writer_v2 = state.get_result("writer_v2") or {}
    if writer_v2.get("statement"):
        return str(writer_v2["statement"])
    return ""
