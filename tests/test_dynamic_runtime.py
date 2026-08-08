from backend.core.dynamic_runtime import run_dynamic_agent


TEST_EVENT = "food safety crisis event with public complaints"
FIRST_DRAFT = "first draft statement"
SECOND_DRAFT = "second draft statement after redteam and legal review"


def _fake_registry():
    def sentiment(event):
        assert event == TEST_EVENT
        return {
            "risk_level": "high",
            "public_emotion": "angry",
            "keywords": ["food safety"],
            "recommended_tone": "先共情、再回应行动、避免抢先定性",
            "analysis_summary": "High risk food safety event.",
        }

    def writer(payload):
        assert payload["event"] == TEST_EVENT
        assert payload["sentiment_analysis"]["risk_level"] == "high"
        return {
            "statement": FIRST_DRAFT,
            "strategy": "empathy first",
            "tone": "先共情、再回应行动、避免抢先定性",
            "notes": "dynamic writer",
        }

    def redteam(payload):
        assert payload["draft"] == FIRST_DRAFT
        return {
            "issues": ["action details are not specific enough"],
            "attack_summary": "Could be challenged for lacking concrete actions.",
            "suggestions": ["add update mechanism"],
        }

    def legal(payload):
        assert payload["draft"] == FIRST_DRAFT
        assert payload["redteam_review"]["issues"] == ["action details are not specific enough"]
        return {
            "legal_risks": [],
            "safe_points": ["no premature admission"],
            "revision_advice": ["keep conditional wording"],
            "public_opinion_suggestions": ["add update mechanism"],
            "integrated_revision_tasks": ["add investigation scope"],
            "legal_safety_score_hint": 8,
            "review_summary": "Overall safe.",
        }

    def writer_v2(payload):
        assert payload["first_draft"]["statement"] == FIRST_DRAFT
        assert payload["redteam_review"]["attack_summary"]
        assert payload["legal_review"]["integrated_revision_tasks"] == ["add investigation scope"]
        return {
            "statement": SECOND_DRAFT,
            "strategy": "revise based on redteam and legal review",
            "revisions_from_v1": ["added investigation scope"],
            "review_summary": {"first_draft_excerpt": FIRST_DRAFT},
        }

    def decision(payload):
        assert payload["second_draft"] == SECOND_DRAFT
        assert payload["results"]["writer_v2"]["statement"] == SECOND_DRAFT
        assert payload["legal_review"]["legal_safety_score_hint"] == 8
        return {
            "final_statement": payload["second_draft"],
            "scores": {
                "legal_safety": 8,
                "empathy": 8,
                "robustness": 8,
            },
            "decision_summary": "dynamic decision",
        }

    return {
        "sentiment": sentiment,
        "writer": writer,
        "redteam": redteam,
        "legal": legal,
        "writer_v2": writer_v2,
        "decision": decision,
    }


def test_dynamic_runtime_generates_plan_and_validator_fixes_dependencies():
    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())

    raw_agents = [item["agent"] for item in result["raw_plan"]["plan"]]
    validated_agents = [item["agent"] for item in result["validated_plan"]["plan"]]

    assert raw_agents == ["writer", "redteam", "writer_v2", "decision"]
    assert validated_agents == [
        "sentiment",
        "writer",
        "redteam",
        "legal",
        "writer_v2",
        "decision",
    ]


def test_dynamic_runtime_executes_agents_and_saves_state_results():
    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())

    assert result["executed_agents"] == [
        "sentiment",
        "writer",
        "redteam",
        "legal",
        "writer_v2",
        "decision",
    ]
    assert result["failed_agents"] == []
    assert result["results"]["sentiment"]["risk_level"] == "high"
    assert result["results"]["writer"]["statement"] == FIRST_DRAFT
    assert result["results"]["writer_v2"]["statement"] == SECOND_DRAFT
    assert result["results"]["decision"]["final_statement"] == SECOND_DRAFT


def test_dynamic_runtime_execution_trace_is_complete():
    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())
    trace = result["execution_trace"]

    assert len(trace) == 6
    assert [item["agent"] for item in trace] == [
        "sentiment",
        "writer",
        "redteam",
        "legal",
        "writer_v2",
        "decision",
    ]
    assert all(item["status"] == "success" for item in trace)
    assert all("start_time" in item for item in trace)
    assert all("end_time" in item for item in trace)
    assert all("output" in item for item in trace)


def test_dynamic_runtime_records_executor_failure_without_crashing():
    registry = _fake_registry()

    def failing_legal(payload):
        raise RuntimeError("legal unavailable")

    def fallback_writer_v2(payload):
        return {
            "statement": payload["first_draft"]["statement"],
            "strategy": "fallback",
            "revisions_from_v1": [],
            "review_summary": {},
        }

    registry["legal"] = failing_legal
    registry["writer_v2"] = fallback_writer_v2
    registry["decision"] = lambda payload: {
        "final_statement": payload["second_draft"],
        "scores": {
            "legal_safety": 6,
            "empathy": 8,
            "robustness": 6,
        },
        "decision_summary": "decision continued without legal",
    }
    result = run_dynamic_agent(TEST_EVENT, agent_registry=registry)

    assert result["executed_agents"] == ["sentiment", "writer", "redteam", "writer_v2", "decision"]
    assert result["failed_agents"][0]["agent"] == "legal"
    assert result["execution_trace"][3]["agent"] == "legal"
    assert result["execution_trace"][3]["status"] == "failed"
