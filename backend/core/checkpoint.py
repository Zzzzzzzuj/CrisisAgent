import json
from pathlib import Path

from backend.core.state import AgentState


CHECKPOINT_PATH = Path(__file__).resolve().parent / "data" / "checkpoints.json"


def save_checkpoint(state: AgentState, checkpoint_path: str | Path = CHECKPOINT_PATH) -> dict:
    data = _read_checkpoint_data(checkpoint_path)
    state_data = state.to_dict()
    data[state.session_id] = state_data
    _write_checkpoint_data(checkpoint_path, data)
    return state_data


def load_checkpoint(session_id: str, checkpoint_path: str | Path = CHECKPOINT_PATH) -> AgentState | None:
    data = _read_checkpoint_data(checkpoint_path)
    state_data = data.get(session_id)
    if state_data is None:
        return None
    return AgentState.from_dict(state_data)


def list_checkpoints(checkpoint_path: str | Path = CHECKPOINT_PATH) -> list[dict]:
    data = _read_checkpoint_data(checkpoint_path)
    return [
        {
            "session_id": state_data.get("session_id", session_id),
            "plan_id": state_data.get("plan_id", ""),
            "event": state_data.get("event", ""),
            "status": state_data.get("status", ""),
            "created_time": _extract_created_time(state_data),
        }
        for session_id, state_data in sorted(data.items())
    ]


def delete_checkpoint(session_id: str, checkpoint_path: str | Path = CHECKPOINT_PATH) -> bool:
    data = _read_checkpoint_data(checkpoint_path)
    if session_id not in data:
        return False
    del data[session_id]
    _write_checkpoint_data(checkpoint_path, data)
    return True


def _read_checkpoint_data(checkpoint_path: str | Path) -> dict:
    path = Path(checkpoint_path)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    return data if isinstance(data, dict) else {}


def _write_checkpoint_data(checkpoint_path: str | Path, data: dict) -> None:
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_created_time(state_data: dict) -> str:
    trace = state_data.get("trace", [])
    if not isinstance(trace, list):
        return ""
    for item in trace:
        if isinstance(item, dict) and item.get("start_time"):
            return str(item["start_time"])
    return ""
