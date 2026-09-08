-- P13 product-workbench storage foundation. Apply manually in a PostgreSQL database.
CREATE TABLE IF NOT EXISTS product_sources (resource_id TEXT PRIMARY KEY, owner_id TEXT, created_by TEXT, updated_by TEXT, status TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS product_ingestion_runs (resource_id TEXT PRIMARY KEY, owner_id TEXT, created_by TEXT, status TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS product_crisis_events (resource_id TEXT PRIMARY KEY, owner_id TEXT, created_by TEXT, updated_by TEXT, status TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS product_event_agent_runs (resource_id TEXT PRIMARY KEY, owner_id TEXT, created_by TEXT, status TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS product_eval_runs (resource_id TEXT PRIMARY KEY, created_by TEXT, status TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS product_audit_logs (resource_id TEXT PRIMARY KEY, actor_id TEXT, actor_role TEXT, status TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
