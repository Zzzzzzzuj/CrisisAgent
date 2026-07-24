from backend.core.executor import execute


def test_executor_runs_normal_plan():
    plan = {
        "plan_id": "plan-1",
        "plan": [{"agent": "sentiment", "reason": "need sentiment"}],
    }
    context = {"event": "test event"}
    registry = {"sentiment": lambda payload: {"risk_level": "high", "event": payload}}

    result = execute(plan, context, agent_registry=registry)

    assert result["plan_id"] == "plan-1"
    assert result["executed_agents"] == ["sentiment"]
    assert result["results"]["sentiment"] == {"risk_level": "high", "event": "test event"}
    assert result["failed_agents"] == []
    assert result["execution_trace"][0]["status"] == "success"


def test_executor_runs_multiple_agents_in_plan_order():
    calls = []

    def make_runner(name):
        def runner(payload):
            calls.append(name)
            return {"agent": name}

        return runner

    plan = {
        "plan_id": "plan-2",
        "plan": [
            {"agent": "sentiment", "reason": "first"},
            {"agent": "writer", "reason": "second"},
            {"agent": "decision", "reason": "third"},
        ],
    }
    registry = {
        "sentiment": make_runner("sentiment"),
        "writer": make_runner("writer"),
        "decision": make_runner("decision"),
    }

    result = execute(plan, {"event": "test"}, agent_registry=registry)

    assert calls == ["sentiment", "writer", "decision"]
    assert result["executed_agents"] == ["sentiment", "writer", "decision"]
    assert [item["agent"] for item in result["execution_trace"]] == [
        "sentiment",
        "writer",
        "decision",
    ]


def test_executor_records_invalid_agent_without_crashing():
    plan = {
        "plan_id": "plan-3",
        "plan": [{"agent": "unknown", "reason": "bad agent"}],
    }

    result = execute(plan, {"event": "test"}, agent_registry={})

    assert result["executed_agents"] == []
    assert result["results"] == {}
    assert result["failed_agents"] == [
        {
            "agent": "unknown",
            "reason": "Agent is not registered.",
        }
    ]
    assert result["execution_trace"][0]["status"] == "failed"
    assert result["execution_trace"][0]["error"] == "Agent is not registered."


def test_executor_records_agent_exception_and_continues():
    def failing_runner(payload):
        raise RuntimeError("agent down")

    plan = {
        "plan_id": "plan-4",
        "plan": [
            {"agent": "legal", "reason": "may fail"},
            {"agent": "writer", "reason": "should continue"},
        ],
    }
    registry = {
        "legal": failing_runner,
        "writer": lambda payload: {"statement": "ok"},
    }

    result = execute(plan, {"event": "test"}, agent_registry=registry)

    assert result["executed_agents"] == ["writer"]
    assert result["results"] == {"writer": {"statement": "ok"}}
    assert result["failed_agents"][0]["agent"] == "legal"
    assert "RuntimeError: agent down" in result["failed_agents"][0]["reason"]
    assert [item["status"] for item in result["execution_trace"]] == ["failed", "success"]


def test_executor_output_schema_is_stable():
    plan = {
        "plan_id": "plan-5",
        "plan": [{"agent": "writer", "reason": "write response"}],
    }
    registry = {"writer": lambda payload: {"statement": "ok"}}

    result = execute(plan, {"event": "test"}, agent_registry=registry)

    assert set(result.keys()) == {
        "plan_id",
        "executed_agents",
        "results",
        "failed_agents",
        "execution_trace",
    }
    assert set(result["execution_trace"][0].keys()) == {
        "agent",
        "reason",
        "start_time",
        "end_time",
        "status",
        "output",
        "error",
    }
