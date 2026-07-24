import json

from evaluation import response_evaluator
from evaluation import response_judge
from evaluation.response_metrics import (
    evaluate_response_quality,
    score_action_completeness,
    score_communication_clarity,
    score_empathy,
    score_hallucination_risk,
    score_legal_safety,
    summarize_response_results,
)


SAFE_STATEMENT = (
    "我们已经关注到相关情况，并充分理解消费者和公众对此产生的担忧，对由此带来的不安深表歉意。"
    "公司已第一时间启动专项核查，正在对相关原料、生产流程和涉及批次进行全面排查。"
    "目前我们将积极配合监管部门的调查要求，并根据核查进展及时同步后续信息。"
    "如核查属实，我们将依法依规处理并推进整改。"
)
EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
CASE = {
    "id": "case-1",
    "category": "food_safety",
    "event": EVENT,
    "must_include": ["核查", "配合监管", "消费者", "持续"],
    "must_avoid": ["确认违法", "一定赔偿"],
    "expected_actions": ["调查", "整改", "配合监管", "后续更新"],
    "supported_facts": ["食品品牌", "过期原料", "偷拍视频", "网上传播", "监管介入"],
}


def test_legal_safety_detects_premature_liability_and_absolute_promise():
    result = score_legal_safety("我们确认违法，并一定赔偿所有损失。")

    assert result["score"] < 7
    assert any("提前定责" in issue for issue in result["issues"])
    assert any("绝对化承诺" in issue for issue in result["issues"])


def test_legal_safety_rewards_conditional_and_regulatory_actions():
    result = score_legal_safety("如核查属实，我们将依法依规处理，并积极配合监管部门调查。")

    assert result["score"] == 10
    assert result["issues"] == []


def test_empathy_scores_user_and_apology_expression():
    result = score_empathy("我们理解消费者和用户的担忧，并对此深表歉意，正在高度重视。")

    assert result["score"] == 10


def test_action_completeness_scores_required_actions():
    result = score_action_completeness("我们将启动调查，推进整改，配合监管，并持续更新后续进展。")

    assert result["score"] == 10


def test_communication_clarity_checks_length_keywords_and_forbidden_terms():
    result = score_communication_clarity("我们确认违法。", CASE)

    assert result["score"] < 7
    assert any("声明过短" in issue for issue in result["issues"])
    assert any("包含禁用表达" in issue for issue in result["issues"])


def test_hallucination_risk_detects_unsupported_specific_facts():
    result = score_hallucination_risk(
        "我们将在7月24日赔付100万元，并承诺99.9%安全。",
        EVENT,
        CASE,
    )

    assert result["score"] > 0
    assert "7月24日" in result["unsupported_facts"]
    assert "100万" in result["unsupported_facts"]
    assert "99.9%" in result["unsupported_facts"]


def test_evaluate_response_quality_returns_scores_and_pass():
    result = evaluate_response_quality(SAFE_STATEMENT, EVENT, CASE)

    assert result["pass"] is True
    assert set(result["scores"].keys()) == {
        "legal_safety",
        "empathy",
        "action_completeness",
        "communication_clarity",
        "hallucination_risk",
    }


def test_summarize_response_results_calculates_average_scores():
    case_results = [
        {"response_evaluation": evaluate_response_quality(SAFE_STATEMENT, EVENT, CASE)},
        {"response_evaluation": evaluate_response_quality("我们确认违法，并一定赔偿所有损失。", EVENT, CASE)},
    ]

    summary = summarize_response_results(case_results)

    assert summary["total_cases"] == 2
    assert 0 <= summary["pass_rate"] <= 1
    assert "average_scores" in summary
    assert summary["average_scores"]["legal_safety"] < 10


