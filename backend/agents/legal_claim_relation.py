"""Observe candidate legal-rule relevance without deciding claim truth."""

import hashlib
import json
from collections.abc import Callable

from backend.llm.parser import parse_json_response
from backend.logger import get_logger


logger = get_logger(__name__)
RELATIONS = {"candidate_rule_relevant", "no_rule_match", "uncertain"}
UNCERTAIN_REASONS = {"claim_context_insufficient", "semantic_relation_unclear"}
_RULE_MARKERS = ("不得", "禁止", "严禁", "应当", "必须", "违反")
_TOPICS = {
    "food_expiry": (("过期", "保质期"), ("食品", "原料", "食材", "食物", "餐饮")),
    "privacy": (("个人信息", "隐私", "泄露"), ()),
    "recall": (("召回",), ("产品", "商品", "食品")),
}


class _InvalidEvidenceRef(ValueError):
    pass


def evidence_ref(chunk: dict) -> str | None:
    chunk_id = chunk.get("chunk_id")
    if isinstance(chunk_id, str) and chunk_id.strip():
        return chunk_id.strip()
    source, content = chunk.get("source"), chunk.get("text")
    if not isinstance(source, str) or not source.strip() or not isinstance(content, str) or not content.strip():
        return None
    digest = hashlib.sha256(f"{source}\0{content}".encode("utf-8")).hexdigest()
    return f"content:{digest}"


def build_legal_claim_relations(
    claims: list[dict], chunks: list[dict], *, mode: str = "mock",
    llm_call: Callable[[str], str] | None = None,
) -> dict:
    eligible = [(index, item["claim"].strip()) for index, item in enumerate(claims or [])
                if isinstance(item, dict) and item.get("requires_legal_rule") is True
                and isinstance(item.get("claim"), str) and item["claim"].strip()]
    if not eligible or not chunks:
        return {"legal_claim_relations": [], "relation_status": "skipped"}

    evidence: dict[str, dict] = {}
    conflicts: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        ref = evidence_ref(chunk)
        if ref is None:
            continue
        previous = evidence.get(ref)
        if previous is not None and (previous.get("source"), previous.get("text")) != (
            chunk.get("source"), chunk.get("text")
        ):
            conflicts.add(ref)
        else:
            evidence[ref] = chunk
    if not evidence:
        return {"legal_claim_relations": [], "relation_status": "fallback",
                "relation_status_reason": "invalid_evidence_ref"}

    pairs = [(index, claim, ref, chunk) for index, claim in eligible for ref, chunk in evidence.items()]
    if mode == "llm":
        try:
            if llm_call is None:
                raise ValueError("The Legal Agent LLM caller is required.")
            raw = llm_call(_batch_prompt(eligible, evidence))
        except Exception as exc:
            logger.warning("Legal claim relation execution fallback: %s", exc.__class__.__name__)
            return _module_fallback(pairs, "execution_error")
        try:
            decisions = _parse_batch(raw, {(index, ref) for index, _, ref, _ in pairs})
        except _InvalidEvidenceRef as exc:
            logger.warning("Legal claim relation invalid evidence ref: %s", exc.__class__.__name__)
            return _module_fallback(pairs, "invalid_evidence_ref")
        except Exception as exc:
            logger.warning("Legal claim relation invalid output: %s", exc.__class__.__name__)
            return _module_fallback(pairs, "invalid_output")
        try:
            rows = []
            for index, claim, ref, chunk in pairs:
                decision, reason = decisions[index, ref]
                if ref in conflicts:
                    decision, reason = "uncertain", None
                elif _vague(claim):
                    decision, reason = "uncertain", "claim_context_insufficient"
                elif decision == "candidate_rule_relevant":
                    if not _has_rule_text(chunk.get("text")):
                        decision, reason = "no_rule_match", None
                    elif _deterministic_relation(claim, chunk.get("text")) == "no_rule_match":
                        decision, reason = "no_rule_match", None
                rows.append(_relation(index, ref, decision, reason))
            result = {
                "legal_claim_relations": rows,
                "relation_status": "ok" if not conflicts else "fallback",
            }
            if conflicts:
                result["relation_status_reason"] = "invalid_evidence_ref"
            return result
        except Exception as exc:
            logger.warning("Legal claim relation execution fallback: %s", exc.__class__.__name__)
            return _module_fallback(pairs, "execution_error")

    try:
        rows = []
        for index, claim, ref, chunk in pairs:
            decision = "uncertain" if ref in conflicts else _deterministic_relation(claim, chunk.get("text"))
            reason = None if ref in conflicts else _uncertain_reason(claim, decision)
            rows.append(_relation(index, ref, decision, reason))
        result = {"legal_claim_relations": rows, "relation_status": "fallback" if conflicts else "ok"}
        if conflicts:
            result["relation_status_reason"] = "invalid_evidence_ref"
        return result
    except Exception as exc:
        logger.warning("Legal claim relation execution fallback: %s", exc.__class__.__name__)
        return _module_fallback(pairs, "execution_error")


