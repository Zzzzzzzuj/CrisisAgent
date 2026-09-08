from __future__ import annotations

from backend.product_storage.config import get_product_storage_backend
from backend.product_storage.json_repositories import JsonAuditLogRepository, JsonCrisisEventRepository, JsonEvalRunRepository
from backend.product_storage.postgres_repositories import PostgresRepositoryUnavailable


def get_audit_log_repository():
    return JsonAuditLogRepository() if get_product_storage_backend() == "json" else PostgresRepositoryUnavailable("audit log")


def get_eval_run_repository():
    return JsonEvalRunRepository() if get_product_storage_backend() == "json" else PostgresRepositoryUnavailable("eval run")


def get_crisis_event_repository():
    return JsonCrisisEventRepository() if get_product_storage_backend() == "json" else PostgresRepositoryUnavailable("crisis event")
