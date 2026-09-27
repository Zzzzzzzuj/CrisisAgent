"""A single, claim-scoped human fact pause and continuation for Dynamic Runtime."""

from copy import deepcopy
from hashlib import sha256
import re
from uuid import uuid4

from backend.agents.legal_action_policy import REQUEST_HUMAN_FACT_VERIFICATION
from backend.agents.legal_claim_extractor import extract_claims
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.core.state import RUNNING, WAITING_HUMAN


FACT_KEY = "human_fact"
FACT_INPUT = "FACT_INPUT"
FINAL_REVIEW = "FINAL_REVIEW"
PHASE_PENDING = "PENDING"
PHASE_RESPONSE_RECORDED = "RESPONSE_RECORDED"
PHASE_CONTINUING = "CONTINUING"
PHASE_COMPLETED = "COMPLETED"
_DEFINITE = re.compile(r"不存在|没有|并未|未曾|未使用|绝无|均未|都未|未见|不含|未检出|已经确认|经调查确认|确实|属实|不涉及|未发现|符合|合格|正常|安全|均为|都为|在保质期")
_SAFE_UNCERTAINTY = re.compile(
    r"(?:事实|情况|结果)(?:目前|尚|仍|暂)?(?:尚未|尚待|仍在|仍需|暂未|暂无法|还需|进一步确认|核实|调查|核查)|"
    r"(?:调查|核查|核实)(?:工作)?(?:仍在进行|尚未完成|仍需继续|正在进行)|"
    r"目前(?:相关)?事实仍在进一步确认|目前尚无法确认"
)
_NON_TOPIC_BIGRAMS = {"经调", "本批", "次不", "存在", "使用", "的情", "情况", "调查", "核查"}


def pause_for_claim(state, remaining_plan: list[dict]) -> bool:
    extraction = state.metadata.get("legal_claim_extraction") or {}
    coverage = (state.metadata.get("legal_claim_coverage") or {}).get("claim_coverage", [])
    recommendations = (state.metadata.get("legal_claim_action_recommendation") or {}).get("claim_action_recommendations", [])
    claims = extraction.get("legal_claims", [])
    draft = str((state.get_result("writer") or {}).get("statement", ""))
    if not isinstance(claims, list) or not isinstance(coverage, list) or not isinstance(recommendations, list):
        return False
    if state.metadata.get(FACT_KEY):
        return False
    for row in recommendations:
        if not isinstance(row, dict) or row.get("recommended_action") != REQUEST_HUMAN_FACT_VERIFICATION:
            continue
        index = row.get("claim_index")
        if type(index) is not int or index < 0 or index >= len(claims):
            continue
        claim = claims[index]
        if not isinstance(claim, dict) or claim.get("requires_case_fact") is not True:
            continue
        if not any(isinstance(item, dict) and item.get("claim_index") == index and item.get("case_fact_status") == "unresolved" for item in coverage):
            continue
        request = {
            "request_id": str(uuid4()),
            "claim_index": index,
            "claim": claim["claim"],
            "missing_fact": "该企业个案事实尚无可信的逐 Claim 核实结果",
            "question": f"请确认以下陈述所依据的企业调查事实；若目前无法确认，请选择 FACT_UNAVAILABLE：{claim['claim']}",
            "status": "pending",
        }
        state.metadata[FACT_KEY] = {
            "request": request,
            "draft": draft,
            "draft_hash": sha256(draft.encode("utf-8")).hexdigest(),
            "remaining_plan": deepcopy(remaining_plan),
            "response": None,
            "phase": PHASE_PENDING,
            "observation": {"case_fact_status": "unresolved", "human_verification_attempted": False},
            "revision_attempted": False,
            "decision_attempted": False,
        }
        state.metadata["human_wait_type"] = FACT_INPUT
        state.set_status(WAITING_HUMAN)
        _trace(state, 0, "REQUEST_HUMAN_FACT_VERIFICATION", request["request_id"], index,
               {"case_fact_status": "unresolved"}, "case_fact_requires_human_input",
               evidence_gap="CASE_FACT_UNRESOLVED")
        return True
    return False


