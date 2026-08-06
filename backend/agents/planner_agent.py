from uuid import uuid4


AVAILABLE_AGENTS = {"sentiment", "writer", "redteam", "legal", "writer_v2", "decision"}
EXECUTION_ORDER = ("sentiment", "writer", "redteam", "legal", "writer_v2", "decision")
NEGATIVE_PUBLIC_OPINION_TERMS = (
    "爆",
    "质疑",
    "投诉",
    "网友",
    "传播",
    "舆情",
    "抵制",
    "泄露",
    "监管",
)
LEGAL_TRIGGER_TERMS = (
    "食品",
    "过期",
    "原料",
    "生产",
    "数据",
    "隐私",
    "泄露",
    "用户信息",
    "违法",
    "监管",
    "赔偿",
    "责任",
    "合规",
)
LEGAL_CATEGORIES = {"food_safety", "data_privacy", "legal_risk"}


def run(payload: dict) -> dict:
    event = str(payload.get("event", ""))
    category = str(payload.get("category", ""))
    risk_level = str(payload.get("risk_level", "")).lower()

    planned_agents: dict[str, dict] = {}

    if _needs_sentiment(event, risk_level):
        _add_plan_item(
            planned_agents,
            agent="sentiment",
            reason="事件存在负面舆情或较高传播风险，需要先判断公众情绪与风险等级。",
            confidence=0.9 if risk_level in {"high", "critical"} else 0.8,
        )

    if _needs_legal(event, category):
        _add_plan_item(
            planned_agents,
            agent="legal",
            reason="事件涉及食品安全、数据隐私或法律责任表达，需要进行合规审查。",
            confidence=0.9 if category in LEGAL_CATEGORIES else 0.8,
        )

    _add_plan_item(
        planned_agents,
        agent="writer",
        reason="所有危机事件都需要生成对外回应文案。",
        confidence=1.0,
    )
    _add_plan_item(
        planned_agents,
        agent="redteam",
        reason="Run adversarial review before compliance and revision.",
        confidence=0.9,
    )
    _add_plan_item(
        planned_agents,
        agent="writer_v2",
        reason="Revise the first draft after redteam and legal review.",
        confidence=1.0,
    )
    _add_plan_item(
        planned_agents,
        agent="decision",
        reason="所有危机事件都需要最终决策和评分。",
        confidence=1.0,
    )

    return {
        "plan_id": str(uuid4()),
        "plan": [
            planned_agents[agent]
            for agent in EXECUTION_ORDER
            if agent in planned_agents and agent in AVAILABLE_AGENTS
        ],
    }


def _needs_sentiment(event: str, risk_level: str) -> bool:
    if risk_level in {"medium", "high", "critical"}:
        return True
    return any(term in event for term in NEGATIVE_PUBLIC_OPINION_TERMS)


def _needs_legal(event: str, category: str) -> bool:
    if category in LEGAL_CATEGORIES:
        return True
    return any(term in event for term in LEGAL_TRIGGER_TERMS)


def _add_plan_item(
    planned_agents: dict[str, dict],
    agent: str,
    reason: str,
    confidence: float,
) -> None:
    if agent not in AVAILABLE_AGENTS or agent in planned_agents:
        return

    planned_agents[agent] = {
        "agent": agent,
        "reason": reason,
        "confidence": round(float(confidence), 2),
    }
