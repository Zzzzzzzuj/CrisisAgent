from copy import deepcopy


INIT = "INIT"
CREATED = "CREATED"
QUEUED = "QUEUED"
RUNNING = "RUNNING"
WAITING_HUMAN = "WAITING_HUMAN"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
REJECTED = "REJECTED"

VALID_STATE_STATUSES = {
    INIT,
    CREATED,
    QUEUED,
    RUNNING,
    WAITING_HUMAN,
    COMPLETED,
    FAILED,
    REJECTED,
}

ALLOWED_STATE_TRANSITIONS = {
    INIT: {CREATED, QUEUED, RUNNING, WAITING_HUMAN, COMPLETED, FAILED, REJECTED},
    CREATED: {QUEUED, RUNNING, WAITING_HUMAN, COMPLETED, FAILED, REJECTED},
    QUEUED: {RUNNING, WAITING_HUMAN, COMPLETED, FAILED, REJECTED},
    RUNNING: {WAITING_HUMAN, COMPLETED, FAILED, REJECTED},
    WAITING_HUMAN: {QUEUED, RUNNING, FAILED, REJECTED},
    COMPLETED: set(),
    FAILED: set(),
    REJECTED: set(),
}


def validate_state_status(status: str) -> str:
    if status not in VALID_STATE_STATUSES:
        raise ValueError(f"Unsupported AgentState status: {status}")
    return status


def validate_state_transition(current_status: str, next_status: str) -> str:
    validate_state_status(current_status)
    validate_state_status(next_status)
    if current_status == next_status:
        return next_status
    allowed_targets = ALLOWED_STATE_TRANSITIONS[current_status]
    if next_status not in allowed_targets:
        raise ValueError(
            f"Invalid AgentState transition: {current_status} -> {next_status}"
        )
    return next_status


class AgentState:
    def __init__(
        self,
        session_id: str,
        plan_id: str,
        event: str,
        results: dict | None = None,
        trace: list | None = None,
        metadata: dict | None = None,
    ):
        self.session_id = session_id
        self.plan_id = plan_id
        self.event = event
        self.results = results or {}
        self.trace = trace or []
        self.metadata = metadata or {}
        self.failed_agents = []
        self.current_agent = None
        self.status = CREATED
        self.approval = {
            "required": False,
            "decision": None,
            "reviewer": "",
            "reviewer_id": None,
            "reviewer_username": "",
            "reviewer_role": "",
            "comment": "",
            "reason": "",
            "timestamp": None,
        }

    def set_result(self, agent: str, result: dict) -> None:
        self.results[agent] = deepcopy(result)

    def get_result(self, agent: str):
        result = self.results.get(agent)
        return deepcopy(result)

    def get_all_results(self) -> dict:
        return deepcopy(self.results)

    def to_context(self) -> dict:
        return {
            "session_id": self.session_id,
            "plan_id": self.plan_id,
            "event": self.event,
            "results": self.get_all_results(),
            "metadata": deepcopy(self.metadata),
            "current_agent": self.current_agent,
            "failed_agents": deepcopy(self.failed_agents),
            "status": self.status,
            "approval": deepcopy(self.approval),
        }

    def set_status(self, status: str) -> None:
        self.status = validate_state_transition(self.status, status)

    def to_dict(self) -> dict:
        validate_state_status(self.status)
        return {
            "session_id": self.session_id,
            "plan_id": self.plan_id,
            "event": self.event,
            "status": self.status,
            "results": self.get_all_results(),
            "trace": deepcopy(self.trace),
            "metadata": deepcopy(self.metadata),
            "approval": deepcopy(self.approval),
            "failed_agents": deepcopy(self.failed_agents),
            "current_agent": self.current_agent,
        }

    @classmethod
    def from_dict(cls, data: dict):
        state = cls(
            session_id=str(data.get("session_id", "")),
            plan_id=str(data.get("plan_id", "")),
            event=str(data.get("event", "")),
            results=deepcopy(data.get("results", {})),
            trace=deepcopy(data.get("trace", [])),
            metadata=deepcopy(data.get("metadata", {})),
        )
        state.status = validate_state_status(data.get("status", CREATED))
        state.approval.update(deepcopy(data.get("approval", {})))
        state.failed_agents = deepcopy(data.get("failed_agents", []))
        state.current_agent = data.get("current_agent")
        return state

    def add_trace(self, item: dict) -> None:
        self.trace.append(deepcopy(item))

    def mark_failed(self, agent: str | None, reason: str) -> None:
        self.failed_agents.append(
            {
                "agent": agent,
                "reason": reason,
            }
        )
