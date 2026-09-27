from backend.core.executor import execute
from backend.core.state import AgentState
from backend.harness.spec import build_default_harness_spec
from backend.skills.runtime_skills import create_runtime_skill_registry
from backend.skills.skill_selector import SkillSelector
from backend.skills.skill_schema import AgentSkill


def _state():
    return AgentState(session_id="skill-session", plan_id="skill-plan", event="食品安全投诉", metadata={
        "harness_spec": build_default_harness_spec(),
        "ingestion": {"risk_level": "high", "fact_status": "unverified", "source_items": [{"source": "a"}, {"source": "b"}]},
    })


def test_runtime_registry_has_four_skills_and_agent_allowlists():
    registry = create_runtime_skill_registry()
    items = {item["name"]: item for item in registry.list_skills()}
    assert {"event_risk_triage", "evidence_verification", "context_retrieval", "statement_constraint_check"} <= set(items)
    assert items["event_risk_triage"]["agent_allowlist"] == ["redteam"]
    assert items["context_retrieval"]["agent_allowlist"] == ["writer", "legal"]
    assert items["statement_constraint_check"]["agent_allowlist"] == ["writer_v2"]


def test_selector_produces_different_role_combinations_and_reasons():
    state = _state()
    selector = SkillSelector()
    redteam = selector.select_and_execute(state, "redteam", {"event": state.event})
    legal = selector.select_and_execute(state, "legal", {"context_pack": {"top_legal_evidence": []}})
    writer_v2 = selector.select_and_execute(state, "writer_v2", {"first_draft": {"statement": "draft"}, "legal_review": {}})

    assert [item["skill_id"] for item in redteam["selected"]] == ["event_risk_triage"]
    assert [item["skill_id"] for item in legal["selected"]] == ["context_retrieval", "evidence_verification"]
    assert [item["skill_id"] for item in writer_v2["selected"]] == ["statement_constraint_check"]
    assert redteam["selected"][0]["reason"]
    assert state.metadata["skill_runtime_results"]["legal"]["results"]
    assert any(item["reason"] == "not_required_for_agent" for item in redteam["skipped"])


def test_selector_reuses_saved_results_on_resume():
    state = _state()
    selector = SkillSelector()
    first = selector.select_and_execute(state, "redteam", {"event": state.event})
    state.metadata["ingestion"]["risk_level"] = "low"
    assert selector.select_and_execute(state, "redteam", {"event": "changed"}) == first


def test_executor_records_skill_results_and_checkpoint_like_state_is_rehydratable():
    state = _state()
    result = execute({"plan_id": "skill-plan", "plan": [{"agent": "redteam", "reason": "review"}]}, state,
                     agent_registry={"redteam": lambda payload: {"issues": [], "skill_count": len(payload["skill_results"]["results"])} })

    assert result["results"]["redteam"]["skill_count"] == 1
    assert result["execution_trace"][0]["skills"]["selected"][0]["skill_id"] == "event_risk_triage"
    restored = AgentState.from_dict(state.to_dict())
    assert restored.metadata["skill_runtime_results"] == state.metadata["skill_runtime_results"]


def test_skill_failure_is_structured_and_does_not_raise():
    registry = create_runtime_skill_registry()
    original = registry.get("event_risk_triage")
    registry._skills["event_risk_triage"] = AgentSkill(
        name=original.name, description=original.description, input_schema=original.input_schema,
        output_schema=original.output_schema, category=original.category, owner_agent=original.owner_agent,
        safety_level=original.safety_level, enabled=True, version=original.version,
        handler=lambda _: (_ for _ in ()).throw(RuntimeError("triage down")),
        skill_id=original.skill_id, agent_allowlist=original.agent_allowlist,
        preconditions=original.preconditions,
    )
    state = _state()
    result = SkillSelector(registry).select_and_execute(state, "redteam", {"event": state.event})

    assert result["results"][0]["success"] is False
    assert result["failure_tags"] == ["skill_tool_execution_failed"]
    assert state.metadata["skill_runtime_results"]["redteam"]["results"][0]["human_review_required"] is True
