from backend.rag.retrieval_need_gate import (
    CONTENT_EDITING,
    CRISIS_RESPONSE_NEEDED,
    CUSTOMER_SERVICE_LOOKUP,
    GENERAL_BUSINESS_INFORMATION,
    POLICY_LOOKUP,
    UNRELATED,
    evaluate_retrieval_need,
)


def test_food_safety_crisis_needs_rag():
    result = evaluate_retrieval_need("某食品品牌被曝光使用过期原料，相关视频在网络传播，消费者要求监管介入。")

    assert result["need_rag"] is True
    assert result["intent"] == CRISIS_RESPONSE_NEEDED
    assert "occurred_negative_event" in result["matched_signals"]


def test_data_leak_crisis_needs_rag():
    result = evaluate_retrieval_need("某APP已被曝光泄露用户身份证和手机号，用户要求平台回应。")

    assert result["need_rag"] is True
    assert result["intent"] == CRISIS_RESPONSE_NEEDED


def test_service_outage_crisis_needs_rag():
    result = evaluate_retrieval_need("在线服务大面积宕机，用户无法登录并投诉客服无响应。")

    assert result["need_rag"] is True
    assert result["intent"] == CRISIS_RESPONSE_NEEDED


def test_unrelated_query_does_not_need_rag():
    result = evaluate_retrieval_need("世界杯决赛比分和球队阵容分析")

    assert result["need_rag"] is False
    assert result["intent"] == UNRELATED


def test_business_non_crisis_does_not_need_rag():
    result = evaluate_retrieval_need("公司年度财报收入结构和利润率解读")

    assert result["need_rag"] is False
    assert result["intent"] == GENERAL_BUSINESS_INFORMATION


def test_privacy_policy_lookup_does_not_need_rag():
    result = evaluate_retrieval_need("用户想查询隐私政策入口在哪里")

    assert result["need_rag"] is False
    assert result["intent"] == POLICY_LOOKUP


def test_warranty_location_lookup_does_not_need_rag():
    result = evaluate_retrieval_need("消费者咨询产品保修期限和维修网点")

    assert result["need_rag"] is False
    assert result["intent"] == CUSTOMER_SERVICE_LOOKUP


def test_normal_executive_speech_editing_does_not_need_rag():
    result = evaluate_retrieval_need("高管普通公开演讲的发言稿润色")

    assert result["need_rag"] is False
    assert result["intent"] == CONTENT_EDITING


def test_regulation_study_discussion_does_not_need_rag():
    result = evaluate_retrieval_need("监管政策讨论和行业合规趋势分析")

    assert result["need_rag"] is False
    assert result["intent"] == POLICY_LOOKUP


def test_event_has_priority_over_crisis_like_draft():
    result = evaluate_retrieval_need(
        event="公司发布新产品",
        draft="我们正在核查相关情况并将持续整改，配合监管并承担责任。",
    )

    assert result["need_rag"] is False
    assert "辅助 draft/redteam 中的危机化表达不单独触发 RAG" in result["reason"]


def test_event_crisis_needs_rag_even_when_draft_is_short():
    result = evaluate_retrieval_need(
        event="某APP被曝泄露用户身份证信息，用户要求平台解释。",
        draft="我们会回应。",
    )

    assert result["need_rag"] is True


def test_output_schema_is_stable():
    result = evaluate_retrieval_need("用户查询客服热线和工作时间")

    assert set(result) == {
        "need_rag",
        "intent",
        "decision_score",
        "reason",
        "matched_signals",
        "negative_signals",
    }
    assert isinstance(result["decision_score"], int)
    assert isinstance(result["matched_signals"], list)
    assert isinstance(result["negative_signals"], list)


def test_evaluation_gold_fields_do_not_change_gate_decision():
    event = "用户想查询隐私政策入口在哪里"
    result_without_gold = evaluate_retrieval_need(event)
    result_with_gold_like_noise = evaluate_retrieval_need(
        event=event,
        redteam_review={
            "expected_hit": True,
            "acceptable_sources": ["data_privacy.md"],
            "split": "development",
            "gold category": "data_privacy",
        },
    )

    assert result_with_gold_like_noise["need_rag"] == result_without_gold["need_rag"]
    assert result_with_gold_like_noise["intent"] == result_without_gold["intent"]
