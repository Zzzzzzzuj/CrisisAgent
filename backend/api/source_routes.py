from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import os

from fastapi import APIRouter, HTTPException, status

from backend.api.source_schemas import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
    SourceTestResponse,
    SourceUpdateRequest,
)
from backend.ingestion.source_registry import SourceDefinition, SourceRegistry


router = APIRouter(prefix="/api/sources", tags=["sources"])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_PATH = PROJECT_ROOT / "data" / "source_registry.runtime.json"


class JsonSourceRegistryStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("SOURCE_REGISTRY_RUNTIME_PATH", DEFAULT_RUNTIME_PATH))

    def list_sources(self) -> list[dict[str, Any]]:
        return [asdict(source) for source in self._load()]

    def create(self, payload: SourceCreateRequest) -> dict[str, Any]:
        sources = self._load()
        if any(source.source_id == payload.source_id for source in sources):
            raise ValueError("source_id already exists")
        source = _source_from_create(payload)
        _validate_source(source)
        sources.append(source)
        self._save(sources)
        return asdict(source)

    def update(self, source_id: str, payload: SourceUpdateRequest) -> dict[str, Any]:
        sources = self._load()
        for index, current in enumerate(sources):
            if current.source_id != source_id:
                continue
            values = asdict(current)
            values.update({key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None})
            updated = SourceDefinition(**values)
            _validate_source(updated)
            sources[index] = updated
            self._save(sources)
            return asdict(updated)
        raise KeyError(source_id)

    def get(self, source_id: str) -> SourceDefinition:
        for source in self._load():
            if source.source_id == source_id:
                return source
        raise KeyError(source_id)

    def _load(self) -> list[SourceDefinition]:
        if not self.path.exists():
            return []
        import json

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
            raise ValueError("Runtime source registry must contain a sources array.")
        sources = []
        for raw in payload["sources"]:
            source = SourceDefinition(
                source_id=str(raw.get("source_id", "")).strip(),
                source_name=str(raw.get("source_name", "")).strip(),
                source_type=str(raw.get("source_type", "")).strip(),
                url=str(raw.get("url", "")).strip(),
                enabled=raw.get("enabled", False) is True,
                company_keywords=tuple(str(value).strip() for value in raw.get("company_keywords", []) or []),
                risk_keywords=tuple(str(value).strip() for value in raw.get("risk_keywords", []) or []),
                respect_robots=raw.get("respect_robots", True) is not False,
                rate_limit_seconds=float(raw.get("rate_limit_seconds", 3)),
                timeout_seconds=float(raw.get("timeout_seconds", 10)),
                max_items=int(raw.get("max_items", 5)),
            )
            _validate_source(source)
            if any(item.source_id == source.source_id for item in sources):
                raise ValueError(f"Duplicate source_id: {source.source_id}")
            sources.append(source)
        return sources

    def _save(self, sources: list[SourceDefinition]) -> None:
        import json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sources": [asdict(source) for source in sources]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_source_store() -> JsonSourceRegistryStore:
    return JsonSourceRegistryStore()


def _source_from_create(payload: SourceCreateRequest) -> SourceDefinition:
    values = payload.model_dump()
    values["company_keywords"] = tuple(values["company_keywords"])
    values["risk_keywords"] = tuple(values["risk_keywords"])
    return SourceDefinition(**values)


def _validate_source(source: SourceDefinition) -> None:
    SourceRegistry._validate(source)
    if not source.company_keywords and not source.risk_keywords:
        raise ValueError("at least one company_keywords or risk_keywords entry is required")


def _response(source: dict[str, Any]) -> SourceResponse:
    return SourceResponse(**source)


@router.get("", response_model=SourceListResponse)
def list_sources() -> SourceListResponse:
    sources = get_source_store().list_sources()
    return SourceListResponse(sources=[_response(item) for item in sources], count=len(sources))


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreateRequest) -> SourceResponse:
    try:
        return _response(get_source_store().create(payload))
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{source_id}", response_model=SourceResponse)
def update_source(source_id: str, payload: SourceUpdateRequest) -> SourceResponse:
    try:
        return _response(get_source_store().update(source_id, payload))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{source_id}/test", response_model=SourceTestResponse)
def test_source(source_id: str) -> SourceTestResponse:
    try:
        source = get_source_store().get(source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.") from exc

    errors: list[str] = []
    try:
        _validate_source(source)
    except ValueError as exc:
        errors.append(str(exc))
    return SourceTestResponse(
        source_id=source.source_id,
        exists=True,
        enabled=source.enabled,
        source_type_supported=source.source_type in {"rss", "article_url"},
        url_https=source.url.lower().startswith("https://"),
        keywords_valid=bool(source.company_keywords or source.risk_keywords),
        test_status="config_valid" if not errors else "config_invalid",
        errors=errors,
    )
