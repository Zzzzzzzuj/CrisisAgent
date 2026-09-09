from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.watchlist_schemas import WatchlistCreateRequest, WatchlistListResponse, WatchlistResponse, WatchlistUpdateRequest
from backend.api.watchlist_store import get_watchlist_store
from backend.api.workspace_security import authorize, get_workspace_user, owner_fields, write_audit


router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])
READ = {"admin", "operator", "legal_reviewer", "viewer"}
WRITE = {"admin", "operator"}


@router.get("", response_model=WatchlistListResponse)
def list_watchlists(enabled: bool | None = Query(default=None), user: dict = Depends(get_workspace_user)):
    authorize(user, READ, "watchlist.list", "watchlist")
    values = get_watchlist_store().list(enabled)
    return WatchlistListResponse(watchlists=[WatchlistResponse(**item) for item in values], count=len(values))


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
def create_watchlist(payload: WatchlistCreateRequest, user: dict = Depends(get_workspace_user)):
    authorize(user, WRITE, "watchlist.create", "watchlist")
    try:
        value = get_watchlist_store().create(payload, str(user.get("id", "demo-system")), owner_fields(user)["owner_id"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(user, "watchlist.create", "watchlist", value["entity_id"])
    return WatchlistResponse(**value)


@router.get("/{entity_id}", response_model=WatchlistResponse)
def get_watchlist(entity_id: str, user: dict = Depends(get_workspace_user)):
    authorize(user, READ, "watchlist.view", "watchlist", entity_id)
    value = get_watchlist_store().get(entity_id)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Watchlist '{entity_id}' not found.")
    return WatchlistResponse(**value)


@router.patch("/{entity_id}", response_model=WatchlistResponse)
def update_watchlist(entity_id: str, payload: WatchlistUpdateRequest, user: dict = Depends(get_workspace_user)):
    authorize(user, WRITE, "watchlist.update", "watchlist", entity_id)
    try:
        value = get_watchlist_store().update(entity_id, payload, str(user.get("id", "demo-system")))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Watchlist '{exc.args[0]}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(user, "watchlist.update", "watchlist", entity_id)
    return WatchlistResponse(**value)


@router.post("/{entity_id}/archive", response_model=WatchlistResponse)
def archive_watchlist(entity_id: str, user: dict = Depends(get_workspace_user)):
    authorize(user, WRITE, "watchlist.archive", "watchlist", entity_id)
    try:
        value = get_watchlist_store().archive(entity_id, str(user.get("id", "demo-system")))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Watchlist '{exc.args[0]}' not found.") from exc
    write_audit(user, "watchlist.archive", "watchlist", entity_id)
    return WatchlistResponse(**value)