def record_response(state, response: dict) -> dict:
    fact = state.metadata.get(FACT_KEY)
    if (state.status != WAITING_HUMAN or state.metadata.get("human_wait_type") != FACT_INPUT
            or not isinstance(fact, dict)):
        raise ValueError("Session is not waiting for a human fact response.")
    request = fact.get("request") or {}
    if request.get("status") != "pending" or fact.get("response") is not None:
        raise ValueError("Human fact request was already answered.")
    if not isinstance(response, dict) or response.get("request_id") != request.get("request_id"):
        raise ValueError("Human fact request_id is invalid or expired.")
    response_type = response.get("response_type")
    if not isinstance(response_type, str) or response_type not in {"FACT_PROVIDED", "FACT_UNAVAILABLE"}:
        raise ValueError("response_type must be FACT_PROVIDED or FACT_UNAVAILABLE.")
    text = response.get("fact_text", "")
    if not isinstance(text, str) or (response_type == "FACT_PROVIDED" and not text.strip()):
        raise ValueError("FACT_PROVIDED requires non-empty fact_text.")
    draft = str((state.get_result("writer") or {}).get("statement", ""))
    index = request.get("claim_index")
    claims = (state.metadata.get("legal_claim_extraction") or {}).get("legal_claims", [])
    if (draft != fact.get("draft") or sha256(draft.encode("utf-8")).hexdigest() != fact.get("draft_hash")
            or type(index) is not int or index < 0 or index >= len(claims)
            or not isinstance(claims[index], dict) or claims[index].get("claim") != request.get("claim")):
        raise ValueError("Human fact request no longer matches the frozen draft and claim.")
    request["status"] = "answered"
    fact["response"] = {"request_id": request["request_id"], "response_type": response_type,
                        "fact_text": text.strip() if response_type == "FACT_PROVIDED" else ""}
    observation = {"case_fact_status": "unresolved", "human_verification_attempted": True}
    if response_type == "FACT_UNAVAILABLE":
        observation["fact_currently_unavailable"] = True
    else:
        observation.update({"source": "human_provided", "verification_status": "human_asserted"})
    fact["observation"] = observation
    fact["phase"] = PHASE_RESPONSE_RECORDED
    _trace(state, 1, "HUMAN_FACT_RESPONSE", request["request_id"], index,
           {key: value for key, value in observation.items()}, response_type)
    state.set_status(RUNNING)
    return deepcopy(fact["response"])


def revision_is_safe(original_claim: str, revised_draft: str) -> bool:
    """Allow continuation only when the revised statement clearly remains uncertain."""
    if not revised_draft.strip() or not original_claim.strip():
        return False
    # Any detected definitive factual wording keeps this revision in human review,
    # even if another sentence also contains an uncertainty disclaimer.
    if _DEFINITE.search(revised_draft):
        return False
    extraction = extract_claims(revised_draft, "mock")
    if extraction["claim_extraction_status"] != "ok":
        return False
    revised = extraction["legal_claims"]
    coverage = build_claim_coverage(revised, {"legal_claim_relations": [], "relation_status": "skipped"})
    for item, row in zip(revised, coverage["claim_coverage"]):
        if row["case_fact_status"] == "unresolved" and _DEFINITE.search(item["claim"]):
            return False
    target_terms = {
        original_claim[index:index + 2]
        for index in range(len(original_claim) - 1)
        if original_claim[index:index + 2] not in _NON_TOPIC_BIGRAMS
    }
    for sentence in re.split(r"[。！？!?；;\n]+", revised_draft):
        if _DEFINITE.search(sentence) and any(term in sentence for term in target_terms):
            return False
    return bool(_SAFE_UNCERTAINTY.search(revised_draft))


def _trace(state, round_index: int, action: str, request_id: str, claim_index: int,
           observation: dict, reason: str, **extra) -> None:
    state.add_trace({"agent": "human_fact", "status": "success", "round": round_index,
                     "action": action, "request_id": request_id, "claim_index": claim_index,
                     "observation": deepcopy(observation), "reason": reason, **extra})


def record_action(state, round_index: int, action: str, reason: str, observation: dict) -> None:
    request = state.metadata[FACT_KEY]["request"]
    _trace(state, round_index, action, request["request_id"], request["claim_index"], observation, reason)
