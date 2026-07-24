from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from backend.agents import decision_agent, legal_agent, redteam_agent, sentiment_agent, writer_agent
from backend.config import get_config
from backend.schemas import AgentTraceItem, CrisisRunRequest, CrisisRunResponse, ScoreBundle, ToolTraceItem
from backend.storage import save_session


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
            input=tool_info.get("input"),
            output=tool_info.get("output"),
            success=bool(tool_info.get("success")),
            duration_ms=float(tool_info.get("duration_ms", 0.0)),
        )
    ]


def _record_step(
    trace: list[AgentTraceItem],
    agent: str,
    name: str,
    agent_input: object,
    runner,
    mock_runner=None,
    requested_mode: str = "mock",
):
    start_time = _now_iso()
    output = runner(agent_input)
    end_time = _now_iso()

    fallback_candidate = False
    if requested_mode == "llm" and mock_runner is not None:
        fallback_candidate = output == mock_runner(deepcopy(agent_input))

    mode, fallback, status = _resolve_mode_and_fallback(requested_mode, fallback_candidate)
    rag = legal_agent.get_last_rag_info() if agent == "Agent B" else None
    memory = writer_agent.get_last_memory_info() if agent == "Agent C" and requested_mode == "llm" else None
    context = writer_agent.get_last_context_info() if agent == "Agent C" and requested_mode == "llm" else None
    tools = _get_agent_tools(agent)
    _append_trace(
        trace,
        agent,
        name,
        agent_input,
        output,
        start_time,
        end_time,
        mode,
        fallback,
        status,
        rag,
        memory,
        context,
        tools,
    )
    return output


def run_crisis_workflow(request: CrisisRunRequest) -> CrisisRunResponse:
    session_id = str(uuid4())
    trace: list[AgentTraceItem] = []
    requested_mode = get_config().agent_mode

    sentiment_output = _record_step(
        trace=trace,
        agent="Agent A",
        name="舆情分析 Agent",
        agent_input=request.event,
        runner=sentiment_agent.run,
        mock_runner=sentiment_agent._run_mock,
        requested_mode=requested_mode,
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
    )

    legal_input = {
        "event": request.event,
        "draft": first_draft_output["statement"],
        "redteam_review": redteam_output,
    }
    legal_output = _record_step(
        trace=trace,
        agent="Agent B",
        name="合规审查 Agent",
        agent_input=legal_input,
        runner=legal_agent.run,
        mock_runner=legal_agent._run_mock,
        requested_mode=requested_mode,
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
    )

    response = CrisisRunResponse(
        session_id=session_id,
        final_statement=decision_output["final_statement"],
        scores=ScoreBundle(**decision_output["scores"]),
        agent_trace=trace,
    )

    save_session(session_id, response.model_dump())
    return response
