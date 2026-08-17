import re


_ABSOLUTE_COMMITMENTS = ("一定", "绝不", "永远", "保证不会", "百分之百", "100%")
_UNVERIFIED_FACT_TERMS = ("已经确认", "事实证明", "确定为", "坐实", "确认存在违法")
_ILLEGAL_ADMISSION_TERMS = ("我们违法", "承认违法", "违法事实成立", "非法收集", "违规事实成立")
_SKIP_REVIEW_TERMS = ("无需审核", "跳过审核", "直接发布", "不用人工审核")
_PRIVACY_PATTERNS = [
    r"\b1[3-9]\d{9}\b",
    r"\b\d{17}[\dXx]\b",
    r"身份证号[:：]?\s*\d",
    r"手机号[:：]?\s*\d",
]


def evaluate_output_guardrail(statement: str) -> dict:
    text = str(statement or "")
    issues = []

    _append_keyword_issue(issues, text, "absolute_commitment", _ABSOLUTE_COMMITMENTS)
    _append_keyword_issue(issues, text, "unverified_factual_conclusion", _UNVERIFIED_FACT_TERMS)
    _append_keyword_issue(issues, text, "illegal_admission", _ILLEGAL_ADMISSION_TERMS)
    _append_keyword_issue(issues, text, "skip_human_review_hint", _SKIP_REVIEW_TERMS)
    _append_privacy_issue(issues, text)

    return {
        "hit": bool(issues),
        "severity": _resolve_severity(issues),
        "issues": issues,
    }


def _append_keyword_issue(issues: list[dict], text: str, category: str, terms: tuple[str, ...]) -> None:
    matched = [term for term in terms if term in text]
    if matched:
        issues.append(
            {
                "category": category,
                "severity": "high" if category in {"illegal_admission", "skip_human_review_hint"} else "medium",
                "matched_signals": matched,
            }
        )


def _append_privacy_issue(issues: list[dict], text: str) -> None:
    matched = [pattern for pattern in _PRIVACY_PATTERNS if re.search(pattern, text)]
    if matched:
        issues.append(
            {
                "category": "privacy_leak",
                "severity": "high",
                "matched_signals": matched,
            }
        )


def _resolve_severity(issues: list[dict]) -> str:
    if any(issue.get("severity") == "high" for issue in issues):
        return "high"
    if issues:
        return "medium"
    return "none"
