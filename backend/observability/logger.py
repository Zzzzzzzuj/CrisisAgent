import json
import logging
from datetime import datetime, timezone
from typing import Any


LOG_FIELDS = (
    "timestamp",
    "level",
    "session_id",
    "agent_name",
    "event",
    "status",
    "latency_ms",
    "error_type",
    "fallback_used",
    "guardrail_triggered",
    "reviewer",
)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "session_id": getattr(record, "session_id", ""),
            "agent_name": getattr(record, "agent_name", ""),
            "event": getattr(record, "event", record.getMessage()),
            "status": getattr(record, "status", ""),
            "latency_ms": getattr(record, "latency_ms", None),
            "error_type": getattr(record, "error_type", ""),
            "fallback_used": bool(getattr(record, "fallback_used", False)),
            "guardrail_triggered": bool(getattr(record, "guardrail_triggered", False)),
            "reviewer": getattr(record, "reviewer", ""),
        }
        return json.dumps(_sanitize_payload(payload), ensure_ascii=False)


def get_structured_logger(name: str = "crisisagent") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_runtime_event(
    *,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
    session_id: str = "",
    agent_name: str = "",
    event: str = "",
    status: str = "",
    latency_ms: int | None = None,
    error_type: str = "",
    fallback_used: bool = False,
    guardrail_triggered: bool = False,
    reviewer: str = "",
) -> None:
    target_logger = logger or get_structured_logger()
    target_logger.log(
        level,
        _safe_text(event),
        extra={
            "session_id": _safe_text(session_id, 128),
            "agent_name": _safe_text(agent_name, 128),
            "event": _safe_text(event),
            "status": _safe_text(status, 64),
            "latency_ms": latency_ms,
            "error_type": _safe_text(error_type, 128),
            "fallback_used": fallback_used,
            "guardrail_triggered": guardrail_triggered,
            "reviewer": _safe_text(reviewer, 128),
        },
    )


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in payload.items()}


def _safe_text(value: Any, limit: int = 240) -> str:
    text = str(value or "")
    for marker in ("sk-", "Bearer ", "Authorization"):
        if marker in text:
            text = text.replace(marker, "[redacted]")
    text = " ".join(text.split())
    return text[:limit]
