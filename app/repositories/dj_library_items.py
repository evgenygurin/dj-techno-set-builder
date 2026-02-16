"""Repository for DjLibraryItem — file management for DJ library."""

from sqlalchemy import select

from app.models.dj import DjLibraryItem
from app.repositories.base import BaseRepository


class DjLibraryItemRepository(BaseRepository[DjLibraryItem]):
    """Repository for DJ library file management."""

    async def get_by_track_id(self, track_id: int) -> DjLibraryItem | None:
        """Find library item for a track.

        Args:
            track_id: Track ID to search for

        Returns:
            DjLibraryItem if exists, None otherwise
        """
        stmt = select(DjLibraryItem).where(DjLibraryItem.track_id == track_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
