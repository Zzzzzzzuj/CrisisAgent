from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from backend.agents import decision_agent, legal_agent, redteam_agent, sentiment_agent, writer_agent
from backend.config import get_config
from backend.schemas import AgentTraceItem, CrisisRunRequest, CrisisRunResponse, ScoreBundle, ToolTraceItem
from backend.storage import save_session
from backend.harness.service import get_effective_harness_spec
from backend.core.state import AgentState
from backend.core.context_pack_runtime import ContextPackRuntimeProvider, inject_context_pack
from backend.core.trace_safety import (
    context_pack_trace_metadata,
    sanitize_trace_metadata,
    summarize_trace_input,
    summarize_trace_output,
)
from backend.skills.skill_selector import SkillSelector


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_mode_and_fallback(
    requested_mode: str,
    fallback_candidate: bool,
) -> tuple[str, bool, str]:
    if requested_mode == "llm" and fallback_candidate:
        return "llm", True, "fallback"
    return requested_mode, False, "success"


def _append_trace(
    trace: list[AgentTraceItem],
    agent: str,
    name: str,
    agent_input: object,
    agent_output: object,
    start_time: str,
    end_time: str,
    mode: str,
    fallback: bool,
    status: str,
    rag: dict | None = None,
    memory: dict | None = None,
    context: dict | None = None,
    tools: list[ToolTraceItem] | None = None,
    harness_spec: dict | None = None,
) -> None:
    trace.append(
        AgentTraceItem(
            agent=agent,
            name=name,
            input=agent_input,
            output=agent_output,
            start_time=start_time,
            end_time=end_time,
            status=status,
            mode=mode,
            fallback=fallback,
            rag=rag,
            memory=memory,
            context=context,
        tools=tools or [],
        )
    )


def _get_agent_tools(agent: str) -> list[ToolTraceItem]:
    if agent != "Agent A":
        return []

    tool_info = sentiment_agent.get_last_tool_info()
    if not tool_info.get("name"):
        return []

    return [
        ToolTraceItem(
            name=tool_info["name"],
            input=summarize_trace_input(tool_info.get("input")),
            output=tool_info.get("output"),
            success=bool(tool_info.get("success")),
            duration_ms=float(tool_info.get("duration_ms", 0.0)),
        )
    ]


def _strip_result_metadata(output):
    if not isinstance(output, dict) or "_metadata" not in output:
        return output
    clean = deepcopy(output)
    clean.pop("_metadata", None)
    return clean


def _record_step(
    trace: list[AgentTraceItem],
    agent: str,
    name: str,
    agent_input: object,
    runner,
    mock_runner=None,
    requested_mode: str = "mock",
    harness_spec: dict | None = None,
    runtime_state: AgentState | None = None,
):
    start_time = _now_iso()
    context_pack = None
    context_trace = None
    skill_run = None
    if runtime_state is not None:
        key = {"Agent B": "legal", "Agent D": "redteam", "Agent E": "decision"}.get(agent)
        if agent == "Agent C":
            key = "writer_v2" if "第二版" in name else "writer"
        context_pack = ContextPackRuntimeProvider().build_for_agent(runtime_state, key) if key else None
        if isinstance(agent_input, dict):
            agent_input = inject_context_pack(agent_input, context_pack)
            if key:
                skill_run = SkillSelector().select_and_execute(runtime_state, key, agent_input)
                agent_input["skill_results"] = deepcopy(skill_run)
    output = runner(agent_input)
    end_time = _now_iso()
    clean_output = _strip_result_metadata(output)
    if runtime_state is not None:
        runtime_state.set_result(key or agent, clean_output)

    fallback_candidate = False
    if requested_mode == "llm" and mock_runner is not None:
        fallback_candidate = clean_output == mock_runner(deepcopy(agent_input))

    mode, fallback, status = _resolve_mode_and_fallback(requested_mode, fallback_candidate)
    rag = legal_agent.get_last_rag_info() if agent == "Agent B" else None
    if agent == "Agent B" and isinstance(output, dict):
        claim_extraction = (output.get("_metadata") or {}).get("claim_extraction")
        if isinstance(claim_extraction, dict):
            rag = {**(rag or {}), **deepcopy(claim_extraction)}
            if runtime_state is not None:
                runtime_state.metadata["legal_claim_extraction"] = deepcopy(claim_extraction)
        claim_relation = (output.get("_metadata") or {}).get("claim_evidence_relation")
        if isinstance(claim_relation, dict):
            rag = {**(rag or {}), **deepcopy(claim_relation)}
            if runtime_state is not None:
                runtime_state.metadata["legal_claim_relation"] = deepcopy(claim_relation)
        claim_coverage = (output.get("_metadata") or {}).get("claim_coverage")
        if isinstance(claim_coverage, dict):
            rag = {**(rag or {}), **deepcopy(claim_coverage)}
            if runtime_state is not None:
                runtime_state.metadata["legal_claim_coverage"] = deepcopy(claim_coverage)
        recommendation = (output.get("_metadata") or {}).get("claim_action_recommendation")
        if isinstance(recommendation, dict):
            rag = {**(rag or {}), **deepcopy(recommendation)}
            if runtime_state is not None:
                runtime_state.metadata["legal_claim_action_recommendation"] = deepcopy(recommendation)
        targeted = (output.get("_metadata") or {}).get("targeted_legal_search")
        if isinstance(targeted, dict):
            rag = {**(rag or {}), **deepcopy(targeted)}
            if runtime_state is not None:
                runtime_state.metadata["legal_targeted_search"] = deepcopy(targeted)
    memory = writer_agent.get_last_memory_info() if agent == "Agent C" and requested_mode == "llm" else None
    context = writer_agent.get_last_context_info() if agent == "Agent C" and requested_mode == "llm" else None
    if context_pack is not None:
        context_trace = context_pack_trace_metadata(context_pack)
        context_trace.update({
            "selected_count": len(context_pack.get("selected_case_ids", [])),
            "dropped_count": len(context_pack.get("dropped_fields", [])),
        })
        if context is not None:
            context_trace.update(context)
    tools = _get_agent_tools(agent)
    _append_trace(
        trace,
        agent,
        name,
        summarize_trace_input(agent_input),
        summarize_trace_output(clean_output),
        start_time,
        end_time,
        mode,
        fallback,
        status,
        sanitize_trace_metadata(rag),
        memory,
        context_trace if context_trace is not None else context,
        tools,
        harness_spec,
    )
    return clean_output


