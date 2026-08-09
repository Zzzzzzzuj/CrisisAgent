CRISIS_RESPONSE_NEEDED = "crisis_response_needed"
UNRELATED = "unrelated"
GENERAL_BUSINESS_INFORMATION = "general_business_information"
INFORMATION_LOOKUP = "information_lookup"
POLICY_LOOKUP = "policy_lookup"
CUSTOMER_SERVICE_LOOKUP = "customer_service_lookup"
CONTENT_EDITING = "content_editing"
HYPOTHETICAL_DISCUSSION = "hypothetical_discussion"
TRAINING_LEARNING = "training_learning"
HISTORICAL_ANALYSIS = "historical_analysis"
STATISTICS_REPORTING = "statistics_reporting"
PREPAREDNESS_DRILL = "preparedness_drill"
FUTURE_HYPOTHETICAL = "future_hypothetical"
AMBIGUOUS_ENTERPRISE_RISK = "ambiguous_enterprise_risk"


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
        "事故",
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
        "顾客",
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
        "处置",
        "对外",
        "口径",
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
        "论坛",
        "留言",
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
        "白屏",
        "打不开",
        "扣费",
        "未到账",
        "渗液",
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
        "总部",
        "客服",
        "团队",
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
        "骑行路线",
        "读书笔记",
        "破冰游戏",
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
        "校园招聘",
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
        "归档",
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
        "法规学习",
        "法规培训",
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
        "模板",
        "公告模板",
        "倡议模板",
    ),
    HYPOTHETICAL_DISCUSSION: (
        "未来可能",
        "猜测",
        "假设",
        "如果未来",
        "以后",
        "预案",
        "趋势分析",
    ),
    TRAINING_LEARNING: (
        "培训",
        "内部培训",
        "新人培训",
        "学习",
        "学习提纲",
        "培训材料",
        "内部材料",
    ),
    HISTORICAL_ANALYSIS: (
        "历史",
        "去年",
        "过去一年",
        "过去半年",
        "三年前",
        "复盘",
        "归档",
        "历史案例",
    ),
    STATISTICS_REPORTING: (
        "统计",
        "月报",
        "报表",
        "热度",
        "数量",
        "占比",
        "分类",
    ),
    PREPAREDNESS_DRILL: (
        "演练",
        "应急演练",
        "提前准备",
        "提前梳理",
        "角色分工",
    ),
    FUTURE_HYPOTHETICAL: (
        "如果以后",
        "如果未来",
        "未来出现",
        "未来发生",
        "以后出现",
        "尚未发生",
    ),
}

_NO_CURRENT_TERMS = (
    "目前没有发生",
    "尚未发生",
    "没有真实故障",
    "没有真实事故",
    "目前没有真实",
    "仅用于演练",
    "只是演练",
    "假设未来",
    "如果未来",
    "未来可能",
    "如果以后",
    "猜测",
    "提前准备",
    "过去一年",
    "过去半年",
    "三年前",
    "历史数据",
    "内部培训",
    "学习材料",
)

