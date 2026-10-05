from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from backend.agents import decision_agent, legal_agent, redteam_agent, sentiment_agent, writer_agent
from backend.core.adapter import build_agent_input
from backend.core.human_fact_runtime import pause_for_claim
from backend.core.state import AgentState
from backend.llm.client import get_last_llm_trace, get_llm_trace_calls, reset_last_llm_trace
from backend.harness.spec import harness_trace_reference
from backend.core.harness_runtime import get_runtime_context
from backend.core.context_pack_runtime import ContextPackRuntimeProvider, inject_context_pack
from backend.core.trace_safety import (
    context_pack_trace_metadata,
    sanitize_trace_metadata,
    summarize_skill_trace,
    summarize_trace_input,
    summarize_trace_output,
)
from backend.skills.skill_selector import SkillSelector


AgentRunner = Callable[[dict], dict]
_CONTEXT_PACK_PROVIDER = ContextPackRuntimeProvider()
_SKILL_SELECTOR = SkillSelector()
AGENT_REGISTRY: dict[str, AgentRunner] = {
    "sentiment": sentiment_agent.run,
    "writer": writer_agent.run,
    "writer_v2": writer_agent.generate_second_draft,
    "redteam": redteam_agent.run,
    "legal": legal_agent.run,
    "decision": decision_agent.run,
}


def execute(plan: dict, state, agent_registry: dict[str, AgentRunner] | None = None,
            *, checkpoint: Callable[[AgentState], object] | None = None,
            skip_completed: bool = False) -> dict:
    registry = agent_registry or AGENT_REGISTRY
    plan_id = plan.get("plan_id")
    agent_state = _ensure_state(plan_id, state)
    runtime_context = get_runtime_context(agent_state)
    if runtime_context is not None:
        agent_state.metadata.setdefault("harness_runtime_context", runtime_context.trace_metadata())
    executed_agents = []

    items = plan.get("plan", [])
    for position, item in enumerate(items):
        agent_name = item.get("agent")
        if skip_completed and agent_state.get_result(agent_name) is not None:
            executed_agents.append(agent_name)
            continue
        reason = item.get("reason", "")
        agent_state.current_agent = agent_name
        start_time = _now_iso()
        monotonic_start = perf_counter()
        context_pack = None

        if agent_name not in registry:
            error = "Agent is not registered."
            agent_state.mark_failed(agent_name, error)
            trace_item = _build_trace_item(agent_name, reason, start_time, _now_iso(), "failed", None, error)
            trace_item["duration_ms"] = _elapsed_ms(monotonic_start)
            agent_state.add_trace(trace_item)
            continue

        try:
            reset_last_llm_trace()
            payload = build_agent_input(agent_name, agent_state, runtime_context=runtime_context)
            if runtime_context is not None:
                context_pack = _CONTEXT_PACK_PROVIDER.build_for_agent(agent_state, agent_name)
                payload = inject_context_pack(payload, context_pack)
                skill_run = _SKILL_SELECTOR.select_and_execute(agent_state, agent_name, payload)
                payload["skill_results"] = deepcopy(skill_run)
            output = registry[agent_name](_adapt_payload_for_runner(agent_name, payload))
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            agent_state.mark_failed(agent_name, error)
            trace_item = _build_trace_item(agent_name, reason, start_time, _now_iso(), "failed", None, error)
            trace_item["duration_ms"] = _elapsed_ms(monotonic_start)
            trace_item.update(_collect_llm_metadata())
            if context_pack:
                trace_item["context_pack"] = context_pack_trace_metadata(context_pack)
            if runtime_context is not None:
                trace_item.update(runtime_context.trace_metadata())
            agent_state.add_trace(trace_item)
            continue

        executed_agents.append(agent_name)
        output_metadata = _extract_result_metadata(output)
        clean_output = _strip_result_metadata(output)
        agent_state.set_result(agent_name, clean_output)
        if agent_name == "legal" and isinstance(output_metadata.get("claim_extraction"), dict):
            agent_state.metadata["legal_claim_extraction"] = deepcopy(output_metadata["claim_extraction"])
        if agent_name == "legal" and isinstance(output_metadata.get("claim_evidence_relation"), dict):
            agent_state.metadata["legal_claim_relation"] = deepcopy(output_metadata["claim_evidence_relation"])
        if agent_name == "legal" and isinstance(output_metadata.get("claim_coverage"), dict):
            agent_state.metadata["legal_claim_coverage"] = deepcopy(output_metadata["claim_coverage"])
        if agent_name == "legal" and isinstance(output_metadata.get("claim_action_recommendation"), dict):
            agent_state.metadata["legal_claim_action_recommendation"] = deepcopy(output_metadata["claim_action_recommendation"])
        if agent_name == "legal" and isinstance(output_metadata.get("legal_action_loop"), dict):
            agent_state.metadata["legal_action_loop"] = deepcopy(output_metadata["legal_action_loop"])
        if agent_name == "legal" and isinstance(output_metadata.get("targeted_legal_search"), dict):
            agent_state.metadata["legal_targeted_search"] = deepcopy(output_metadata["targeted_legal_search"])
        trace_item = _build_trace_item(agent_name, reason, start_time, _now_iso(), "success",
                                       summarize_trace_output(clean_output), None)
        trace_item["duration_ms"] = _elapsed_ms(monotonic_start)
        trace_item.update(sanitize_trace_metadata(_collect_trace_metadata(agent_name, output_metadata)))
        if runtime_context is not None:
            trace_item.update(runtime_context.trace_metadata())
        context_ref = (agent_state.metadata.get("context_pack_refs") or {}).get(agent_name)
        if runtime_context is not None and context_ref:
            snapshots = agent_state.metadata.get("context_pack_snapshots") or {}
            pack = snapshots.get(agent_name)
            trace_item["context_pack"] = {
                **deepcopy(context_ref),
                **(context_pack_trace_metadata(pack) if isinstance(pack, dict) else {}),
            }
            trace_item["skills"] = summarize_skill_trace(
                (agent_state.metadata.get("skill_runtime_results") or {}).get(agent_name, {})
            )
        agent_state.add_trace(trace_item)
        paused = agent_name == "legal" and pause_for_claim(agent_state, items[position + 1:])
        agent_state.current_agent = None
        if checkpoint is not None:
            # A remote call completed before this checkpoint can be repeated after a crash.
            checkpoint(agent_state)
        if paused:
            break
    agent_state.current_agent = None
    _safe_run_metrics(agent_state)
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
    calls = get_llm_trace_calls()
    return {"llm": deepcopy(llm_trace), "llm_calls": calls}


