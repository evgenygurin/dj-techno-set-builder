"""Repository for DjLibraryItem — file management for DJ library."""

from sqlalchemy import select

from app.core.models.dj import DjLibraryItem
from app.infrastructure.repositories.base import BaseRepository


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

    async def create_from_download(
        self,
        track_id: int,
        file_path: str,
        file_size: int,
        file_hash: bytes,
        bitrate_kbps: int,
        mime_type: str = "audio/mpeg",
    ) -> DjLibraryItem:
        """Create library item after successful download.

        Args:
            track_id: Track ID
            file_path: Absolute path to downloaded file
            file_size: File size in bytes
            file_hash: SHA256 hash of file contents
            bitrate_kbps: Bitrate in kbps (e.g. 320)
            mime_type: MIME type (default: audio/mpeg)

        Returns:
            Created DjLibraryItem
        """
        item = DjLibraryItem(
            track_id=track_id,
            file_path=file_path,
            file_size_bytes=file_size,
            file_hash=file_hash,
            bitrate_kbps=bitrate_kbps,
            mime_type=mime_type,
        )
        self.session.add(item)
        await self.session.flush()
        return item
