from backend.core.dynamic_runtime import run_dynamic_agent


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def _fake_registry():
    def sentiment(event):
        assert event == TEST_EVENT
        return {
            "risk_level": "high",
            "public_emotion": "angry",
            "keywords": ["过期原料"],
            "recommended_tone": "先共情、再回应行动、避免抢先定性",
            "analysis_summary": "高风险食品安全事件。",
        }

    def writer(payload):
        assert payload["event"] == TEST_EVENT
        assert payload["sentiment_analysis"]["risk_level"] == "high"
        return {
            "statement": "我们已关注到相关情况，并启动核查。",
            "strategy": "先共情再行动。",
            "tone": "先共情、再回应行动、避免抢先定性",
            "notes": "dynamic writer",
        }

    def redteam(payload):
        assert payload["draft"] == "我们已关注到相关情况，并启动核查。"
        return {
            "issues": ["行动说明还可以更完整"],
            "attack_summary": "可能被质疑不够具体。",
            "suggestions": ["补充后续更新机制"],
        }

    def legal(payload):
        assert payload["draft"] == "我们已关注到相关情况，并启动核查。"
        assert payload["redteam_review"]["issues"] == ["行动说明还可以更完整"]
        return {
            "legal_risks": [],
            "safe_points": ["未提前定责"],
            "revision_advice": ["保留条件式表达"],
            "public_opinion_suggestions": ["补充后续更新机制"],
            "integrated_revision_tasks": ["补充核查范围"],
            "legal_safety_score_hint": 8,
            "review_summary": "整体稳妥。",
        }

    def decision(payload):
        assert payload["results"]["writer"]["statement"] == "我们已关注到相关情况，并启动核查。"
        assert payload["results"]["legal"]["legal_safety_score_hint"] == 8
        return {
            "final_statement": payload["results"]["writer"]["statement"],
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
        "decision": decision,
    }


def test_dynamic_runtime_generates_plan_and_validator_fixes_dependencies():
    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())

    raw_agents = [item["agent"] for item in result["raw_plan"]["plan"]]
    validated_agents = [item["agent"] for item in result["validated_plan"]["plan"]]

    assert raw_agents == ["sentiment", "legal", "writer", "decision"]
    assert validated_agents == ["sentiment", "writer", "redteam", "legal", "decision"]


def test_dynamic_runtime_executes_agents_and_saves_state_results():
    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())

    assert result["executed_agents"] == ["sentiment", "writer", "redteam", "legal", "decision"]
    assert result["failed_agents"] == []
    assert result["results"]["sentiment"]["risk_level"] == "high"
    assert result["results"]["writer"]["statement"] == "我们已关注到相关情况，并启动核查。"
    assert result["results"]["redteam"]["issues"] == ["行动说明还可以更完整"]
    assert result["results"]["legal"]["legal_safety_score_hint"] == 8
    assert result["results"]["decision"]["final_statement"] == "我们已关注到相关情况，并启动核查。"


def test_dynamic_runtime_execution_trace_is_complete():
    result = run_dynamic_agent(TEST_EVENT, agent_registry=_fake_registry())
    trace = result["execution_trace"]

    assert len(trace) == 5
    assert [item["agent"] for item in trace] == [
        "sentiment",
        "writer",
        "redteam",
        "legal",
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

    registry["legal"] = failing_legal
    registry["decision"] = lambda payload: {
        "final_statement": payload["results"]["writer"]["statement"],
        "scores": {
            "legal_safety": 6,
            "empathy": 8,
            "robustness": 6,
        },
        "decision_summary": "decision continued without legal",
    }
    result = run_dynamic_agent(TEST_EVENT, agent_registry=registry)

    assert result["executed_agents"] == ["sentiment", "writer", "redteam", "decision"]
    assert result["failed_agents"][0]["agent"] == "legal"
    assert result["execution_trace"][3]["agent"] == "legal"
    assert result["execution_trace"][3]["status"] == "failed"
