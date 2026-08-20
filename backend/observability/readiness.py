import os

from sqlalchemy import text

from backend.auth import is_auth_enabled
from backend.core import checkpoint
from backend.core.runtime_tasks import (
    check_rq_backend,
    get_runtime_mode,
    get_task_queue_backend,
    is_worker_initialized,
)
from backend.db.session import get_database_url, get_engine, is_database_checkpoint_enabled


def check_readiness() -> dict:
    checks = {
        "checkpoint_backend": _check_checkpoint_backend(),
        "database": _check_database(),
        "async_worker": _check_async_worker(),
        "required_env": _check_required_env(),
        "auth": _check_auth(),
    }
    ready = all(item["ok"] for item in checks.values())
    return {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "checks": checks,
    }


def _check_checkpoint_backend() -> dict:
    try:
        checkpoint.list_checkpoints()
        return {
            "ok": True,
            "backend": "postgres" if is_database_checkpoint_enabled() else "json",
        }
    except Exception as exc:
        return {
            "ok": False,
            "backend": "postgres" if is_database_checkpoint_enabled() else "json",
            "error": exc.__class__.__name__,
        }


def _check_database() -> dict:
    if not is_database_checkpoint_enabled():
        return {"ok": True, "enabled": False, "backend": "json"}

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return {
            "ok": False,
            "enabled": True,
            "error": "DATABASE_URL is required when CHECKPOINT_STORAGE=postgres.",
        }

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "ok": True,
            "enabled": True,
            "database_url_configured": bool(get_database_url()),
        }
    except Exception as exc:
        return {
            "ok": False,
            "enabled": True,
            "error": exc.__class__.__name__,
        }


def _check_async_worker() -> dict:
    mode = get_runtime_mode()
    queue_backend = get_task_queue_backend()
    if mode == "async" and queue_backend == "rq":
        rq_status = check_rq_backend()
        return {
            "ok": rq_status.get("ok") is True,
            "runtime_mode": mode,
            "task_queue_backend": queue_backend,
            "worker_initialized": rq_status.get("ok") is True,
            **rq_status,
        }
    return {
        "ok": True,
        "runtime_mode": mode,
        "task_queue_backend": queue_backend,
        "worker_initialized": is_worker_initialized(),
    }


def _check_required_env() -> dict:
    return {
        "ok": True,
        "checkpoint_storage": os.getenv("CHECKPOINT_STORAGE", "json"),
        "runtime_mode": get_runtime_mode(),
        "task_queue_backend": get_task_queue_backend(),
        "auth_enabled": is_auth_enabled(),
    }


def _check_auth() -> dict:
    if not is_auth_enabled():
        return {"ok": True, "enabled": False}
    if not os.getenv("SECRET_KEY", "").strip():
        return {
            "ok": False,
            "enabled": True,
            "error": "SECRET_KEY is required when AUTH_ENABLED=true.",
        }
    return {"ok": True, "enabled": True}
