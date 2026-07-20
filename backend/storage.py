_SESSION_STORE: dict[str, dict] = {}


def save_session(session_id: str, data: dict) -> None:
    _SESSION_STORE[session_id] = data


def get_session(session_id: str) -> dict | None:
    return _SESSION_STORE.get(session_id)


def list_sessions() -> list[dict]:
    sessions = []
    for session_id, data in _SESSION_STORE.items():
        final_statement = data.get("final_statement", "")
        sessions.append(
            {
                "session_id": session_id,
                "final_statement_preview": final_statement[:50],
                "scores": data.get("scores", {}),
            }
        )
    return sessions
