from uuid import uuid4

from backend.agents.decision_agent import run as run_decision_agent
from backend.agents.legal_agent import run as run_legal_agent
from backend.agents.redteam_agent import run as run_redteam_agent
from backend.agents.sentiment_agent import run as run_sentiment_agent
from backend.agents.writer_agent import generate_first_draft, generate_second_draft
from backend.schemas import AgentTraceItem, CrisisRunRequest, CrisisRunResponse, ScoreBundle
from backend.storage import save_session


def _append_trace(
    trace: list[AgentTraceItem],
    agent: str,
    name: str,
    agent_input: object,
    agent_output: object,
) -> None:
    trace.append(
        AgentTraceItem(
            agent=agent,
            name=name,
            input=agent_input,
            output=agent_output,
        )
    )


def run_crisis_workflow(request: CrisisRunRequest) -> CrisisRunResponse:
    session_id = str(uuid4())
    trace: list[AgentTraceItem] = []

    sentiment_output = run_sentiment_agent(request.event)
    _append_trace(trace, "Agent A", "舆情分析 Agent", request.event, sentiment_output)

    first_draft_input = {
        "event": request.event,
        "sentiment_analysis": sentiment_output,
    }
    first_draft_output = generate_first_draft(first_draft_input)
    _append_trace(
        trace,
        "Agent C",
        "策略文案 Agent（第一版）",
        first_draft_input,
        first_draft_output,
    )

    redteam_input = {
        "event": request.event,
        "draft": first_draft_output["statement"],
    }
    redteam_output = run_redteam_agent(redteam_input)
    _append_trace(trace, "Agent D", "红队攻击 Agent", redteam_input, redteam_output)

    legal_input = {
        "event": request.event,
        "draft": first_draft_output["statement"],
        "redteam_review": redteam_output,
    }
    legal_output = run_legal_agent(legal_input)
    _append_trace(trace, "Agent B", "合规审查 Agent", legal_input, legal_output)

    second_draft_input = {
        "event": request.event,
        "first_draft": first_draft_output,
        "redteam_review": redteam_output,
        "legal_review": legal_output,
    }
    second_draft_output = generate_second_draft(second_draft_input)
    _append_trace(
        trace,
        "Agent C",
        "策略文案 Agent（第二版）",
        second_draft_input,
        second_draft_output,
    )

    decision_input = {
        "event": request.event,
        "second_draft": second_draft_output["statement"],
        "sentiment_analysis": sentiment_output,
        "redteam_review": redteam_output,
        "legal_review": legal_output,
    }
    decision_output = run_decision_agent(decision_input)
    _append_trace(trace, "Agent E", "最终决策 Agent", decision_input, decision_output)

    response = CrisisRunResponse(
        session_id=session_id,
        final_statement=decision_output["final_statement"],
        scores=ScoreBundle(**decision_output["scores"]),
        agent_trace=trace,
    )

    save_session(session_id, response.model_dump())
    return response