_CURRENT_OCCURRENCE_TERMS = (
    "当前",
    "现在",
    "已经",
    "已",
    "出现",
    "发生",
    "发现",
    "收到",
    "期间",
    "连续",
    "被",
    "多名",
    "大量",
    "正在",
    "近日",
    "开始",
    "突然",
    "当天",
    "陆续",
    "集中",
)

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
_POLICY_STUDY_TERMS = ("学习", "总结", "解读", "材料", "趋势", "讨论", "分析", "培训")
_CONTENT_EDITING_ACTION_TERMS = ("润色", "翻译", "改写", "优化", "发言稿", "模板")


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

    current_incident_signals = _detect_current_incident(event_text, matched_signals)
    current_incident = bool(current_incident_signals)
    task_intent = _detect_task_intent(event_text, matched_signals, negative_signals)

    if current_incident:
        return _result(
            need_rag=True,
            intent=CRISIS_RESPONSE_NEEDED,
            decision_score=decision_score,
            matched_signals=matched_signals,
            negative_signals=negative_signals,
            reason="检测到当前正在发生或已经发生的现实风险，current_incident 优先于模板、统计、培训等任务词，放行 RAG。",
            current_incident=current_incident,
            current_incident_signals=current_incident_signals,
            task_intent=task_intent,
            decision_path="current_incident_override",
        )

    if _is_high_confidence_non_current_task(task_intent):
        return _result(
            need_rag=False,
            intent=task_intent,
            decision_score=decision_score,
            matched_signals=matched_signals,
            negative_signals=negative_signals,
            reason=f"未检测到当前现实危机，且任务被识别为 {task_intent}，不触发 RAG。",
            current_incident=current_incident,
            current_incident_signals=current_incident_signals,
            task_intent=task_intent,
            decision_path="non_current_task_reject",
        )

    if _has_ambiguous_enterprise_risk(event_text, matched_signals):
        return _result(
            need_rag=True,
            intent=CRISIS_RESPONSE_NEEDED,
            decision_score=decision_score,
            matched_signals=matched_signals,
            negative_signals=negative_signals,
            reason="无法高置信判定为非当前任务，且存在企业风险或用户影响迹象，按 recall-first 策略放行 RAG。",
            current_incident=current_incident,
            current_incident_signals=current_incident_signals,
            task_intent=AMBIGUOUS_ENTERPRISE_RISK,
            decision_path="ambiguous_enterprise_risk_allow",
        )

    if auxiliary_signals and not matched_signals:
        return _result(
            need_rag=False,
            intent=INFORMATION_LOOKUP,
            decision_score=decision_score,
            matched_signals=matched_signals,
            negative_signals=negative_signals,
            reason="事件文本本身没有体现企业现实风险；draft/redteam 中的危机化表达不单独触发 RAG。",
            current_incident=current_incident,
            current_incident_signals=current_incident_signals,
            task_intent=task_intent,
            decision_path="event_first_auxiliary_reject",
        )

    return _result(
        need_rag=False,
        intent=task_intent if task_intent != AMBIGUOUS_ENTERPRISE_RISK else INFORMATION_LOOKUP,
        decision_score=decision_score,
        matched_signals=matched_signals,
        negative_signals=negative_signals,
        reason="文本缺少当前现实危机、用户影响或企业处置需求，不触发 RAG。",
        current_incident=current_incident,
        current_incident_signals=current_incident_signals,
        task_intent=task_intent,
        decision_path="no_current_incident_no_enterprise_risk",
    )


def _result(
    need_rag: bool,
    intent: str,
    decision_score: int,
    matched_signals: list[str],
    negative_signals: list[str],
    reason: str,
    current_incident: bool,
    current_incident_signals: list[str],
    task_intent: str,
    decision_path: str,
) -> dict:
    return {
        "need_rag": need_rag,
        "intent": intent,
        "decision_score": decision_score,
        "reason": reason,
        "matched_signals": matched_signals,
        "negative_signals": negative_signals,
        "current_incident": current_incident,
        "current_incident_signals": current_incident_signals,
        "task_intent": task_intent,
        "decision_path": decision_path,
    }


def _build_auxiliary_text(draft: str, redteam_review: dict | None) -> str:
    parts = [str(draft or "")]
    if isinstance(redteam_review, dict):
        parts.append(str(redteam_review.get("attack_summary", "")))
        parts.append(str(redteam_review.get("issues", [])))
        parts.append(str(redteam_review.get("suggestions", [])))
    return "\n".join(part for part in parts if part)


def _detect_current_incident(text: str, matched_signals: list[str]) -> list[str]:
    if _contains_any(text, _NO_CURRENT_TERMS) and not _has_strong_current_evidence(text, matched_signals):
        return []

    signals = set(matched_signals)
    current_signals = []
    has_current_time = _contains_any(text, _CURRENT_OCCURRENCE_TERMS)
    has_public_or_response = bool({"affected_public", "response_or_action_required", "public_spread"} & signals)
    has_harm = "harm_or_anomaly" in signals

    if has_current_time and ("occurred_negative_event" in signals or has_harm):
        current_signals.append("concrete_event_occurrence")
    if has_current_time and "affected_public" in signals:
        current_signals.append("current_user_impact")
    if has_current_time and has_harm:
        current_signals.append("observed_harm_or_anomaly")
    if "public_spread" in signals and ("occurred_negative_event" in signals or has_harm):
        current_signals.append("ongoing_public_reaction")
    if "response_or_action_required" in signals and (
        "occurred_negative_event" in signals or has_harm or "public_spread" in signals
    ):
        current_signals.append("current_response_need")
    if has_harm and {"affected_public", "enterprise_context"} <= signals:
        current_signals.append("observed_enterprise_user_risk")
    if has_harm and "affected_public" in signals:
        current_signals.append("observed_user_harm")
    if {"affected_public", "response_or_action_required", "public_spread"} <= signals:
        current_signals.append("public_response_pressure")

    return _dedupe(current_signals)


def _has_strong_current_evidence(text: str, matched_signals: list[str]) -> bool:
    signals = set(matched_signals)
    if _contains_any(text, ("当前", "现在", "已经", "已", "正在", "立即", "当天")) and (
        "affected_public" in signals or "harm_or_anomaly" in signals or "occurred_negative_event" in signals
    ):
        return True
    if "多名" in text and ("用户" in text or "消费者" in text or "家长" in text):
        return True
    return False


