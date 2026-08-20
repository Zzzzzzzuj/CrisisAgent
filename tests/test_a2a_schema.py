from backend.skills.a2a_schema import AgentMessage, explain_a2a_vs_mcp


def test_agent_message_serializes_required_a2a_fields():
    message = AgentMessage(
        from_agent="planner",
        to_agent="legal_agent",
        task_type="legal_review",
        payload={"event": "食品安全事件"},
        trace_id="trace-1",
        session_id="session-1",
        requires_ack=True,
    )

    data = message.to_dict()

    assert data["message_id"]
    assert data["from_agent"] == "planner"
    assert data["to_agent"] == "legal_agent"
    assert data["requires_ack"] is True
    assert data["created_at"]


def test_a2a_vs_mcp_explanation_distinguishes_protocol_roles():
    explanation = explain_a2a_vs_mcp()

    assert "tool" in explanation["mcp"]
    assert "agent" in explanation["a2a"].lower()
    assert "AgentState" in explanation["crisisagent_mapping"]
