from evaluation.response_evaluator_v2 import (
    build_markdown_report,
    load_cases,
)
from evaluation.response_metrics_v2 import (
    evaluate_response_quality_v2,
    score_domain_relevance,
)


def test_data_privacy_food_template_pollution_fails():
    case = _case(
        category="data_privacy",
        required_concepts=[
            ["隐私", "个人信息", "数据安全"],
            ["泄露", "外泄", "疑似泄露"],
            ["用户", "消费者"],
            ["核查", "排查", "调查"],
        ],
        expected_actions=["核查", "通知用户", "安全整改"],
        forbidden_domain_terms=["原料", "生产流程", "仓储", "涉事批次"],
    )
    statement = (
        "我们已启动专项核查，将对原料、生产流程、仓储管理和涉事批次进行全面排查，"
        "并持续向公众同步进展。"
    )

    result = evaluate_response_quality_v2(statement, case["event"], case)

    assert result["scores"]["domain_relevance"] <= 3
    assert result["pass"] is False
    assert "原料" in result["details"]["domain_relevance"]["forbidden_domain_term_hits"]


def test_service_outage_food_template_pollution_fails():
    case = _case(
        category="service_outage",
        required_concepts=[
            ["服务", "平台", "系统"],
            ["无法登录", "故障", "不可用"],
            ["用户", "客户"],
            ["恢复", "修复", "恢复服务"],
        ],
        expected_actions=["故障排查", "服务恢复", "进展更新"],
        forbidden_domain_terms=["原料", "生产流程", "仓储", "涉事批次", "食品安全"],
    )
    statement = (
        "公司将围绕食品安全要求，对相关原料、生产流程、仓储和涉事批次进行核查，"
        "如发现问题将依法依规处理。"
    )

    result = evaluate_response_quality_v2(statement, case["event"], case)

    assert result["scores"]["domain_relevance"] <= 3
    assert result["pass"] is False
    assert result["details"]["domain_relevance"]["obvious_cross_domain_template"] is True


def test_food_safety_domain_terms_are_not_penalized_when_relevant():
    case = _case(
        category="food_safety",
        event="某食品品牌被曝光使用过期原料，消费者要求监管介入。",
        required_concepts=[
            ["食品安全", "食品"],
            ["过期原料", "原料"],
            ["核查", "排查", "调查"],
            ["监管", "监管部门"],
        ],
        expected_actions=["核查", "配合监管", "整改"],
        forbidden_domain_terms=["个人信息", "数据泄露", "服务恢复", "高管言论"],
    )
    statement = (
        "我们高度重视食品安全，已对过期原料、生产流程和涉事批次启动核查，"
        "并配合监管部门调查，后续将根据结果整改。"
    )

    score = score_domain_relevance(statement, case)

    assert score["score"] >= 7
    assert score["forbidden_domain_term_hits"] == []


def test_required_concepts_support_synonym_groups():
    case = _case(
        category="data_privacy",
        required_concepts=[
            ["隐私", "个人信息", "数据安全"],
            ["核查", "排查", "调查"],
            ["用户", "消费者"],
        ],
        expected_actions=["排查", "安全整改"],
        forbidden_domain_terms=["原料", "生产流程", "仓储"],
    )
    statement = "我们已关注用户对个人信息安全的担忧，正在排查相关问题并推动安全整改。"

    score = score_domain_relevance(statement, case)

    assert score["score"] >= 7
    assert ["隐私", "个人信息", "数据安全"] in score["matched_concept_groups"]


def test_domain_relevance_at_or_below_three_forces_fail():
    case = _case(
        category="data_privacy",
        required_concepts=[["隐私", "个人信息"], ["用户"], ["核查"]],
        expected_actions=["通知用户"],
        forbidden_domain_terms=["原料", "生产流程", "仓储", "涉事批次"],
    )
    statement = "我们将核查原料、生产流程、仓储和涉事批次。"

    result = evaluate_response_quality_v2(statement, case["event"], case)

    assert result["scores"]["domain_relevance"] <= 3
    assert result["strong_fail"] is True
    assert result["pass"] is False


def test_response_cases_v2_split_and_category_requirements():
    cases = load_cases()
    ids = [case["id"] for case in cases]
    development_ids = {case["id"] for case in cases if case["split"] == "development"}
    final_ids = {case["id"] for case in cases if case["split"] == "final"}
    categories = {case["category"] for case in cases}
    final_categories = {case["category"] for case in cases if case["split"] == "final"}

    assert len(cases) == 30
    assert len(development_ids) == 18
    assert len(final_ids) == 12
    assert len(ids) == len(set(ids))
    assert development_ids.isdisjoint(final_ids)
    assert categories == final_categories


def test_all_cases_define_required_v2_fields():
    required_fields = {
        "id",
        "split",
        "category",
        "event",
        "expected_risk",
        "expected_emotion",
        "acceptable_sources",
        "required_concepts",
        "expected_actions",
        "forbidden_domain_terms",
        "supported_facts",
        "expected_human_review",
    }

    for case in load_cases():
        assert required_fields <= set(case)
        assert all(isinstance(group, list) for group in case["required_concepts"])


def test_fallback_rate_one_report_marks_mock_or_fallback_notice():
    summary = {
        "agent_mode": "llm",
        "total_cases": 1,
        "pass_rate": 0.0,
        "fallback_rate": 1.0,
        "llm_case_count": 0,
        "mock_or_fallback_case_count": 1,
        "average_scores": {
            "legal_safety": 0,
            "empathy": 0,
            "action_completeness": 0,
            "communication_clarity": 0,
            "hallucination_risk": 0,
            "domain_relevance": 0,
        },
        "split_summary": {},
        "category_summary": {},
        "mock_or_fallback_warning": "本报告验证的是 mock/fallback 链路和 Evaluation 规则，不能解释为真实 LLM 生成效果。",
        "case_results": [],
    }

    report = build_markdown_report(summary)

    assert "本报告验证的是 mock/fallback 链路和 Evaluation 规则" in report
    assert "不能解释为真实 LLM 生成效果" in report


def _case(
    category: str,
    required_concepts: list[list[str]],
    expected_actions: list[str],
    forbidden_domain_terms: list[str],
    event: str = "某APP被曝用户个人信息疑似泄露，用户要求平台解释。",
) -> dict:
    return {
        "id": f"test_{category}",
        "split": "development",
        "category": category,
        "event": event,
        "expected_risk": "high",
        "expected_emotion": "angry",
        "acceptable_sources": [],
        "required_concepts": required_concepts,
        "expected_actions": expected_actions,
        "forbidden_domain_terms": forbidden_domain_terms,
        "supported_facts": [],
        "expected_human_review": True,
    }
