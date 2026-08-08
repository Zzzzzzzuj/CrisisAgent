from backend.evaluation import evaluate_agent_run


EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def test_evaluation_passes_safe_food_safety_statement():
    final_statement = (
        "我们已注意到相关网络传播内容，并充分理解公众和消费者对此产生的担忧与关切。"
        "公司已立即启动专项核查，对相关原料、生产流程和涉事批次进行全面排查。"
        "如核查发现违反食品安全要求的情形，我们将依法依规严肃处理并推进整改。"
        "目前我们正积极配合监管部门调查，并将根据核查进展持续同步后续信息。"
        "对于给消费者带来的不安，我们表示歉意。"
    )
    results = {
        "redteam": {"suggestions": ["补充后续更新机制"]},
        "writer_v2": {"statement": final_statement},
    }
    trace = [{"agent": "writer_v2", "status": "success"}]

    evaluation = evaluate_agent_run(EVENT, results, final_statement, trace)

    assert evaluation["passed"] is True
    assert evaluation["legal_safety_score"] >= 7
    assert evaluation["empathy_score"] >= 6
    assert evaluation["robustness_score"] >= 6
    assert set(evaluation.keys()) == {
        "legal_safety_score",
        "empathy_score",
        "robustness_score",
        "passed",
        "issues",
        "suggestions",
    }


def test_evaluation_lowers_legal_safety_for_absolute_commitments():
    final_statement = (
        "公司已经确认事件事实属实，公司一定负责，绝不发生类似问题。"
        "我们会给所有消费者一个结果。"
    )
    results = {
        "redteam": {"suggestions": ["补充核查进展"]},
        "writer_v2": {"statement": final_statement},
    }
    trace = [{"agent": "writer_v2", "status": "success"}]

    evaluation = evaluate_agent_run(EVENT, results, final_statement, trace)

    assert evaluation["legal_safety_score"] < 7
    assert evaluation["passed"] is False
    assert any("提前确认" in issue or "绝对化承诺" in issue for issue in evaluation["issues"])
