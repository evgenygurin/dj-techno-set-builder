from typing import Any

from sqlalchemy import func, select

from app.models.dj import DjPlaylist, DjPlaylistItem
from app.infrastructure.repositories.base import BaseRepository


class DjPlaylistRepository(BaseRepository[DjPlaylist]):
    model = DjPlaylist

    async def search_by_name(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjPlaylist], int]:
        filters: list[Any] = [DjPlaylist.name.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def get_track_counts_batch(self, playlist_ids: list[int]) -> dict[int, int]:
        """Return {playlist_id: item_count} for the given playlist IDs.

        Single query — avoids N+1 in list_playlists / PlaylistFinder.
        """
        if not playlist_ids:
            return {}
        stmt = (
            select(DjPlaylistItem.playlist_id, func.count().label("cnt"))
            .where(DjPlaylistItem.playlist_id.in_(playlist_ids))
            .group_by(DjPlaylistItem.playlist_id)
        )
        result = await self.session.execute(stmt)
        return {row.playlist_id: row.cnt for row in result}


class DjPlaylistItemRepository(BaseRepository[DjPlaylistItem]):
    model = DjPlaylistItem

    async def list_by_playlist(
        self, playlist_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjPlaylistItem], int]:
        filters: list[Any] = [DjPlaylistItem.playlist_id == playlist_id]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def get_counts_batch(self, playlist_ids: list[int]) -> dict[int, int]:
        """Return {playlist_id: item_count} for the given playlist IDs.

        Single query regardless of how many playlists — avoids N+1 in list_playlists.
        """
        if not playlist_ids:
            return {}
        stmt = (
            select(DjPlaylistItem.playlist_id, func.count().label("cnt"))
            .where(DjPlaylistItem.playlist_id.in_(playlist_ids))
            .group_by(DjPlaylistItem.playlist_id)
        )
        result = await self.session.execute(stmt)
        return {row.playlist_id: row.cnt for row in result}