def _extract_result_metadata(output) -> dict:
    if isinstance(output, dict) and isinstance(output.get("_metadata"), dict):
        return deepcopy(output["_metadata"])
    return {}


def _strip_result_metadata(output):
    if not isinstance(output, dict) or "_metadata" not in output:
        return output
    clean_output = dict(output)
    clean_output.pop("_metadata", None)
    return clean_output


def _collect_trace_metadata(agent_name: str | None, result_metadata: dict) -> dict:
    trace_metadata = {}
    llm_calls = get_llm_trace_calls()
    if llm_calls:
        trace_metadata["llm_calls"] = llm_calls
    if isinstance(result_metadata.get("llm"), dict):
        trace_metadata["llm"] = deepcopy(result_metadata["llm"])
    else:
        trace_metadata.update(_collect_llm_metadata())

    if isinstance(result_metadata.get("rag"), dict):
        trace_metadata["rag"] = deepcopy(result_metadata["rag"])
    else:
        trace_metadata.update(_collect_agent_metadata(agent_name))
    if isinstance(result_metadata.get("retrieval_calls"), list):
        trace_metadata["retrieval_calls"] = deepcopy(result_metadata["retrieval_calls"])
    if agent_name == "legal" and isinstance(result_metadata.get("claim_extraction"), dict):
        trace_metadata["rag"] = {
            **trace_metadata.get("rag", {}),
            **deepcopy(result_metadata["claim_extraction"]),
        }
    if agent_name == "legal" and isinstance(result_metadata.get("claim_evidence_relation"), dict):
        trace_metadata["rag"] = {
            **trace_metadata.get("rag", {}),
            **deepcopy(result_metadata["claim_evidence_relation"]),
        }
    if agent_name == "legal" and isinstance(result_metadata.get("claim_coverage"), dict):
        trace_metadata["rag"] = {
            **trace_metadata.get("rag", {}),
            **deepcopy(result_metadata["claim_coverage"]),
        }
    if agent_name == "legal" and isinstance(result_metadata.get("claim_action_recommendation"), dict):
        trace_metadata["rag"] = {
            **trace_metadata.get("rag", {}),
            **deepcopy(result_metadata["claim_action_recommendation"]),
        }
    if agent_name == "legal" and isinstance(result_metadata.get("targeted_legal_search"), dict):
        trace_metadata["rag"] = {
            **trace_metadata.get("rag", {}),
            **deepcopy(result_metadata["targeted_legal_search"]),
        }
    if agent_name == "legal" and isinstance(result_metadata.get("legal_action_loop"), dict):
        trace_metadata["legal_action_loop"] = deepcopy(result_metadata["legal_action_loop"])
    return sanitize_trace_metadata(trace_metadata)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(start: float) -> float:
    return round(max(0.0, (perf_counter() - start) * 1000), 3)


def _safe_run_metrics(state: AgentState) -> dict | None:
    try:
        from backend.observability.run_metrics import build_run_metrics

        metrics = build_run_metrics(state.session_id, state.trace, state.status, state.approval)
        state.metadata["run_metrics"] = metrics
        return deepcopy(metrics)
    except Exception:
        # Instrumentation must never change workflow outcome.
        return None
