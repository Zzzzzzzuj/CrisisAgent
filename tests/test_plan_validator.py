import pytest

from backend.core.plan_validator import validate_plan


def test_validate_plan_reorders_when_legal_appears_too_early():
    plan = {
        "plan_id": "plan-1",
        "plan": [
            {"agent": "sentiment", "reason": "analyze"},
            {"agent": "legal", "reason": "review"},
            {"agent": "writer", "reason": "write"},
        ],
    }

    result = validate_plan(plan)

    assert [item["agent"] for item in result["plan"]] == [
        "sentiment",
        "writer",
        "redteam",
        "legal",
    ]
    assert result["plan"][1]["reason"] == "write"
    assert result["plan"][3]["reason"] == "review"


def test_validate_plan_adds_missing_redteam_for_legal():
    plan = {
        "plan_id": "plan-2",
        "plan": [
            {"agent": "writer", "reason": "write"},
            {"agent": "legal", "reason": "review"},
        ],
    }

    result = validate_plan(plan)

    agents = [item["agent"] for item in result["plan"]]
    assert agents == ["sentiment", "writer", "redteam", "legal"]
    redteam_item = result["plan"][2]
    assert redteam_item["agent"] == "redteam"
    assert redteam_item["confidence"] == 1.0
    assert "Automatically added dependency" in redteam_item["reason"]


def test_validate_plan_writer_to_decision_keeps_dependency_order():
    plan = {
        "plan_id": "plan-3",
        "plan": [
            {"agent": "writer", "reason": "write"},
            {"agent": "decision", "reason": "decide"},
        ],
    }

    result = validate_plan(plan)

    assert [item["agent"] for item in result["plan"]] == [
        "sentiment",
        "writer",
        "redteam",
        "legal",
        "decision",
    ]
    assert result["plan"][1]["reason"] == "write"
    assert result["plan"][4]["reason"] == "decide"


def test_validate_plan_rejects_invalid_agent():
    plan = {
        "plan_id": "plan-4",
        "plan": [{"agent": "unknown", "reason": "bad"}],
    }

    with pytest.raises(ValueError, match="Unsupported agent"):
        validate_plan(plan)
