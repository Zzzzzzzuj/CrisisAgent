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
_FACT_GAP_MARKERS = ("尚未确认", "尚未证实", "尚未查明", "尚不清楚", "仍未确认", "仍待确认", "尚待确认")
_MATERIAL_UNKNOWN_MARKERS = ("是否", "多少", "原因", "范围", "哪些", "影响", "何时", "何处", "为何", "哪一")


def extract_claims(
    draft: str,
    mode: str,
    llm_call: Callable[[str], str] | None = None,
    *,
    event: str = "",
    risk_level: str | None = None,
) -> dict:
    draft = str(draft or "")
    event = str(event or "")
    if not draft.strip() and not event.strip():
        return {"legal_claims": [], "claim_extraction_status": "ok"}

    if mode == "llm":
        try:
            if llm_call is None:
                raise ValueError("Claim extraction requires the Legal Agent LLM caller.")
            raw = llm_call(_build_prompt(draft, event, risk_level))
            parsed = parse_json_response(raw)
            validate_required_fields(parsed, ("claims",))
            claims = _validate_claims(parsed["claims"], draft, event)
            deterministic_claims = _combine_claims(draft, event, risk_level)
            if not claims and deterministic_claims:
                raise ValueError("Claim extraction omitted recognizable claims.")
            claims = _merge_claims(
                claims,
                [item for item in deterministic_claims if item.get("claim_origin") == "event_fact_gap"],
            )
            return _result(claims, "ok", mode, event, risk_level)
        except Exception as exc:
            logger.warning("Legal claim extraction fallback: %s", exc.__class__.__name__)
            status = "fallback"
    else:
        status = "ok"

    try:
        return _result(_combine_claims(draft, event, risk_level), status, mode, event, risk_level)
    except Exception as exc:
        logger.warning("Legal claim extraction failed: %s", exc.__class__.__name__)
        result = {"legal_claims": [], "claim_extraction_status": "failed"}
        if event:
            result["event_fact_gap_detection"] = {"status": "failed", "candidate_count": 0}
        return result


def _build_prompt(draft: str, event: str = "", risk_level: str | None = None) -> str:
    return (
        "从原始事件和声明草稿中识别需要法律规则或企业个案事实核验的关键陈述。"
        "额外识别事件中明确尚未确认、且会影响当前回应或风险处置的个案事实缺口；"
        "不要把一般不确定措辞都变成问题，不要把法律资料当作企业事实证据。"
        "事件来源项必须复制自事件原文，claim_origin 必须为 event_fact_gap，"
        "requires_case_fact 必须为 true；草稿来源项必须复制自草稿原文，claim_origin 可为 writer_draft。"
        "不要判断事实真伪，不要生成原文没有的事实。纯道歉和未来承诺不是 Claim。"
        "只返回 JSON：{\"claims\":[{\"claim\":\"原文片段\","
        "\"requires_legal_rule\":false,\"requires_case_fact\":true,"
        "\"claim_origin\":\"event_fact_gap\"}]}。\n"
        f"风险等级：{risk_level or 'unknown'}\n原始事件：\n{event}\n声明草稿：\n{draft}\n"
        "当前没有可信、逐 Claim 的企业个案事实核验来源。Legal RAG 只提供规则候选材料，不能填补该事实缺口。"
    )


def _validate_claims(value, draft: str, event: str = "") -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("claims must be a list.")
    claims = []
    seen = set()
    normalized_draft = _normalize(draft)
    normalized_event = _normalize(event)
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each claim must be an object.")
        validate_required_fields(item, ("claim", "requires_legal_rule", "requires_case_fact"))
        claim = item["claim"]
        legal = item["requires_legal_rule"]
        case_fact = item["requires_case_fact"]
        origin = item.get("claim_origin", "writer_draft")
        if not isinstance(claim, str) or not claim.strip() or type(legal) is not bool or type(case_fact) is not bool:
            raise ValueError("Claim text and evidence requirements are invalid.")
        normalized_claim = _normalize(claim)
        if origin == "event_fact_gap":
            source_matches = bool(normalized_event and normalized_claim in normalized_event)
            valid_origin = case_fact and not legal
        elif origin == "writer_draft":
            source_matches = bool(normalized_draft and normalized_claim in normalized_draft)
            valid_origin = True
        else:
            source_matches = False
            valid_origin = False
        if (not (legal or case_fact) or _is_promise_only(claim) or not source_matches
                or not valid_origin):
            raise ValueError("A claim must be verifiable and copied from its declared source.")
        key = (origin, normalized_claim)
        if key not in seen:
            normalized = {"claim": claim.strip(), "requires_legal_rule": legal,
                          "requires_case_fact": case_fact}
            if origin == "event_fact_gap":
                normalized["claim_origin"] = origin
            claims.append(normalized)
            seen.add(key)
    return claims


def _result(claims: list[dict], status: str, mode: str, event: str, risk_level: str | None) -> dict:
    result = {"legal_claims": claims, "claim_extraction_status": status}
    if event:
        candidates = [item for item in claims if item.get("claim_origin") == "event_fact_gap"]
        result["event_fact_gap_detection"] = {
            "status": ("deterministic_offline_rule" if mode != "llm" else
                       "llm_structured_with_offline_rule" if status == "ok" else "deterministic_fallback"),
            "candidate_count": len(candidates),
            "reason": "explicit_material_uncertainty" if candidates else "no_eligible_gap",
            "risk_level": risk_level or "unknown",
        }
    return result


def _combine_claims(draft: str, event: str, risk_level: str | None) -> list[dict]:
    return _merge_claims(_extract_mock(draft), _extract_event_fact_gaps(event, risk_level))


def _merge_claims(claims: list[dict], additions: list[dict]) -> list[dict]:
    claims = list(claims)
    seen = {(item.get("claim_origin", "writer_draft"), _normalize(item["claim"])) for item in claims}
    for item in additions:
        key = (item.get("claim_origin", "writer_draft"), _normalize(item["claim"]))
        if key not in seen:
            claims.append(item)
            seen.add(key)
    return claims


def _extract_event_fact_gaps(event: str, risk_level: str | None) -> list[dict]:
    """Offline heuristic for explicit, material unknowns; risk is handled downstream."""
    if not event:
        return []
    candidates = []
    for sentence in _SENTENCE_BREAK.split(event):
        sentence = sentence.strip(" \t\r，,")
        if not sentence or not any(marker in sentence for marker in _FACT_GAP_MARKERS):
            continue
        # Only enumerate concrete unknown dimensions (whether, scope, cause, impact, etc.).
        if not any(marker in sentence for marker in _MATERIAL_UNKNOWN_MARKERS):
            continue
        start = max((sentence.rfind(marker) for marker in _FACT_GAP_MARKERS), default=-1)
        detail = sentence[start + len(next(marker for marker in _FACT_GAP_MARKERS
                                             if sentence.startswith(marker, start))):].strip(" ：:，,")
        if not detail:
            continue
        candidates.append({"claim": detail, "requires_legal_rule": False,
                           "requires_case_fact": True, "claim_origin": "event_fact_gap"})
    return candidates


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
