AGENT_DEPENDENCIES = {
    "sentiment": [],
    "writer": ["sentiment"],
    "redteam": ["writer"],
    "legal": ["writer", "redteam"],
    "writer_v2": ["writer", "redteam", "legal"],
    "decision": ["writer_v2"],
}
AGENT_ORDER = ("sentiment", "writer", "redteam", "legal", "writer_v2", "decision")


def validate_plan(plan: dict) -> dict:
    requested_items = plan.get("plan", [])
    requested_agents = [_validate_agent_item(item) for item in requested_items]

    required_agents = set(requested_agents)
    for agent in list(requested_agents):
        _add_dependencies(agent, required_agents)

    return {
        **plan,
        "plan": [
            _build_plan_item(agent, requested_items)
            for agent in AGENT_ORDER
            if agent in required_agents
        ],
    }


def _validate_agent_item(item: dict) -> str:
    agent = item.get("agent")
    if agent not in AGENT_DEPENDENCIES:
        raise ValueError(f"Unsupported agent in plan: {agent}")
    return agent


def _add_dependencies(agent: str, required_agents: set[str]) -> None:
    for dependency in AGENT_DEPENDENCIES[agent]:
        if dependency not in required_agents:
            required_agents.add(dependency)
            _add_dependencies(dependency, required_agents)


def _build_plan_item(agent: str, requested_items: list[dict]) -> dict:
    for item in requested_items:
        if item.get("agent") == agent:
            return dict(item)

    return {
        "agent": agent,
        "reason": f"Automatically added dependency for dynamic execution: {agent}.",
        "confidence": 1.0,
    }
