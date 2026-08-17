from pathlib import Path

from backend.core.state import AgentState
from backend.db.repositories import (
    CheckpointRepository,
    JSONCheckpointRepository,
    SQLAlchemyCheckpointRepository,
)
from backend.db.session import is_database_checkpoint_enabled


CHECKPOINT_PATH = Path(__file__).resolve().parent / "data" / "checkpoints.json"


def save_checkpoint(state: AgentState, checkpoint_path: str | Path | None = None) -> dict:
    return _get_repository(checkpoint_path).save_checkpoint(state)


def load_checkpoint(session_id: str, checkpoint_path: str | Path | None = None) -> AgentState | None:
    return _get_repository(checkpoint_path).load_checkpoint(session_id)


def list_checkpoints(checkpoint_path: str | Path | None = None) -> list[dict]:
    return _get_repository(checkpoint_path).list_checkpoints()


def delete_checkpoint(session_id: str, checkpoint_path: str | Path | None = None) -> bool:
    return _get_repository(checkpoint_path).delete_checkpoint(session_id)


def list_audit_logs(
    session_id: str | None = None,
    checkpoint_path: str | Path | None = None,
) -> list[dict]:
    return _get_repository(checkpoint_path).list_audit_logs(session_id)


def _get_repository(checkpoint_path: str | Path | None = None) -> CheckpointRepository:
    if checkpoint_path is not None:
        return JSONCheckpointRepository(checkpoint_path)
    if is_database_checkpoint_enabled():
        return SQLAlchemyCheckpointRepository()
    return JSONCheckpointRepository(CHECKPOINT_PATH)