def _relation(index: int, ref: str, relation: str, reason: str | None = None) -> dict:
    row = {"claim_index": index, "evidence_ref": ref, "relation": relation}
    if relation == "uncertain" and reason is not None:
        row["reason"] = reason
    return row


def _uncertain_reason(claim: str, relation: str) -> str | None:
    if relation != "uncertain":
        return None
    return "claim_context_insufficient" if _vague(claim) else "semantic_relation_unclear"


def _module_fallback(pairs: list[tuple], reason: str) -> dict:
    return {
        "legal_claim_relations": [_relation(index, ref, "uncertain") for index, _, ref, _ in pairs],
        "relation_status": "fallback",
        "relation_status_reason": reason,
    }


def _batch_prompt(claims: list[tuple[int, str]], evidence: dict[str, dict]) -> str:
    data = {
        "claims": [{"claim_index": index, "claim": claim} for index, claim in claims],
        "evidence": [{"evidence_ref": ref, "text": str(chunk.get("text") or "")[:1500]}
                     for ref, chunk in evidence.items()],
    }
    return (
        "只判断候选规则文本与每条声明的法律问题是否相关，不判断企业事实、违法与否、法律效力或整条声明真假。"
        "每个 claim_index × evidence_ref 必须且只能返回一条记录；不添加其他字段。"
        "relation 仅允许 candidate_rule_relevant、no_rule_match、uncertain；"
        "仅 uncertain 必须附加 reason，值只能是 claim_context_insufficient 或 semantic_relation_unclear；"
        "其他 relation 不得附加 reason；"
        "含义不明确或只有危机沟通建议时，分别返回 uncertain、no_rule_match。"
        "仅返回 JSON 对象：{\"relations\":[{\"claim_index\":0,\"evidence_ref\":\"...\","
        "\"relation\":\"uncertain\",\"reason\":\"semantic_relation_unclear\"}]}。\n"
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    )


def _parse_batch(raw: str, expected: set[tuple[int, str]]) -> dict[tuple[int, str], tuple[str, str | None]]:
    parsed = parse_json_response(raw)
    if set(parsed) != {"relations"} or not isinstance(parsed["relations"], list):
        raise ValueError("Unexpected relation response fields.")
    decisions: dict[tuple[int, str], tuple[str, str | None]] = {}
    for item in parsed["relations"]:
        if not isinstance(item, dict) or not {"claim_index", "evidence_ref", "relation"} <= set(item):
            raise ValueError("Unexpected relation fields.")
        index, ref, relation = item["claim_index"], item["evidence_ref"], item["relation"]
        if type(index) is not int:
            raise ValueError("Relation references an unknown claim.")
        if not isinstance(ref, str) or ref not in {expected_ref for _, expected_ref in expected}:
            raise _InvalidEvidenceRef("Relation references an unknown evidence chunk.")
        if (index, ref) not in expected:
            raise ValueError("Relation references an unknown claim-evidence pair.")
        if not isinstance(relation, str) or relation not in RELATIONS or (index, ref) in decisions:
            raise ValueError("Invalid or duplicate relation decision.")
        if relation == "uncertain":
            if set(item) != {"claim_index", "evidence_ref", "relation", "reason"} or item["reason"] not in UNCERTAIN_REASONS:
                raise ValueError("Uncertain relation requires a valid reason.")
            reason = item["reason"]
        else:
            if set(item) != {"claim_index", "evidence_ref", "relation"}:
                raise ValueError("Decided relation cannot carry an uncertain reason.")
            reason = None
        decisions[index, ref] = relation, reason
    if set(decisions) != expected:
        raise ValueError("The batch response omitted claim-evidence pairs.")
    return decisions


def _deterministic_relation(claim: str, text: object) -> str:
    if _vague(claim) or not isinstance(text, str) or not text.strip():
        return "uncertain"
    if not _has_rule_text(text):
        return "no_rule_match"
    claim_topics = _topics(claim)
    evidence_topics = _topics(text)
    if claim_topics & evidence_topics:
        return "candidate_rule_relevant"
    return "no_rule_match" if claim_topics and evidence_topics else "uncertain"


def _has_rule_text(text: object) -> bool:
    if not isinstance(text, str) or not any(marker in text for marker in _RULE_MARKERS):
        return False
    if any(phrase in text for phrase in ("声明应当", "回应应当", "沟通应当")) and not any(
        term in text for term in ("法律", "法规", "条例", "监管", "食品安全", "个人信息")
    ):
        return False
    return True


def _topics(text: str) -> set[str]:
    return {name for name, (issue_terms, domain_terms) in _TOPICS.items()
            if any(term in text for term in issue_terms)
            and (not domain_terms or any(term in text for term in domain_terms))}


def _vague(claim: str) -> bool:
    return (any(term in claim for term in ("不存在违法行为", "没有违法行为", "未违法"))
            and not _topics(claim))
