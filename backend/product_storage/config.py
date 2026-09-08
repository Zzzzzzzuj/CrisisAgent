from __future__ import annotations

import os


class ProductStorageConfigurationError(RuntimeError):
    pass


def get_product_storage_backend() -> str:
    value = os.getenv("PRODUCT_STORAGE", "json").strip().lower() or "json"
    if value not in {"json", "postgres"}:
        raise ProductStorageConfigurationError("PRODUCT_STORAGE must be 'json' or 'postgres'.")
    return value


def get_product_database_url() -> str:
    value = os.getenv("PRODUCT_DATABASE_URL", "").strip()
    if not value:
        raise ProductStorageConfigurationError("PRODUCT_DATABASE_URL is required when PRODUCT_STORAGE=postgres.")
    return value
