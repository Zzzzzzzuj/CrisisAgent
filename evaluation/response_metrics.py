import re


LEGAL_RISK_PATTERNS = {
    "premature_liability": ["确认违法", "已经违法", "全部属实", "确实违规", "承担全部责任"],
    "absolute_promise": ["一定赔偿", "永久补偿", "保证不会", "绝不发生", "所有损失"],
}
CONDITIONAL_TERMS = ["如核查属实", "若情况属实", "经核查", "在事实查明后", "依法依规"]
REGULATOR_ACTION_TERMS = ["配合监管", "监管部门", "监管要求", "接受监管"]
INVESTIGATION_TERMS = ["调查", "核查", "排查", "专项核查"]
EMPATHY_TERMS = ["关注", "关切", "担忧", "歉意", "重视", "理解", "消费者", "用户"]
CONSUMER_TERMS = ["消费者", "用户", "公众", "客户"]
APOLOGY_TERMS = ["歉意", "道歉", "深表歉意", "诚挚歉意", "重视"]
RECTIFICATION_TERMS = ["整改", "改进", "优化", "处理", "纠正"]
UPDATE_TERMS = ["持续更新", "及时同步", "进展", "后续", "公布"]
STRUCTURE_TERMS = ["第一时间", "同时", "目前", "后续", "如核查属实", "再次"]


def evaluate_response_quality(final_statement: str, event: str, case: dict | None = None) -> dict:
    case = case or {}
    legal = score_legal_safety(final_statement)
    empathy = score_empathy(final_statement)
    action = score_action_completeness(final_statement)
    clarity = score_communication_clarity(final_statement, case)
    hallucination = score_hallucination_risk(final_statement, event, case)

    scores = {
        "legal_safety": legal["score"],
        "empathy": empathy["score"],
        "action_completeness": action["score"],
        "communication_clarity": clarity["score"],
        "hallucination_risk": hallucination["score"],
    }
    issues = (
        legal["issues"]
        + empathy["issues"]
        + action["issues"]
        + clarity["issues"]
        + hallucination["issues"]
    )

    return {
        "scores": scores,
        "pass": _is_pass(scores),
        "issues": issues,
        "details": {
            "legal_safety": legal,
            "empathy": empathy,
            "action_completeness": action,
            "communication_clarity": clarity,
            "hallucination_risk": hallucination,
        },
    }


def score_legal_safety(statement: str) -> dict:
    score = 10
    issues = []

    risk_hits = _find_pattern_hits(statement, LEGAL_RISK_PATTERNS["premature_liability"])
    if risk_hits:
        score -= 4
        issues.append(f"提前定责风险: {', '.join(risk_hits)}")

    promise_hits = _find_pattern_hits(statement, LEGAL_RISK_PATTERNS["absolute_promise"])
    if promise_hits:
        score -= 3
        issues.append(f"绝对化承诺风险: {', '.join(promise_hits)}")

    if not _contains_any(statement, CONDITIONAL_TERMS):
        score -= 2
        issues.append("缺少条件式或依法依规表达")

    if not _contains_any(statement, REGULATOR_ACTION_TERMS + INVESTIGATION_TERMS):
        score -= 2
        issues.append("缺少监管配合或核查行动表达")

    return {"score": _clamp_score(score), "issues": issues}


def score_empathy(statement: str) -> dict:
    score = 0
    issues = []

    if _contains_any(statement, EMPATHY_TERMS):
        score += 4
    else:
        issues.append("缺少公众关切或担忧回应")

    if _contains_any(statement, CONSUMER_TERMS):
        score += 3
    else:
        issues.append("缺少消费者/用户视角")

    if _contains_any(statement, APOLOGY_TERMS):
        score += 3
    else:
        issues.append("缺少歉意或重视表达")

    return {"score": _clamp_score(score), "issues": issues}


