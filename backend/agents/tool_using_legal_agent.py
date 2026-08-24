from __future__ import annotations

from typing import Any

from backend.core.reasoning_mode import build_controlled_tool_plan
from backend.core.tool_policy import evaluate_tool_call_policy, validate_tool_plan_safety
from backend.skills.builtins import create_default_registry
from backend.skills.function_calling_adapter import FunctionCallingAdapter
from backend.skills.registry import SkillRegistry


AGENT_NAME = "tool_using_legal"


def run(payload: dict, registry: SkillRegistry | None = None) -> dict:
    registry = registry or create_default_registry()
    adapter = FunctionCallingAdapter(registry)
    available_skills = [
        skill["name"]
        for skill in registry.list_skills()
        if skill.get("enabled", True)
    ]
    event = str(payload.get("event", ""))
    sentiment_result = payload.get("sentiment_result") or payload.get("sentiment_analysis") or {}
    redteam_result = payload.get("redteam_result") or payload.get("redteam_review") or {}
    plan = payload.get("tool_plan") or build_controlled_tool_plan(
        event=event,
        sentiment_result=sentiment_result,
        redteam_result=redteam_result,
        available_skills=available_skills,
        user_requested_strict_review=bool(payload.get("user_requested_strict_review", False)),
    )

    plan_policy = validate_tool_plan_safety(plan)
    tool_call_trace = []
    observations = []
    if not plan_policy["allow"]:
        return _build_review(
            event=event,
            plan=plan,
            observations=observations,
            tool_call_trace=[
                {
                    "name": "tool_plan",
                    "success": False,
                    "policy": plan_policy,
                    "error": plan_policy["reason"],
                }
            ],
            human_review_required=True,
        )

    for tool_name in plan.get("required_tools", []):
        arguments = _tool_arguments(tool_name, event, payload, plan)
        policy = evaluate_tool_call_policy(tool_name, arguments, plan)
        if not policy["allow"]:
            trace = {
                "name": tool_name,
                "arguments": arguments,
                "success": False,
                "policy": policy,
                "error": policy["reason"],
            }
            tool_call_trace.append(trace)
            break
        try:
            adapter.validate_input(tool_name, arguments)
        except Exception as exc:
            tool_call_trace.append(
                {
                    "name": tool_name,
                    "arguments": arguments,
                    "success": False,
                    "policy": policy,
                    "error": f"schema_validation_failed:{exc}",
                }
            )
            break

        result = adapter.execute_tool_call(tool_name, arguments, call_id=f"{AGENT_NAME}:{len(tool_call_trace) + 1}")
        result["policy"] = policy
        tool_call_trace.append(result)
        observations.append(
            {
                "tool": tool_name,
                "success": result["success"],
                "output": result["output"],
                "error": result["error"],
            }
        )
        if not result["success"]:
            break

    return _build_review(
        event=event,
        plan=plan,
        observations=observations,
        tool_call_trace=tool_call_trace,
        human_review_required=bool(plan.get("human_review_required")),
    )


def _tool_arguments(tool_name: str, event: str, payload: dict, plan: dict) -> dict[str, Any]:
    if tool_name == "legal_rag_search":
        return {"query": event, "top_k": 3}
    if tool_name == "guardrail_check":
        return {
            "event": event,
            "statement": str(payload.get("draft") or payload.get("statement") or ""),
        }
    if tool_name == "knowledge_document_search":
        return {
            "source_category": _source_category_from_event(event, plan),
            "published_only": True,
        }
    return {}


def _build_review(
    *,
    event: str,
    plan: dict,
    observations: list[dict],
    tool_call_trace: list[dict],
    human_review_required: bool,
) -> dict:
    rag_observation = _find_observation(observations, "legal_rag_search")
    guardrail_observation = _find_observation(observations, "guardrail_check")
    knowledge_observation = _find_observation(observations, "knowledge_document_search")
    rag_sources = (rag_observation.get("output") or {}).get("sources", []) if rag_observation else []
    guardrail_hit = bool((guardrail_observation.get("output") or {}).get("hit")) if guardrail_observation else False
    failed_tool = next((trace for trace in tool_call_trace if not trace.get("success")), None)

    legal_risks = []
    if plan.get("risk_level") == "high":
        legal_risks.append("高风险事件需要基于证据审慎回应，避免提前定责或绝对承诺。")
    if guardrail_hit:
        legal_risks.append("Guardrail 命中，需人工复核输入或输出中的高风险表达。")
    if failed_tool:
        legal_risks.append(f"工具调用未完成：{failed_tool.get('error')}")
    if not legal_risks:
        legal_risks.append("当前未发现必须升级的法律风险，但仍建议保留审慎表达。")

    safe_points = [
        "说明已启动事实核查。",
        "避免在核查完成前作绝对事实或法律结论。",
    ]
    if rag_sources:
        safe_points.append(f"参考 RAG evidence 来源：{_source_names(rag_sources)}。")
    if knowledge_observation and (knowledge_observation.get("output") or {}).get("count", 0) > 0:
        safe_points.append("可结合已发布知识文档中的治理要求组织回应。")

    revision_advice = [
        "声明中保留条件式表达，例如“如核查发现问题，将依法依规处理”。",
        "对公众关切给出核查、沟通和后续更新安排。",
    ]
    if plan.get("skipped_tools"):
        revision_advice.append(f"跳过工具原因：{plan['skipped_tools']}")

    return {
        "agent": AGENT_NAME,
        "event": event,
        "tool_plan": plan,
        "tool_observations": observations,
        "legal_risks": legal_risks,
        "safe_points": safe_points,
        "revision_advice": revision_advice,
        "human_review_required": bool(human_review_required or guardrail_hit or failed_tool),
        "tool_call_trace": tool_call_trace,
        "_metadata": {
            "tool_using_agent": {
                "plan": plan,
                "tool_call_trace": tool_call_trace,
                "observation_count": len(observations),
            }
        },
    }


def _find_observation(observations: list[dict], tool_name: str) -> dict:
    return next((item for item in observations if item.get("tool") == tool_name), {})


def _source_names(sources: list) -> str:
    names = []
    for source in sources:
        if isinstance(source, dict):
            name = source.get("source") or source.get("source_name")
        else:
            name = str(source)
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def _source_category_from_event(event: str, plan: dict) -> str:
    if "食品" in event or "过期" in event:
        return "food_safety"
    if "数据" in event or "隐私" in event or "泄露" in event:
        return "data_privacy"
    return str(plan.get("risk_level") or "general")
