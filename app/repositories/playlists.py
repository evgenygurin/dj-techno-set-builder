from typing import Any

from app.models.dj import DjPlaylist, DjPlaylistItem
from app.repositories.base import BaseRepository


class DjPlaylistRepository(BaseRepository[DjPlaylist]):
    model = DjPlaylist

    async def search_by_name(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjPlaylist], int]:
        filters: list[Any] = [DjPlaylist.name.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)


class DjPlaylistItemRepository(BaseRepository[DjPlaylistItem]):
    model = DjPlaylistItem

    async def list_by_playlist(
        self, playlist_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjPlaylistItem], int]:
        filters: list[Any] = [DjPlaylistItem.playlist_id == playlist_id]
        return await self.list(offset=offset, limit=limit, filters=filters)
