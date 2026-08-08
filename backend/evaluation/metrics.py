ABSOLUTE_PROMISE_TERMS = ("一定", "绝不", "保证", "永远", "全部负责")
PREMATURE_FACT_TERMS = ("已经确认", "确认存在", "事实属实", "确实使用", "公司承认", "违规事实")
INVESTIGATION_TERMS = ("调查", "核查", "排查", "专项核查", "查明")
REGULATOR_TERMS = ("监管", "配合监管", "监管部门")
EMPATHY_TERMS = ("关注", "重视", "理解", "关切", "担忧", "不安")
PUBLIC_TERMS = ("公众", "消费者", "用户", "网友", "客户")
APOLOGY_TERMS = ("歉意", "抱歉", "道歉", "解释")
RECTIFICATION_TERMS = ("整改", "处理", "改进", "纠正", "召回", "下架")
UPDATE_TERMS = ("更新", "同步", "进展", "持续", "公布")


def score_legal_safety(final_statement: str) -> dict:
    score = 10
    issues = []
    suggestions = []

    premature_hits = _hits(final_statement, PREMATURE_FACT_TERMS)
    if premature_hits:
        score -= 4
        issues.append(f"存在提前确认事实或定责表达: {', '.join(premature_hits)}")
        suggestions.append("将事实判断改为条件式表达，例如“如经核查属实”。")

    absolute_hits = _hits(final_statement, ABSOLUTE_PROMISE_TERMS)
    if absolute_hits:
        score -= 3
        issues.append(f"存在绝对化承诺: {', '.join(absolute_hits)}")
        suggestions.append("避免使用“一定、绝不、保证”等绝对化承诺。")

    if not _contains_any(final_statement, INVESTIGATION_TERMS):
        score -= 3
        issues.append("缺少调查/核查/排查描述")
        suggestions.append("补充已启动调查、核查或排查的行动说明。")

    if not _contains_any(final_statement, REGULATOR_TERMS):
        score -= 1
        suggestions.append("如涉及监管关注，可说明将积极配合监管部门。")

    return _metric_result(score, issues, suggestions)


def score_empathy(final_statement: str) -> dict:
    score = 0
    issues = []
    suggestions = []

    if _contains_any(final_statement, EMPATHY_TERMS):
        score += 4
    else:
        issues.append("缺少对公众关切或担忧的回应")
        suggestions.append("开头应先表达关注、重视或理解公众担忧。")

    if _contains_any(final_statement, PUBLIC_TERMS):
        score += 3
    else:
        issues.append("缺少消费者/用户/公众视角")
        suggestions.append("明确回应消费者、用户或公众的关注点。")

    if _contains_any(final_statement, APOLOGY_TERMS):
        score += 3
    else:
        issues.append("缺少歉意或解释表达")
        suggestions.append("在不提前定责的前提下表达歉意或解释后续沟通安排。")

    return _metric_result(score, issues, suggestions)


def score_robustness(results: dict, final_statement: str, agent_trace: list[dict]) -> dict:
    score = 5
    issues = []
    suggestions = []

    redteam_review = results.get("redteam", {})
    redteam_suggestions = redteam_review.get("suggestions", [])
    writer_v2_result = results.get("writer_v2", {})

    if redteam_suggestions and _statement_addresses_redteam(final_statement, redteam_suggestions):
        score += 2
    elif redteam_suggestions:
        issues.append("未明显吸收 redteam 建议")
        suggestions.append("将 redteam 建议转化为声明中的具体动作或沟通安排。")

    if _contains_any(final_statement, RECTIFICATION_TERMS):
        score += 2
    else:
        issues.append("缺少整改/处理/改进动作")
        suggestions.append("补充整改、处理或改进机制。")

    if writer_v2_result or _trace_has_agent(agent_trace, "writer_v2"):
        score += 1
    else:
        issues.append("缺少 writer_v2 第二版修改结果")
        suggestions.append("确保 decision 使用经过 legal/redteam 后的 writer_v2 second_draft。")

    return _metric_result(score, issues, suggestions)


def _statement_addresses_redteam(final_statement: str, redteam_suggestions: list) -> bool:
    if _contains_any(final_statement, UPDATE_TERMS + INVESTIGATION_TERMS + RECTIFICATION_TERMS):
        return True

    suggestion_text = " ".join(str(item) for item in redteam_suggestions)
    useful_terms = ("更新", "调查", "核查", "整改", "监管", "回应", "行动")
    return any(term in final_statement and term in suggestion_text for term in useful_terms)


def _trace_has_agent(agent_trace: list[dict], agent_name: str) -> bool:
    return any(item.get("agent") == agent_name and item.get("status") == "success" for item in agent_trace)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _metric_result(score: int, issues: list[str], suggestions: list[str]) -> dict:
    return {
        "score": max(0, min(10, int(score))),
        "issues": issues,
        "suggestions": suggestions,
    }
