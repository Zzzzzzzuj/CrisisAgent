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
        "患者",
        "合作方",
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
        "说明",
        "方案",
        "安排",
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
        "截图",
        "录屏",
        "社交平台",
        "社群",
        "评论区",
        "发酵",
        "转发",
    ),
    "harm_or_anomaly": (
        "腹痛",
        "呕吐",
        "异物",
        "虫害",
        "气味异常",
        "不舒服",
        "红肿",
        "发热",
        "过热",
        "冒烟",
        "松动",
        "跌落",
        "卡住",
        "中断",
        "无法",
        "迟迟",
        "漏洞",
        "陌生设备",
        "骚扰电话",
        "看到其他账号",
        "订单不同步",
        "信息被获取",
        "信息泄露",
        "资料被改动",
        "退款",
        "取关",
        "排长队",
        "交付受到影响",
        "皮肤",
        "风险",
        "异常",
    ),
    "enterprise_context": (
        "公司",
        "企业",
        "品牌",
        "平台",
        "APP",
        "门店",
        "产品",
        "服务",
        "系统",
        "小程序",
        "运营方",
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
        "山水画",
        "健身",
        "咖啡机",
    ),
    GENERAL_BUSINESS_INFORMATION: (
        "年度财报",
        "季度业绩",
        "收入结构",
        "利润率",
        "新产品发布",
        "发布新产品",
        "发布会",
        "市场卖点",
        "招聘计划",
        "岗位要求",
        "会员价格",
        "会员体系",
        "积分兑换",
        "办公室搬迁",
        "交通指南",
        "展会",
        "促销活动",
        "优惠券",
        "融资轮次",
        "投资机构",
        "参展",
        "权益说明",
    ),
    INFORMATION_LOOKUP: (
        "查询",
        "在哪里",
        "怎么查",
        "入口",
        "链接",
        "名单",
        "联系方式",
        "原文",
        "批次编号",
        "查看",
    ),
    POLICY_LOOKUP: (
        "隐私政策",
        "监管政策",
        "监管法规",
        "政策讨论",
        "合规趋势",
        "学习材料",
        "法规材料",
        "政策变化",
        "行业趋势",
    ),
    CUSTOMER_SERVICE_LOOKUP: (
        "客服热线",
        "客服电话",
        "工作时间",
        "保修期限",
        "保修期",
        "维修网点",
        "售后网点",
        "人工客服入口",
        "服务时间",
    ),
    CONTENT_EDITING: (
        "润色",
        "发言稿",
        "翻译成",
        "语法示例",
        "改写",
        "优化结构",
    ),
    HYPOTHETICAL_DISCUSSION: (
        "未来可能",
        "猜测",
        "假设",
        "如果未来",
        "演练",
        "预案",
        "趋势分析",
        "历史投诉",
        "三年前",
    ),
}

_LOOKUP_ACTION_TERMS = ("查询", "咨询", "想知道", "在哪里", "怎么查", "查看", "确认")
_CUSTOMER_SERVICE_OBJECT_TERMS = (
    "客服电话",
    "客服热线",
    "工作时间",
    "服务时间",
    "保修期限",
    "保修期",
    "维修网点",
    "售后网点",
    "人工客服入口",
)
_POLICY_STUDY_TERMS = ("学习", "总结", "解读", "材料", "趋势", "讨论", "分析")
_CONTENT_EDITING_ACTION_TERMS = ("润色", "翻译", "改写", "优化", "发言稿")
_HYPOTHETICAL_TERMS = ("假设", "如果未来", "未来可能", "演练", "预案", "猜测")
_CURRENT_EVENT_TERMS = (
    "当前",
    "已经",
    "已",
    "出现",
    "发生",
    "发现",
    "收到",
    "期间",
    "连续",
    "后",
    "被",
    "多名",
    "大量",
    "正在",
    "近日",
    "开始",
)


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

    negative_intent = _high_confidence_negative_intent(event_text, matched_signals, negative_signals)
    if negative_intent:
        return _result(
            need_rag=False,
            intent=negative_intent,
            decision_score=decision_score,
            matched_signals=matched_signals,
            negative_signals=negative_signals,
            reason=_build_negative_reason(negative_intent),
        )

    if _has_crisis_or_ambiguous_enterprise_risk(event_text, matched_signals):
        return _result(
            need_rag=True,
            intent=CRISIS_RESPONSE_NEEDED,
            decision_score=decision_score,
            matched_signals=matched_signals,
            negative_signals=negative_signals,
            reason=_build_positive_reason(matched_signals),
        )

    if auxiliary_signals and not matched_signals:
        return _result(
            need_rag=False,
            intent=INFORMATION_LOOKUP,
            decision_score=decision_score,
            matched_signals=matched_signals,
            negative_signals=negative_signals,
            reason=(
                "事件文本本身没有体现企业现实风险；draft/redteam 中的危机化表达"
                "不单独触发 RAG。"
            ),
        )

    return _result(
        need_rag=False,
        intent=INFORMATION_LOOKUP,
        decision_score=decision_score,
        matched_signals=matched_signals,
        negative_signals=negative_signals,
        reason="文本缺少企业现实风险、用户影响或危机处置信号，不触发 RAG。",
    )