def score_action_completeness(statement: str) -> dict:
    checks = {
        "调查/核查": INVESTIGATION_TERMS,
        "整改/处理": RECTIFICATION_TERMS,
        "配合监管": REGULATOR_ACTION_TERMS,
        "后续更新": UPDATE_TERMS,
    }
    score = 0
    issues = []

    for label, terms in checks.items():
        if _contains_any(statement, terms):
            score += 2.5
        else:
            issues.append(f"缺少{label}动作")

    return {"score": _clamp_score(score), "issues": issues}


def score_communication_clarity(statement: str, case: dict | None = None) -> dict:
    case = case or {}
    score = 10
    issues = []
    length = len(statement)

    if length < 80:
        score -= 3
        issues.append("声明过短，可能缺少必要信息")
    elif length > 800:
        score -= 2
        issues.append("声明过长，可能影响公众理解")

    if not _contains_any(statement, STRUCTURE_TERMS):
        score -= 2
        issues.append("缺少清晰的回应结构提示词")

    missing_required = [
        keyword for keyword in case.get("must_include", []) if keyword not in statement
    ]
    if missing_required:
        score -= min(4, len(missing_required))
        issues.append(f"缺少案例要求关键词: {', '.join(missing_required)}")

    forbidden_hits = [
        keyword for keyword in case.get("must_avoid", []) if keyword in statement
    ]
    if forbidden_hits:
        score -= min(4, len(forbidden_hits) * 2)
        issues.append(f"包含禁用表达: {', '.join(forbidden_hits)}")

    return {"score": _clamp_score(score), "issues": issues}


def score_hallucination_risk(statement: str, event: str, case: dict | None = None) -> dict:
    case = case or {}
    supported_text = " ".join([event] + case.get("supported_facts", []))
    unsupported_facts = _find_unsupported_specific_facts(statement, supported_text)

    if not unsupported_facts:
        return {"score": 0, "issues": [], "unsupported_facts": []}

    score = min(10, len(unsupported_facts) * 2)
    return {
        "score": score,
        "issues": [f"可能存在未被输入事件支持的具体事实: {', '.join(unsupported_facts)}"],
        "unsupported_facts": unsupported_facts,
    }


def summarize_response_results(case_results: list[dict]) -> dict:
    if not case_results:
        return {
            "total_cases": 0,
            "pass_rate": 0.0,
            "average_scores": _empty_average_scores(),
        }

    return {
        "total_cases": len(case_results),
        "pass_rate": round(
            sum(1 for item in case_results if item["response_evaluation"]["pass"]) / len(case_results),
            4,
        ),
        "average_scores": {
            key: round(
                sum(item["response_evaluation"]["scores"][key] for item in case_results)
                / len(case_results),
                2,
            )
            for key in _empty_average_scores()
        },
    }


def _is_pass(scores: dict) -> bool:
    return (
        scores["legal_safety"] >= 7
        and scores["empathy"] >= 6
        and scores["action_completeness"] >= 6
        and scores["communication_clarity"] >= 6
        and scores["hallucination_risk"] <= 4
    )


def _empty_average_scores() -> dict:
    return {
        "legal_safety": 0.0,
        "empathy": 0.0,
        "action_completeness": 0.0,
        "communication_clarity": 0.0,
        "hallucination_risk": 0.0,
    }


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _find_pattern_hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in text]


def _find_unsupported_specific_facts(statement: str, supported_text: str) -> list[str]:
    candidates = set()
    for pattern in [
        r"\d+(?:\.\d+)?%",
        r"\d+(?:\.\d+)?万",
        r"\d+(?:\.\d+)?元",
        r"\d{4}年\d{1,2}月\d{1,2}日",
        r"\d{1,2}月\d{1,2}日",
        r"[A-Z][A-Za-z0-9_-]{2,}",
    ]:
        candidates.update(re.findall(pattern, statement))

    unsupported = [
        candidate
        for candidate in sorted(candidates)
        if candidate not in supported_text
    ]
    return unsupported


def _clamp_score(score: float) -> int:
    return int(max(0, min(10, round(score))))
