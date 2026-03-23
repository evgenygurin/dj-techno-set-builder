from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.routers.v1._openapi import (
    RESPONSES_CREATE,
    RESPONSES_DELETE,
    RESPONSES_GET,
    RESPONSES_UPDATE,
)
from app.schemas.playlists import (
    DjPlaylistCreate,
    DjPlaylistItemCreate,
    DjPlaylistItemList,
    DjPlaylistItemRead,
    DjPlaylistList,
    DjPlaylistRead,
    DjPlaylistUpdate,
)
from app.services.playlists import DjPlaylistService

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _service(db: DbSession) -> DjPlaylistService:
    from app.services._factories import build_playlist_service

    return build_playlist_service(db)


# ─── Playlist CRUD ───────────────────────────────────────


@router.get(
    "",
    response_model=DjPlaylistList,
    summary="List playlists",
    description="Retrieve a paginated list of DJ playlists. Supports text search by name.",
    response_description="Paginated list of playlists with total count",
    operation_id="list_playlists",
)
async def list_playlists(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: str | None = Query(
        default=None,
        description="Search playlists by name (case-insensitive)",
    ),
) -> DjPlaylistList:
    return await _service(db).list(offset=offset, limit=limit, search=search)


@router.get(
    "/{playlist_id}",
    response_model=DjPlaylistRead,
    summary="Get playlist",
    description="Retrieve a single DJ playlist by its unique identifier.",
    response_description="The playlist details",
    responses=RESPONSES_GET,
    operation_id="get_playlist",
)
async def get_playlist(playlist_id: int, db: DbSession) -> DjPlaylistRead:
    return await _service(db).get(playlist_id)


@router.post(
    "",
    response_model=DjPlaylistRead,
    status_code=201,
    summary="Create playlist",
    description="Create a new DJ playlist. Set `parent_playlist_id` for folder hierarchy.",
    response_description="The created playlist",
    responses=RESPONSES_CREATE,
    operation_id="create_playlist",
)
async def create_playlist(data: DjPlaylistCreate, db: DbSession) -> DjPlaylistRead:
    result = await _service(db).create(data)
    await db.commit()
    return result


@router.patch(
    "/{playlist_id}",
    response_model=DjPlaylistRead,
    summary="Update playlist",
    description="Partially update an existing DJ playlist. Only provided fields are modified.",
    response_description="The updated playlist",
    responses=RESPONSES_UPDATE,
    operation_id="update_playlist",
)
async def update_playlist(
    playlist_id: int, data: DjPlaylistUpdate, db: DbSession
) -> DjPlaylistRead:
    result = await _service(db).update(playlist_id, data)
    await db.commit()
    return result


@router.delete(
    "/{playlist_id}",
    status_code=204,
    summary="Delete playlist",
    description="Permanently delete a DJ playlist and all its items.",
    responses=RESPONSES_DELETE,
    operation_id="delete_playlist",
)
async def delete_playlist(playlist_id: int, db: DbSession) -> None:
    await _service(db).delete(playlist_id)
    await db.commit()


# ─── Playlist Items ──────────────────────────────────────


@router.get(
    "/{playlist_id}/items",
    response_model=DjPlaylistItemList,
    summary="List playlist items",
    description="Retrieve the ordered track list for a specific playlist.",
    response_description="Paginated list of playlist items with total count",
    responses=RESPONSES_GET,
    operation_id="list_playlist_items",
)
async def list_playlist_items(
    playlist_id: int,
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> DjPlaylistItemList:
    return await _service(db).list_items(playlist_id, offset=offset, limit=limit)


@router.post(
    "/{playlist_id}/items",
    response_model=DjPlaylistItemRead,
    status_code=201,
    summary="Add item to playlist",
    description="Add a track to a playlist at the specified sort index.",
    response_description="The created playlist item",
    responses=RESPONSES_CREATE,
    operation_id="add_playlist_item",
)
async def add_playlist_item(
    playlist_id: int, data: DjPlaylistItemCreate, db: DbSession
) -> DjPlaylistItemRead:
    result = await _service(db).add_item(playlist_id, data)
    await db.commit()
    return result


@router.delete(
    "/{playlist_id}/items/{playlist_item_id}",
    status_code=204,
    summary="Remove item from playlist",
    description="Remove a track from a playlist by item ID.",
    responses=RESPONSES_DELETE,
    operation_id="remove_playlist_item",
)
async def remove_playlist_item(
    playlist_id: int,
    playlist_item_id: int,
    db: DbSession,
) -> None:
    await _service(db).remove_item(playlist_item_id)
    await db.commit()
