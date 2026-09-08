from __future__ import annotations

from backend.product_storage.config import ProductStorageConfigurationError, get_product_database_url


class PostgresRepositoryUnavailable:
    """Explicit first-phase boundary: schema exists, runtime repository is not enabled yet."""

    def __init__(self, resource: str):
        self.resource = resource

    def _raise(self):
        get_product_database_url()
        raise ProductStorageConfigurationError(
            f"PostgreSQL {self.resource} repository is not enabled in phase 1; apply docs/sql/product_storage_schema.sql and implement the database adapter first."
        )

    def __getattr__(self, _name):
        return self._raise
