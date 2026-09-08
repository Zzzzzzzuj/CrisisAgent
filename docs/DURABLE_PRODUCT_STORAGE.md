# Durable Product Storage

P13 introduces a repository boundary for product-workbench objects. `PRODUCT_STORAGE=json` remains the default and reuses the existing readable runtime JSON files and test path environment variables. `PRODUCT_STORAGE=postgres` is an explicit first-phase placeholder: it validates `PRODUCT_DATABASE_URL` only when a repository is used, then reports that the database adapter is not yet enabled.

The planned PostgreSQL tables are documented in [product_storage_schema.sql](sql/product_storage_schema.sql). The schema preserves resource identifiers, owner/audit fields, status, JSONB payloads and timestamps for sources, ingestion runs, events, Agent runs, Eval runs and audit logs.

Export existing local stores without a database connection:

```powershell
python scripts/export_product_storage.py --output data/product_storage_export.json
```

Ordinary pytest stays JSON-only and does not start PostgreSQL. This is a durable-data foundation, not a completed PostgreSQL migration: the next phase must implement SQL repositories, migrations, connection health checks and integration smoke tests.

## Interview

> I kept JSON storage as the deterministic demo backend, but introduced repositories so product APIs no longer have to be coupled to file storage forever. P13 provides a PostgreSQL schema contract and explicit configuration failure behavior without making local tests depend on a database. That lets us export existing JSON data and later replace adapters incrementally instead of rewriting the product workflow.