def _result(
    need_rag: bool,
    intent: str,
    decision_score: int,
    matched_signals: list[str],
    negative_signals: list[str],
    reason: str,
) -> dict:
    return {
        "need_rag": need_rag,
        "intent": intent,
        "decision_score": decision_score,
        "reason": reason,
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
    return [
        signal
        for signal, terms in POSITIVE_SIGNAL_GROUPS.items()
        if _contains_any(text, terms)
    ]


def _matched_negative_signals(text: str) -> list[str]:
    return [
        signal
        for signal, terms in NEGATIVE_SIGNAL_GROUPS.items()
        if _contains_any(text, terms)
    ]


def _positive_signal_weight(signal: str) -> int:
    if signal == "occurred_negative_event":
        return 2
    if signal == "response_or_action_required":
        return 2
    if signal == "harm_or_anomaly":
        return 2
    return 1


def _negative_signal_weight(signal: str) -> int:
    if signal in {UNRELATED, GENERAL_BUSINESS_INFORMATION, CONTENT_EDITING}:
        return 3
    if signal in {POLICY_LOOKUP, CUSTOMER_SERVICE_LOOKUP, HYPOTHETICAL_DISCUSSION}:
        return 2
    return 1


def _high_confidence_negative_intent(
    text: str,
    matched_signals: list[str],
    negative_signals: list[str],
) -> str | None:
    has_risk = _has_crisis_evidence(matched_signals)

    if UNRELATED in negative_signals and not _has_enterprise_context(matched_signals):
        return UNRELATED

    if GENERAL_BUSINESS_INFORMATION in negative_signals and not has_risk:
        return GENERAL_BUSINESS_INFORMATION

    if _is_high_confidence_customer_service_lookup(text, has_risk):
        return CUSTOMER_SERVICE_LOOKUP

    if _is_high_confidence_policy_lookup(text, has_risk):
        return POLICY_LOOKUP

    if _is_high_confidence_content_editing(text, has_risk):
        return CONTENT_EDITING

    if _is_high_confidence_hypothetical(text):
        return HYPOTHETICAL_DISCUSSION

    if _is_high_confidence_information_lookup(text, has_risk):
        return INFORMATION_LOOKUP

    return None


def _is_high_confidence_customer_service_lookup(text: str, has_risk: bool) -> bool:
    return (
        not has_risk
        and _contains_any(text, _LOOKUP_ACTION_TERMS)
        and _contains_any(text, _CUSTOMER_SERVICE_OBJECT_TERMS)
    )


def _is_high_confidence_policy_lookup(text: str, has_risk: bool) -> bool:
    return (
        not has_risk
        and _contains_any(text, NEGATIVE_SIGNAL_GROUPS[POLICY_LOOKUP])
        and (_contains_any(text, _POLICY_STUDY_TERMS) or _contains_any(text, _LOOKUP_ACTION_TERMS))
    )


def _is_high_confidence_content_editing(text: str, has_risk: bool) -> bool:
    return not has_risk and _contains_any(text, _CONTENT_EDITING_ACTION_TERMS)


def _is_high_confidence_hypothetical(text: str) -> bool:
    return _contains_any(text, _HYPOTHETICAL_TERMS) and not _contains_any(text, _CURRENT_EVENT_TERMS)


def _is_high_confidence_information_lookup(text: str, has_risk: bool) -> bool:
    if has_risk:
        return False
    pure_lookup_terms = ("在哪里", "怎么查", "入口", "链接", "名单", "联系方式", "原文", "批次编号")
    return _contains_any(text, _LOOKUP_ACTION_TERMS) and _contains_any(text, pure_lookup_terms)


def _has_crisis_or_ambiguous_enterprise_risk(text: str, matched_signals: list[str]) -> bool:
    if _has_crisis_evidence(matched_signals):
        return True

    has_enterprise = _has_enterprise_context(matched_signals)
    has_public_or_response = bool(
        {"affected_public", "response_or_action_required", "public_spread"} & set(matched_signals)
    )
    if has_enterprise and has_public_or_response:
        return True

    if has_public_or_response and _contains_any(text, _CURRENT_EVENT_TERMS):
        return True

    return False


def _has_crisis_evidence(matched_signals: list[str]) -> bool:
    signals = set(matched_signals)
    if "occurred_negative_event" in signals:
        return True
    if "harm_or_anomaly" in signals and (
        {"affected_public", "response_or_action_required", "public_spread", "enterprise_context"} & signals
    ):
        return True
    if {"affected_public", "response_or_action_required", "public_spread"} <= signals:
        return True
    return False


def _has_enterprise_context(matched_signals: list[str]) -> bool:
    return "enterprise_context" in matched_signals


def _build_positive_reason(matched_signals: list[str]) -> str:
    if "occurred_negative_event" in matched_signals:
        return "事件包含已发生负面事件，并存在用户影响、传播或回应处置需求，放行 RAG。"
    return "无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。"


def _build_negative_reason(intent: str) -> str:
    return f"事件被高置信识别为 {intent}，且缺少当前企业风险或危机处置需求，不触发 RAG。"


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