def _detect_task_intent(text: str, matched_signals: list[str], negative_signals: list[str]) -> str:
    has_risk = bool({"occurred_negative_event", "harm_or_anomaly"} & set(matched_signals))

    if UNRELATED in negative_signals and "enterprise_context" not in matched_signals:
        return UNRELATED
    if GENERAL_BUSINESS_INFORMATION in negative_signals and not has_risk:
        return GENERAL_BUSINESS_INFORMATION
    if _is_customer_service_lookup(text, has_risk):
        return CUSTOMER_SERVICE_LOOKUP
    if _is_content_editing(text, has_risk):
        return CONTENT_EDITING
    if _is_preparedness(text):
        return PREPAREDNESS_DRILL
    if _is_future_hypothetical(text):
        return FUTURE_HYPOTHETICAL
    if _is_statistics_reporting(text):
        return STATISTICS_REPORTING
    if _is_historical_analysis(text):
        return HISTORICAL_ANALYSIS
    if _is_training_learning(text):
        return TRAINING_LEARNING
    if _is_policy_learning(text, has_risk):
        return POLICY_LOOKUP
    if _is_information_lookup(text, has_risk):
        return INFORMATION_LOOKUP
    return AMBIGUOUS_ENTERPRISE_RISK


def _is_high_confidence_non_current_task(task_intent: str) -> bool:
    return task_intent in {
        UNRELATED,
        GENERAL_BUSINESS_INFORMATION,
        INFORMATION_LOOKUP,
        CUSTOMER_SERVICE_LOOKUP,
        POLICY_LOOKUP,
        CONTENT_EDITING,
        HYPOTHETICAL_DISCUSSION,
        TRAINING_LEARNING,
        HISTORICAL_ANALYSIS,
        STATISTICS_REPORTING,
        PREPAREDNESS_DRILL,
        FUTURE_HYPOTHETICAL,
    }


def _has_ambiguous_enterprise_risk(text: str, matched_signals: list[str]) -> bool:
    signals = set(matched_signals)
    if {"enterprise_context", "affected_public"} <= signals:
        return True
    if {"enterprise_context", "response_or_action_required"} <= signals:
        return True
    if {"affected_public", "response_or_action_required"} <= signals and _contains_any(text, _CURRENT_OCCURRENCE_TERMS):
        return True
    return False


def _is_customer_service_lookup(text: str, has_risk: bool) -> bool:
    return (
        not has_risk
        and _contains_any(text, _LOOKUP_ACTION_TERMS)
        and _contains_any(text, _CUSTOMER_SERVICE_OBJECT_TERMS)
    )


def _is_policy_learning(text: str, has_risk: bool) -> bool:
    return (
        not has_risk
        and _contains_any(text, NEGATIVE_SIGNAL_GROUPS[POLICY_LOOKUP])
        and (_contains_any(text, _POLICY_STUDY_TERMS) or _contains_any(text, _LOOKUP_ACTION_TERMS))
    )


def _is_content_editing(text: str, has_risk: bool) -> bool:
    return _contains_any(text, _CONTENT_EDITING_ACTION_TERMS)


def _is_preparedness(text: str) -> bool:
    return _contains_any(text, NEGATIVE_SIGNAL_GROUPS[PREPAREDNESS_DRILL])


def _is_future_hypothetical(text: str) -> bool:
    return _contains_any(text, NEGATIVE_SIGNAL_GROUPS[FUTURE_HYPOTHETICAL]) or _contains_any(text, ("如果未来", "未来可能", "假设未来"))


def _is_historical_analysis(text: str) -> bool:
    return _contains_any(text, NEGATIVE_SIGNAL_GROUPS[HISTORICAL_ANALYSIS])


def _is_statistics_reporting(text: str) -> bool:
    return _contains_any(text, NEGATIVE_SIGNAL_GROUPS[STATISTICS_REPORTING])


def _is_training_learning(text: str) -> bool:
    return _contains_any(text, NEGATIVE_SIGNAL_GROUPS[TRAINING_LEARNING])


def _is_information_lookup(text: str, has_risk: bool) -> bool:
    if has_risk:
        return False
    pure_lookup_terms = ("在哪里", "怎么查", "入口", "链接", "名单", "联系方式", "原文", "批次编号")
    return _contains_any(text, _LOOKUP_ACTION_TERMS) and _contains_any(text, pure_lookup_terms)


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


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _dedupe(items: list[str]) -> list[str]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
