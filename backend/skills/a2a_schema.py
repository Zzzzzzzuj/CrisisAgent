from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AgentMessage:
    from_agent: str
    to_agent: str
    task_type: str
    payload: dict[str, Any]
    trace_id: str
    session_id: str
    requires_ack: bool = False
    message_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task_type": self.task_type,
            "payload": self.payload,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "requires_ack": self.requires_ack,
            "created_at": self.created_at,
        }


def explain_a2a_vs_mcp() -> dict[str, str]:
    return {
        "mcp": "Agent-to-tool/resource protocol: an agent calls external tools or reads resources.",
        "a2a": "Agent-to-agent protocol: agents exchange tasks, context and acknowledgements.",
        "crisisagent_mapping": "CrisisAgent uses shared AgentState today; AgentMessage documents how planner/executor/agents could exchange explicit A2A messages later.",
    }
