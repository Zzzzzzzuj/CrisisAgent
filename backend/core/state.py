from copy import deepcopy


INIT = "INIT"
RUNNING = "RUNNING"
WAITING_HUMAN = "WAITING_HUMAN"
COMPLETED = "COMPLETED"
FAILED = "FAILED"


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
        self.status = INIT
        self.approval = {
            "required": False,
            "decision": None,
            "reviewer": "",
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

    def to_dict(self) -> dict:
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
        state.status = data.get("status", INIT)
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
