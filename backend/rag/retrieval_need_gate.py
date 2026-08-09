CRISIS_RESPONSE_NEEDED = "crisis_response_needed"
UNRELATED = "unrelated"
GENERAL_BUSINESS_INFORMATION = "general_business_information"
INFORMATION_LOOKUP = "information_lookup"
POLICY_LOOKUP = "policy_lookup"
CUSTOMER_SERVICE_LOOKUP = "customer_service_lookup"
CONTENT_EDITING = "content_editing"
HYPOTHETICAL_DISCUSSION = "hypothetical_discussion"

POSITIVE_SIGNAL_GROUPS = {
    "occurred_negative_event": (
        "被曝",
        "曝光",
        "泄露",
        "外泄",
        "宕机",
        "故障",
        "无法登录",
        "交易失败",
        "投诉",
        "抵制",
        "不适",
        "过期",
        "不合格",
        "安全隐患",
        "过度收集",
        "滥用",
        "鼓包",
        "漏水",
        "集中投诉",
        "不当言论",
        "歧视",
        "嘲讽",
    ),
    "affected_public": (
        "用户",
        "消费者",
        "公众",
        "网友",
        "家长",
        "儿童",
        "商户",
        "员工",
        "客户",
    ),
    "response_or_action_required": (
        "要求",
        "回应",
        "解释",
        "道歉",
        "监管",
        "调查",
        "核查",
        "公开",
        "处理",
        "补偿",
        "整改",
        "恢复",
        "召回",
        "检测",
        "维修方案",
        "介入",
    ),
    "public_spread": (
        "传播",
        "视频",
        "热搜",
        "舆论",
        "舆情",
        "黑客论坛",
        "数据样本",
        "媒体",
    ),
}

NEGATIVE_SIGNAL_GROUPS = {
    UNRELATED: (
        "世界杯",
        "旅游",
        "酒店",
        "Python",
        "天气",
        "空气质量",
        "电影",
        "二次函数",
        "翻译",
        "游戏",
        "装备",
    ),
    GENERAL_BUSINESS_INFORMATION: (
        "年度财报",
        "收入结构",
        "利润率",
        "新产品发布会",
        "市场卖点",
        "招聘计划",
        "岗位要求",
        "会员价格",
        "办公室搬迁",
        "交通指南",
        "展会",
        "促销活动",
        "优惠券",
        "融资轮次",
        "投资机构",
    ),
    INFORMATION_LOOKUP: (
        "查询",
        "在哪里",
        "入口",
        "介绍",
        "说明",
        "指南",
        "路线",
        "推荐",
    ),
    POLICY_LOOKUP: (
        "隐私政策",
        "监管政策",
        "政策讨论",
        "合规趋势",
        "学习材料",
    ),
    CUSTOMER_SERVICE_LOOKUP: (
        "客服热线",
        "工作时间",
        "保修期限",
        "维修网点",
        "售后网点",
    ),
    CONTENT_EDITING: (
        "润色",
        "发言稿",
        "翻译成",
        "语法示例",
    ),
    HYPOTHETICAL_DISCUSSION: (
        "未来可能",
        "猜测",
        "假设",
        "是否有",
        "趋势分析",
        "历史投诉",
        "三年前",
    ),
}


def evaluate_retrieval_need(
    event: str,
    draft: str = "",
    redteam_review: dict | None = None,
) -> dict:
    event_text = str(event or "")
    auxiliary_text = _build_auxiliary_text(draft, redteam_review)

    matched_signals = _matched_positive_signals(event_text)
    negative_signals = _matched_negative_signals(event_text)
    auxiliary_signals = _matched_positive_signals(auxiliary_text) if auxiliary_text else []

    positive_score = sum(_positive_signal_weight(signal) for signal in matched_signals)
    negative_score = sum(_negative_signal_weight(signal) for signal in negative_signals)
    decision_score = positive_score - negative_score
    intent = _resolve_intent(matched_signals, negative_signals, decision_score)
    need_rag = intent == CRISIS_RESPONSE_NEEDED

    return {
        "need_rag": need_rag,
        "intent": intent,
        "decision_score": decision_score,
        "reason": _build_reason(need_rag, intent, matched_signals, negative_signals, auxiliary_signals),
        "matched_signals": matched_signals,
        "negative_signals": negative_signals,
    }


def _build_auxiliary_text(draft: str, redteam_review: dict | None) -> str:
    parts = [str(draft or "")]
    if isinstance(redteam_review, dict):
        parts.append(str(redteam_review.get("attack_summary", "")))
        parts.append(str(redteam_review.get("issues", [])))
        parts.append(str(redteam_review.get("suggestions", [])))
    return "\n".join(part for part in parts if part)


def _matched_positive_signals(text: str) -> list[str]:
    signals = []
    for signal, terms in POSITIVE_SIGNAL_GROUPS.items():
        if any(term in text for term in terms):
            signals.append(signal)
    return signals


def _matched_negative_signals(text: str) -> list[str]:
    signals = []
    for signal, terms in NEGATIVE_SIGNAL_GROUPS.items():
        if any(term in text for term in terms):
            signals.append(signal)
    return signals


def _positive_signal_weight(signal: str) -> int:
    if signal == "occurred_negative_event":
        return 2
    if signal == "response_or_action_required":
        return 2
    return 1


def _negative_signal_weight(signal: str) -> int:
    if signal in {UNRELATED, GENERAL_BUSINESS_INFORMATION, CONTENT_EDITING}:
        return 3
    if signal in {POLICY_LOOKUP, CUSTOMER_SERVICE_LOOKUP, HYPOTHETICAL_DISCUSSION}:
        return 2
    return 1


def _resolve_intent(
    matched_signals: list[str],
    negative_signals: list[str],
    decision_score: int,
) -> str:
    has_occurred_event = "occurred_negative_event" in matched_signals
    has_public_or_action = bool(
        {"affected_public", "response_or_action_required", "public_spread"} & set(matched_signals)
    )
    if has_occurred_event and has_public_or_action and decision_score >= 2:
        return CRISIS_RESPONSE_NEEDED

    if negative_signals:
        return _primary_negative_intent(negative_signals)

    if len(matched_signals) >= 3 and decision_score >= 3:
        return CRISIS_RESPONSE_NEEDED

    return INFORMATION_LOOKUP


def _primary_negative_intent(negative_signals: list[str]) -> str:
    priority = (
        UNRELATED,
        GENERAL_BUSINESS_INFORMATION,
        CUSTOMER_SERVICE_LOOKUP,
        CONTENT_EDITING,
        POLICY_LOOKUP,
        HYPOTHETICAL_DISCUSSION,
        INFORMATION_LOOKUP,
    )
    for intent in priority:
        if intent in negative_signals:
            return intent
    return INFORMATION_LOOKUP


def _build_reason(
    need_rag: bool,
    intent: str,
    matched_signals: list[str],
    negative_signals: list[str],
    auxiliary_signals: list[str],
) -> str:
    if need_rag:
        return (
            "事件文本包含已发生负面事件，并同时出现公众影响、传播或回应处置信号，"
            "需要危机响应/合规知识检索。"
        )
    if auxiliary_signals and not matched_signals:
        return (
            f"事件文本本身未体现危机响应意图，辅助 draft/redteam 中的危机化表达不单独触发 RAG；"
            f"当前判定为 {intent}。"
        )
    if negative_signals:
        return f"事件更接近 {intent}，不属于当前危机响应/合规知识检索需求。"
    return "事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。"
