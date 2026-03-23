from app.core.errors import NotFoundError
from app.infrastructure.repositories.playlists import (
    DjPlaylistItemRepository,
    DjPlaylistRepository,
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
from app.services.base import BaseService


class DjPlaylistService(BaseService):
    def __init__(
        self,
        repo: DjPlaylistRepository,
        item_repo: DjPlaylistItemRepository,
    ) -> None:
        super().__init__()
        self.repo = repo
        self.item_repo = item_repo

    # --- Playlist CRUD ---

    async def get(self, playlist_id: int) -> DjPlaylistRead:
        playlist = await self.repo.get_by_id(playlist_id)
        if not playlist:
            raise NotFoundError("DjPlaylist", playlist_id=playlist_id)
        return DjPlaylistRead.model_validate(playlist)

    async def list(
        self, *, offset: int = 0, limit: int = 50, search: str | None = None
    ) -> DjPlaylistList:
        if search:
            items, total = await self.repo.search_by_name(search, offset=offset, limit=limit)
        else:
            items, total = await self.repo.list(offset=offset, limit=limit)
        return DjPlaylistList(
            items=[DjPlaylistRead.model_validate(p) for p in items],
            total=total,
        )

    async def create(self, data: DjPlaylistCreate) -> DjPlaylistRead:
        playlist = await self.repo.create(**data.model_dump())
        return DjPlaylistRead.model_validate(playlist)

    async def update(self, playlist_id: int, data: DjPlaylistUpdate) -> DjPlaylistRead:
        playlist = await self.repo.get_by_id(playlist_id)
        if not playlist:
            raise NotFoundError("DjPlaylist", playlist_id=playlist_id)
        updated = await self.repo.update(playlist, **data.model_dump(exclude_unset=True))
        return DjPlaylistRead.model_validate(updated)

    async def delete(self, playlist_id: int) -> None:
        playlist = await self.repo.get_by_id(playlist_id)
        if not playlist:
            raise NotFoundError("DjPlaylist", playlist_id=playlist_id)
        await self.repo.delete(playlist)

    # --- Playlist Items ---

    async def list_items(
        self, playlist_id: int, *, offset: int = 0, limit: int = 50
    ) -> DjPlaylistItemList:
        await self._require_playlist(playlist_id)
        items, total = await self.item_repo.list_by_playlist(
            playlist_id, offset=offset, limit=limit
        )
        return DjPlaylistItemList(
            items=[DjPlaylistItemRead.model_validate(i) for i in items],
            total=total,
        )

    async def add_item(self, playlist_id: int, data: DjPlaylistItemCreate) -> DjPlaylistItemRead:
        await self._require_playlist(playlist_id)
        item = await self.item_repo.create(playlist_id=playlist_id, **data.model_dump())
        return DjPlaylistItemRead.model_validate(item)

    async def remove_item(self, playlist_item_id: int) -> None:
        item = await self.item_repo.get_by_id(playlist_item_id)
        if not item:
            raise NotFoundError("DjPlaylistItem", playlist_item_id=playlist_item_id)
        await self.item_repo.delete(item)

    # --- Helpers ---

    async def _require_playlist(self, playlist_id: int) -> None:
        playlist = await self.repo.get_by_id(playlist_id)
        if not playlist:
            raise NotFoundError("DjPlaylist", playlist_id=playlist_id)
