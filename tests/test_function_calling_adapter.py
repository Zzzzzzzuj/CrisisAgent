from backend.skills.function_calling_adapter import FunctionCallingAdapter, skill_to_openai_tool_schema
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill


def test_skill_to_openai_tool_schema_uses_function_shape():
    schema = skill_to_openai_tool_schema(_echo_skill())

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo_skill"
    assert schema["function"]["parameters"]["required"] == ["text"]


def test_function_calling_adapter_lists_tools():
    adapter = FunctionCallingAdapter(SkillRegistry([_echo_skill()]))

    tools = adapter.list_tools()

    assert tools[0]["function"]["name"] == "echo_skill"


def test_function_calling_adapter_executes_skill_and_trace():
    adapter = FunctionCallingAdapter(SkillRegistry([_echo_skill()]))

    result = adapter.execute_tool_call("echo_skill", {"text": "hello"}, call_id="call-1")

    assert result["success"] is True
    assert result["output"] == {"echo": "hello"}
    assert result["tool_call_trace"]["tool_call_id"] == "call-1"
    assert result["tool_call_trace"]["fallback_used"] is False


def test_function_calling_adapter_reports_validation_error():
    adapter = FunctionCallingAdapter(SkillRegistry([_echo_skill()]))

    result = adapter.execute_tool_call("echo_skill", {}, call_id="call-err")

    assert result["success"] is False
    assert "Missing required" in result["error"]
    assert result["tool_call_trace"]["status"] == "failed"


def _echo_skill() -> AgentSkill:
    return AgentSkill(
        name="echo_skill",
        description="Echo test skill",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        category="test",
        owner_agent="test_agent",
        safety_level="low",
        enabled=True,
        version="1.0",
        handler=lambda payload: {"echo": payload["text"]},
    )