def test_response_evaluator_generates_json_and_markdown_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("EVALUATION_JUDGE_MODE", "rule")

    class FakeResponse:
        def model_dump(self):
            return {
                "session_id": "session-1",
                "final_statement": SAFE_STATEMENT,
                "scores": {
                    "legal_safety": 8,
                    "empathy": 8,
                    "robustness": 8,
                },
                "agent_trace": [],
            }

    cases_path = tmp_path / "response_cases.json"
    cases_path.write_text(json.dumps([CASE], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(response_evaluator, "run_crisis_workflow", lambda request: FakeResponse())

    summary = response_evaluator.evaluate_cases(cases_path)
    saved_paths = response_evaluator.save_results(
        summary,
        outputs_dir=tmp_path / "outputs",
        reports_dir=tmp_path / "reports",
    )

    json_report = saved_paths["json_path"]
    markdown_report = saved_paths["markdown_path"]

    assert summary["total_cases"] == 1
    assert summary["case_results"][0]["response_evaluation"]["pass"] is True
    assert json_report.endswith(".json")
    assert markdown_report.endswith("latest_response_report.md")
    assert "Response Evaluation Report" in (tmp_path / "reports" / "latest_response_report.md").read_text(
        encoding="utf-8"
    )


def test_response_judge_rule_mode_does_not_call_llm(monkeypatch):
    monkeypatch.setenv("EVALUATION_JUDGE_MODE", "rule")
    rule_evaluation = evaluate_response_quality(SAFE_STATEMENT, EVENT, CASE)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM judge should not be called in rule mode")

    monkeypatch.setattr(response_judge.judge_client, "call_judge_llm", fail_if_called)

    result = response_judge.evaluate_with_optional_judge(EVENT, SAFE_STATEMENT, rule_evaluation)

    assert result["mode"] == "rule"
    assert result["fallback"] is False
    assert result["scores"] == rule_evaluation["scores"]


def test_response_judge_llm_mode_calls_judge_and_parses_json(monkeypatch):
    monkeypatch.setenv("EVALUATION_JUDGE_MODE", "llm")
    captured = {}
    rule_evaluation = evaluate_response_quality(SAFE_STATEMENT, EVENT, CASE)

    def fake_call_judge_llm(event, final_statement):
        captured["event"] = event
        captured["final_statement"] = final_statement
        return """
        ```json
        {
          "legal_safety": 9,
          "empathy": 8,
          "action_completeness": 9,
          "communication_clarity": 8,
          "hallucination_risk": 1,
          "issues": ["表达可以更具体"]
        }
        ```
        """

    monkeypatch.setattr(response_judge.judge_client, "call_judge_llm", fake_call_judge_llm)

    result = response_judge.evaluate_with_optional_judge(EVENT, SAFE_STATEMENT, rule_evaluation)

    assert captured["event"] == EVENT
    assert captured["final_statement"] == SAFE_STATEMENT
    assert result["mode"] == "llm"
    assert result["fallback"] is False
    assert result["scores"] == {
        "legal_safety": 9,
        "empathy": 8,
        "action_completeness": 9,
        "communication_clarity": 8,
        "hallucination_risk": 1,
    }
    assert result["issues"] == ["表达可以更具体"]


def test_response_judge_json_parse_failure_falls_back_to_rule(monkeypatch):
    monkeypatch.setenv("EVALUATION_JUDGE_MODE", "llm")
    rule_evaluation = evaluate_response_quality(SAFE_STATEMENT, EVENT, CASE)
    monkeypatch.setattr(response_judge.judge_client, "call_judge_llm", lambda event, statement: "not json")

    result = response_judge.evaluate_with_optional_judge(EVENT, SAFE_STATEMENT, rule_evaluation)

    assert result["mode"] == "llm"
    assert result["fallback"] is True
    assert result["fallback_to"] == "rule"
    assert result["scores"] == rule_evaluation["scores"]
    assert "error" in result


def test_response_judge_missing_field_falls_back_to_rule(monkeypatch):
    monkeypatch.setenv("EVALUATION_JUDGE_MODE", "llm")
    rule_evaluation = evaluate_response_quality(SAFE_STATEMENT, EVENT, CASE)
    monkeypatch.setattr(
        response_judge.judge_client,
        "call_judge_llm",
        lambda event, statement: '{"legal_safety": 9}',
    )

    result = response_judge.evaluate_with_optional_judge(EVENT, SAFE_STATEMENT, rule_evaluation)

    assert result["mode"] == "llm"
    assert result["fallback"] is True
    assert result["scores"] == rule_evaluation["scores"]