def run_crisis_workflow(request: CrisisRunRequest) -> CrisisRunResponse:
    session_id = str(uuid4())
    trace: list[AgentTraceItem] = []
    requested_mode = get_config().agent_mode
    harness_spec = get_effective_harness_spec()
    runtime_state = AgentState(session_id=session_id, plan_id="fixed-workflow", event=request.event,
                               metadata={"harness_spec": deepcopy(harness_spec)})

    sentiment_output = _record_step(
        trace=trace,
        agent="Agent A",
        name="舆情分析 Agent",
        agent_input=request.event,
        runner=sentiment_agent.run,
        mock_runner=sentiment_agent._run_mock,
        requested_mode=requested_mode,
        harness_spec=harness_spec,
        runtime_state=runtime_state,
    )

    first_draft_input = {
        "event": request.event,
        "sentiment_analysis": sentiment_output,
    }
    first_draft_output = _record_step(
        trace=trace,
        agent="Agent C",
        name="策略文案 Agent（第一版）",
        agent_input=first_draft_input,
        runner=writer_agent.generate_first_draft,
        mock_runner=writer_agent._run_mock,
        requested_mode=requested_mode,
        harness_spec=harness_spec,
        runtime_state=runtime_state,
    )

    redteam_input = {
        "event": request.event,
        "draft": first_draft_output["statement"],
    }
    redteam_output = _record_step(
        trace=trace,
        agent="Agent D",
        name="红队攻击 Agent",
        agent_input=redteam_input,
        runner=redteam_agent.run,
        mock_runner=redteam_agent._run_mock,
        requested_mode=requested_mode,
        harness_spec=harness_spec,
        runtime_state=runtime_state,
    )

    legal_input = {
        "event": request.event,
        "draft": first_draft_output["statement"],
        "redteam_review": redteam_output,
        "sentiment_analysis": sentiment_output,
        "harness_spec": harness_spec,
    }
    legal_output = _record_step(
        trace=trace,
        agent="Agent B",
        name="合规审查 Agent",
        agent_input=legal_input,
        runner=legal_agent.run,
        mock_runner=legal_agent._run_mock,
        requested_mode=requested_mode,
        harness_spec=harness_spec,
        runtime_state=runtime_state,
    )

    second_draft_input = {
        "event": request.event,
        "first_draft": first_draft_output,
        "redteam_review": redteam_output,
        "legal_review": legal_output,
    }
    second_draft_output = _record_step(
        trace=trace,
        agent="Agent C",
        name="策略文案 Agent（第二版）",
        agent_input=second_draft_input,
        runner=writer_agent.generate_second_draft,
        mock_runner=None,
        requested_mode="mock",
        harness_spec=harness_spec,
        runtime_state=runtime_state,
    )

    decision_input = {
        "event": request.event,
        "second_draft": second_draft_output["statement"],
        "sentiment_analysis": sentiment_output,
        "redteam_review": redteam_output,
        "legal_review": legal_output,
    }
    decision_output = _record_step(
        trace=trace,
        agent="Agent E",
        name="最终决策 Agent",
        agent_input=decision_input,
        runner=decision_agent.run,
        mock_runner=decision_agent._run_mock,
        requested_mode=requested_mode,
        harness_spec=harness_spec,
        runtime_state=runtime_state,
    )

    response = CrisisRunResponse(
        session_id=session_id,
        final_statement=decision_output["final_statement"],
        scores=ScoreBundle(**decision_output["scores"]),
        agent_trace=trace,
    )

    saved_session = response.model_dump()
    saved_session["harness_spec"] = harness_spec
    saved_session["context_pack_snapshots"] = deepcopy(runtime_state.metadata.get("context_pack_snapshots", {}))
    saved_session["context_pack_refs"] = deepcopy(runtime_state.metadata.get("context_pack_refs", {}))
    saved_session["skill_runtime_results"] = deepcopy(runtime_state.metadata.get("skill_runtime_results", {}))
    saved_session["skill_selection"] = deepcopy(runtime_state.metadata.get("skill_selection", {}))
    saved_session["legal_claim_extraction"] = deepcopy(runtime_state.metadata.get("legal_claim_extraction", {}))
    saved_session["legal_claim_relation"] = deepcopy(runtime_state.metadata.get("legal_claim_relation", {}))
    saved_session["legal_claim_coverage"] = deepcopy(runtime_state.metadata.get("legal_claim_coverage", {}))
    saved_session["legal_claim_action_recommendation"] = deepcopy(runtime_state.metadata.get("legal_claim_action_recommendation", {}))
    saved_session["legal_targeted_search"] = deepcopy(runtime_state.metadata.get("legal_targeted_search", {}))
    save_session(session_id, saved_session)
    return response
