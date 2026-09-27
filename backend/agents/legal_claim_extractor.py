"""Identify draft claims that need legal rules or case-specific facts."""

import re
from collections.abc import Callable

from backend.llm.parser import parse_json_response, validate_required_fields
from backend.logger import get_logger


logger = get_logger(__name__)
_SENTENCE_BREAK = re.compile(r"[。！？!?；;\n]+")
_LEGAL_TERMS = ("违法", "违规", "违反", "合法", "合规", "法律", "法规", "规定", "法定", "法律责任")
_CASE_FACT_TERMS = (
    "目前", "经调查", "经核查", "本批次", "该批次", "涉事", "我司", "本公司",
    "已确认", "已经确认", "已证实", "查明", "未使用", "没有使用", "确实使用",
    "已启动核查", "已完成核查", "已经召回", "检测结果", "不存在", "没有违法",
)
_PROMISE_TERMS = ("将依法依规", "将依照法律", "将承担责任", "将积极配合")


def extract_claims(draft: str, mode: str, llm_call: Callable[[str], str] | None = None) -> dict:
    draft = str(draft or "")
    if not draft.strip():
        return {"legal_claims": [], "claim_extraction_status": "ok"}

    if mode == "llm":
        try:
            if llm_call is None:
                raise ValueError("Claim extraction requires the Legal Agent LLM caller.")
            raw = llm_call(_build_prompt(draft))
            parsed = parse_json_response(raw)
            validate_required_fields(parsed, ("claims",))
            claims = _validate_claims(parsed["claims"], draft)
            if not claims and _extract_mock(draft):
                raise ValueError("Claim extraction omitted recognizable claims.")
            return {"legal_claims": claims, "claim_extraction_status": "ok"}
        except Exception as exc:
            logger.warning("Legal claim extraction fallback: %s", exc.__class__.__name__)
            status = "fallback"
    else:
        status = "ok"

    try:
        return {"legal_claims": _extract_mock(draft), "claim_extraction_status": status}
    except Exception as exc:
        logger.warning("Legal claim extraction failed: %s", exc.__class__.__name__)
        return {"legal_claims": [], "claim_extraction_status": "failed"}


def _build_prompt(draft: str) -> str:
    return (
        "从下面的声明草稿中复制需要核验的关键陈述。每条陈述可以同时需要法律规则和企业个案事实。"
        "纯道歉或未来承诺不是本任务的 Claim；不要判断真伪，不要补充草稿中不存在的事实。"
        "只返回 JSON：{\"claims\":[{\"claim\":\"原文片段\","
        "\"requires_legal_rule\":true,\"requires_case_fact\":true}]}。\n"
        f"声明草稿：\n{draft}"
    )


def _validate_claims(value, draft: str) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("claims must be a list.")
    claims = []
    seen = set()
    normalized_draft = _normalize(draft)
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each claim must be an object.")
        validate_required_fields(item, ("claim", "requires_legal_rule", "requires_case_fact"))
        claim = item["claim"]
        legal = item["requires_legal_rule"]
        case_fact = item["requires_case_fact"]
        if not isinstance(claim, str) or not claim.strip() or type(legal) is not bool or type(case_fact) is not bool:
            raise ValueError("Claim text and evidence requirements are invalid.")
        if not (legal or case_fact) or _is_promise_only(claim) or _normalize(claim) not in normalized_draft:
            raise ValueError("A claim must be verifiable and copied from the draft.")
        key = _normalize(claim)
        if key not in seen:
            claims.append({"claim": claim.strip(), "requires_legal_rule": legal, "requires_case_fact": case_fact})
            seen.add(key)
    return claims


def _extract_mock(draft: str) -> list[dict]:
    claims = []
    seen = set()
    for sentence in _SENTENCE_BREAK.split(draft):
        claim = sentence.strip(" \t\r，,。！!？?")
        if not claim or _is_promise_only(claim):
            continue
        legal = any(term in claim for term in _LEGAL_TERMS)
        case_fact = any(term in claim for term in _CASE_FACT_TERMS)
        if not (legal or case_fact):
            continue
        key = _normalize(claim)
        if key not in seen:
            claims.append({"claim": claim, "requires_legal_rule": legal, "requires_case_fact": case_fact})
            seen.add(key)
    return claims


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def _is_promise_only(claim: str) -> bool:
    return claim.startswith(("我们将", "我司将", "本公司将", "将")) and any(
        term in claim for term in _PROMISE_TERMS
    )
