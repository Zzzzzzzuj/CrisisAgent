from copy import deepcopy

from backend.core.adapter import build_agent_input
from backend.core.context_pack_runtime import ContextPackRuntimeProvider
from backend.core.executor import execute
from backend.core.state import AgentState


def _state():
    return AgentState(
        session_id="p28-session",
        plan_id="p28-plan",
        event="示例公司食品安全投诉",
        metadata={
            "harness_spec": {
                "metadata": {"harness_id": "crisisagent-default", "version": "1.0.0", "status": "active"},
                "workflow": {"agent_order": ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"],
                              "dependencies": {name: [] for name in ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]}},
                "context_policy": {"token_budget_hint": 80},
            },
            "ingestion": {"source_items": [{"title": "投诉", "risk_level": "high"}], "risk_level": "high"},
        },
    )


def test_provider_builds_role_specific_snapshot_and_reuses_it():
    state = _state()
    provider = ContextPackRuntimeProvider()
    writer = provider.build_for_agent(state, "writer")
    redteam = provider.build_for_agent(state, "redteam")

    assert writer["agent_specific_focus"]["target_agent"] == "writer"
    assert redteam["agent_specific_focus"]["target_agent"] == "redteam"
    assert writer["context_pack_hash"] != ""
    assert state.metadata["context_pack_refs"]["writer"]["selected_count"] == 0
    assert provider.build_for_agent(state, "writer") == writer


def test_executor_injects_pack_without_changing_agent_result_contract():
    state = _state()
    captured = {}

    def writer(payload):
        captured.update(payload)
        return {"statement": "ok"}

    result = execute({"plan_id": "p28-plan", "plan": [{"agent": "writer", "reason": "test"}]}, state,
                     agent_registry={"writer": writer})

    assert result["results"]["writer"] == {"statement": "ok"}
    assert captured["context_pack"]["agent_specific_focus"]["target_agent"] == "writer"
    assert state.metadata["context_pack_snapshots"]["writer"]["context_pack_hash"]
    assert result["execution_trace"][0]["context_pack"]["target_agent"] == "writer"


def test_checkpoint_like_copy_keeps_pack_snapshot():
    state = _state()
    ContextPackRuntimeProvider().build_for_agent(state, "legal")
    restored = AgentState.from_dict(state.to_dict())
    assert restored.metadata["context_pack_snapshots"]["legal"] == state.metadata["context_pack_snapshots"]["legal"]


def test_adapter_remains_compatible_without_runtime_pack():
    state = _state()
    state.set_result("sentiment", {"risk_level": "high"})
    payload = build_agent_input("writer", state)
    assert payload["event"] == state.event
    assert "context_pack" not in payload
