from backend.core.agent_loop import run_agent_loop


TEST_EVENT = "test crisis event"
NO_HUMAN_POLICY = lambda state, evaluation: {"required": False, "reason": "", "triggers": []}


def _plan(plan_id="plan-1"):
    return {
        "plan_id": plan_id,
        "plan": [
            {"agent": "writer", "reason": "write"},
            {"agent": "decision", "reason": "decide"},
        ],
    }


def test_agent_loop_success_finishes_after_one_iteration():
    calls = {"planner": 0, "executor": 0, "evaluator": 0}

    def planner(payload):
        calls["planner"] += 1
        return _plan()

    def executor(plan, state, agent_registry=None):
        calls["executor"] += 1
        state.set_result("writer", {"statement": "ok"})
        state.set_result("decision", {"final_statement": "ok"})
        state.add_trace(
            {
                "agent": "writer",
                "reason": "write",
                "start_time": "start",
                "end_time": "end",
                "status": "success",
                "output": {"statement": "ok"},
                "error": None,
            }
        )
        return {
            "plan_id": plan["plan_id"],
            "executed_agents": ["writer", "decision"],
            "results": state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(state.trace),
        }

    def evaluator(state):
        calls["evaluator"] += 1
        return {"passed": True, "issues": []}

    result = run_agent_loop(
        TEST_EVENT,
        planner=planner,
        validator=lambda plan: plan,
        executor=executor,
        evaluator=evaluator,
        policy=NO_HUMAN_POLICY,
    )

    assert result["status"] == "completed"
    assert result["stopped_reason"] == "evaluation_passed"
    assert len(result["iterations"]) == 1
    assert calls == {"planner": 1, "executor": 1, "evaluator": 1}


def test_agent_loop_evaluation_failure_triggers_replan():
    planner_calls = []

    def planner(payload):
        planner_calls.append(payload)
        return _plan(plan_id=f"plan-{len(planner_calls)}")

    def executor(plan, state, agent_registry=None):
        state.set_result("writer", {"statement": f"draft-{plan['plan_id']}"})
        if plan["plan_id"] == "plan-2":
            state.set_result("decision", {"final_statement": "ok"})
        return {
            "plan_id": plan["plan_id"],
            "executed_agents": ["writer"],
            "results": state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(state.trace),
        }

    def evaluator(state):
        if not state.get_result("decision"):
            return {"passed": False, "issues": ["missing decision"]}
        return {"passed": True, "issues": []}

    result = run_agent_loop(
        TEST_EVENT,
        max_iterations=2,
        planner=planner,
        validator=lambda plan: plan,
        executor=executor,
        evaluator=evaluator,
        policy=NO_HUMAN_POLICY,
    )

    assert result["status"] == "completed"
    assert len(result["iterations"]) == 2
    assert len(planner_calls) == 2
    assert result["iterations"][0]["evaluation"]["passed"] is False
    assert result["iterations"][1]["evaluation"]["passed"] is True


def test_agent_loop_exits_after_max_iterations():
    def executor(plan, state, agent_registry=None):
        state.set_result("writer", {"statement": "draft"})
        return {
            "plan_id": plan["plan_id"],
            "executed_agents": ["writer"],
            "results": state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(state.trace),
        }

    result = run_agent_loop(
        TEST_EVENT,
        max_iterations=2,
        planner=lambda payload: _plan(),
        validator=lambda plan: plan,
        executor=executor,
        evaluator=lambda state: {"passed": False, "issues": ["still invalid"]},
        policy=NO_HUMAN_POLICY,
    )

    assert result["status"] == "failed"
    assert result["stopped_reason"] == "max_iterations_reached"
    assert len(result["iterations"]) == 2


def test_agent_loop_state_trace_records_each_iteration_evaluation():
    result = run_agent_loop(
        TEST_EVENT,
        max_iterations=2,
        planner=lambda payload: _plan(),
        validator=lambda plan: plan,
        executor=lambda plan, state, agent_registry=None: {
            "plan_id": plan["plan_id"],
            "executed_agents": [],
            "results": state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(state.trace),
        },
        evaluator=lambda state: {"passed": False, "issues": ["not enough output"]},
        policy=NO_HUMAN_POLICY,
    )

    loop_traces = [item for item in result["execution_trace"] if item["agent"] == "agent_loop"]
    assert len(loop_traces) == 2
    assert [item["status"] for item in loop_traces] == ["failed", "failed"]
    assert loop_traces[0]["output"]["iteration"] == 1
    assert loop_traces[1]["output"]["iteration"] == 2


def test_agent_loop_agent_failure_does_not_destroy_state_results():
    def executor(plan, state, agent_registry=None):
        state.set_result("writer", {"statement": "draft survives"})
        state.mark_failed("legal", "RuntimeError: legal down")
        state.add_trace(
            {
                "agent": "legal",
                "reason": "review",
                "start_time": "start",
                "end_time": "end",
                "status": "failed",
                "output": None,
                "error": "RuntimeError: legal down",
            }
        )
        return {
            "plan_id": plan["plan_id"],
            "executed_agents": ["writer"],
            "results": state.get_all_results(),
            "failed_agents": list(state.failed_agents),
            "execution_trace": list(state.trace),
        }

    result = run_agent_loop(
        TEST_EVENT,
        max_iterations=1,
        planner=lambda payload: _plan(),
        validator=lambda plan: plan,
        executor=executor,
        evaluator=lambda state: {"passed": False, "issues": ["legal failed"]},
        policy=NO_HUMAN_POLICY,
    )

    assert result["results"]["writer"] == {"statement": "draft survives"}
    assert result["failed_agents"] == [
        {
            "agent": "legal",
            "reason": "RuntimeError: legal down",
        }
    ]
    assert result["execution_trace"][0]["status"] == "failed"
