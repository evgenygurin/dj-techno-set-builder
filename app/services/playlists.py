from __future__ import annotations

from sqlalchemy import select

from app.errors import NotFoundError
from app.models.dj import DjPlaylistItem
from app.models.ingestion import ProviderTrackId
from app.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
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

    async def get_track_count(self, playlist_id: int) -> int:
        """Get the number of tracks in a playlist."""
        _, total = await self.item_repo.list_by_playlist(playlist_id, offset=0, limit=0)
        return total

    async def match_ym_ids_to_track_ids(
        self, ym_ids: list[str], ym_provider_id: int = 4,
    ) -> set[int]:
        """Match YM track IDs to local track_ids via provider_track_ids."""
        session = self.item_repo.session
        stmt = select(ProviderTrackId.track_id).where(
            ProviderTrackId.provider_id == ym_provider_id,
            ProviderTrackId.provider_track_id.in_(ym_ids),
        )
        result = await session.execute(stmt)
        return {row[0] for row in result}

    async def populate_from_track_ids(
        self, playlist_id: int, track_ids: set[int],
    ) -> tuple[int, int]:
        """Add track_ids to playlist, skipping duplicates. Returns (added, skipped)."""
        existing_items, _ = await self.item_repo.list_by_playlist(
            playlist_id, offset=0, limit=10000,
        )
        existing = {item.track_id for item in existing_items}
        next_sort = len(existing_items)
        added = skipped = 0
        session = self.item_repo.session

        for track_id in track_ids:
            if track_id in existing:
                skipped += 1
                continue
            session.add(
                DjPlaylistItem(
                    playlist_id=playlist_id,
                    track_id=track_id,
                    sort_index=next_sort,
                )
            )
            next_sort += 1
            added += 1

        await session.flush()
        return added, skipped

    async def link_platform(
        self, playlist_id: int, platform: str, platform_id: str,
    ) -> None:
        """Update platform_ids on a playlist."""
        playlist = await self.repo.get_by_id(playlist_id)
        if playlist is not None:
            current = playlist.platform_ids or {}
            current[platform] = platform_id
            playlist.platform_ids = current

    # --- Helpers ---

    async def _require_playlist(self, playlist_id: int) -> None:
        playlist = await self.repo.get_by_id(playlist_id)
        if not playlist:
            raise NotFoundError("DjPlaylist", playlist_id=playlist_id)
