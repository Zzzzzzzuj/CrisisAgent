from __future__ import annotations

# Compatibility adapters deliberately reuse the established JSON stores.
from backend.api.audit_store import JsonAuditStore as JsonAuditLogRepository
from backend.api.eval_store import JsonEvalRunStore as JsonEvalRunRepository
from backend.api.event_store import JsonCrisisEventStore as JsonCrisisEventRepository
from backend.api.ingestion_run_store import JsonIngestionRunStore as JsonIngestionRunRepository
from backend.api.event_run_store import JsonEventAgentRunStore as JsonEventAgentRunRepository
