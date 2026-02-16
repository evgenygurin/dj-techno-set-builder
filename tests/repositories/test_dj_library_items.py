"""Tests for DjLibraryItemRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.dj import DjLibraryItem
from app.repositories.dj_library_items import DjLibraryItemRepository


class TestDjLibraryItemRepository:
    async def test_get_by_track_id_returns_item_when_exists(self, session: AsyncSession):
        """get_by_track_id returns library item for track."""
        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create library item
        item = DjLibraryItem(
            track_id=track.track_id,
            file_path="/path/to/file.mp3",
            file_size_bytes=1024,
        )
        session.add(item)
        await session.commit()

        # Test get_by_track_id
        repo = DjLibraryItemRepository(session)
        result = await repo.get_by_track_id(track.track_id)

        assert result is not None
        assert result.track_id == track.track_id
        assert result.file_path == "/path/to/file.mp3"

    async def test_get_by_track_id_returns_none_when_not_exists(self, session: AsyncSession):
        """get_by_track_id returns None when no library item exists."""
        repo = DjLibraryItemRepository(session)
        result = await repo.get_by_track_id(999)

        assert result is None
