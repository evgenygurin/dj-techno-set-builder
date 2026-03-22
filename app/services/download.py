"""Service for downloading tracks from Yandex Music."""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.repositories.dj_library_items import DjLibraryItemRepository
from app.repositories.tracks import TrackRepository
from app.services.yandex_music_client import YandexMusicClient

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Statistics from batch download operation."""

    downloaded: int
    skipped: int
    failed: int
    failed_track_ids: list[int]
    total_bytes: int


class DownloadService:
    """Service for downloading tracks from Yandex Music to local library."""

    def __init__(
        self,
        session: AsyncSession,
        ym_client: YandexMusicClient,
        library_path: Path,
    ):
        """Initialize download service.

        Args:
            session: Database session
            ym_client: Yandex Music API client
            library_path: Path to library directory for downloads
        """
        self.session = session
        self.ym_client = ym_client
        self.library_path = library_path
        self.library_repo = DjLibraryItemRepository(session)
        self.track_repo = TrackRepository(session)

    def _generate_filename(self, track: Track) -> str:
        """Generate sanitized filename for track.

        Format: {track_id}_{sanitized_title}.mp3

        Args:
            track: Track model instance

        Returns:
            Filename string (e.g. "42_fire_eyes.mp3")
        """
        sanitized = self._sanitize_filename(track.title)
        return f"{track.track_id}_{sanitized}.mp3"

    async def _get_yandex_track_id(self, track_id: int) -> str | None:
        """Get Yandex Music track ID from provider_track_ids table.

        Args:
            track_id: Local track ID

        Returns:
            Yandex Music track ID string, or None if not found
        """
        stmt = (
            select(ProviderTrackId.provider_track_id)
            .join(Provider)
            .where(ProviderTrackId.track_id == track_id)
            .where(Provider.provider_code == "yandex")
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _download_single_track(
        self,
        track: Track,
        prefer_bitrate: int,
        max_retries: int = 3,
    ) -> tuple[bool, int]:
        """Download single track with exponential backoff retry.

        Args:
            track: Track model instance
            prefer_bitrate: Preferred bitrate in kbps
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            (success: bool, file_size: int)
        """
        for attempt in range(max_retries):
            try:
                # 1. Get Yandex Music track ID
                ym_id = await self._get_yandex_track_id(track.track_id)
                if not ym_id:
                    logger.error(f"No Yandex Music ID for track {track.track_id}")
                    return (False, 0)

                # 2. Generate filename
                filename = self._generate_filename(track)
                dest_path = self.library_path / filename

                # 3. Download via YM client
                size = await self.ym_client.download_track(
                    ym_id, str(dest_path), prefer_bitrate=prefer_bitrate
                )

                # 4. Calculate SHA256 hash
                file_hash = hashlib.sha256(dest_path.read_bytes()).digest()

                # 5. Save to DjLibraryItem
                await self.library_repo.create_from_download(
                    track_id=track.track_id,
                    file_path=str(dest_path),
                    file_size=size,
                    file_hash=file_hash,
                    bitrate_kbps=prefer_bitrate,
                )

                logger.info(f"Downloaded track {track.track_id} ({size} bytes)")
                return (True, size)

            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"Download attempt {attempt + 1} failed for track "
                        f"{track.track_id}, retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed to download track {track.track_id} after "
                        f"{max_retries} attempts: {e}"
                    )
                    return (False, 0)

        return (False, 0)

    async def download_tracks_batch(
        self,
        track_ids: list[int],
        prefer_bitrate: int = 320,
    ) -> DownloadResult:
        """Download multiple tracks with retry and statistics.

        Runs sequentially — YM rate limiter enforces 1.5s between requests,
        and the shared DB session (SQLite) doesn't support concurrent writes.

        Args:
            track_ids: List of track IDs to download
            prefer_bitrate: Preferred bitrate in kbps (default: 320)

        Returns:
            DownloadResult with download statistics
        """
        # Ensure library directory exists
        self.library_path.mkdir(parents=True, exist_ok=True)

        downloaded = 0
        skipped = 0
        failed = 0
        failed_ids: list[int] = []
        total_bytes = 0

        for track_id in track_ids:
            # Check if already downloaded
            existing = await self.library_repo.get_by_track_id(track_id)
            if existing and existing.file_path:
                logger.info(f"Track {track_id} already downloaded, skipping")
                skipped += 1
                continue

            # Get track from DB
            track = await self.track_repo.get_by_id(track_id)
            if not track:
                logger.warning(f"Track {track_id} not found in database")
                failed += 1
                failed_ids.append(track_id)
                continue

            # Download with retry
            success, size = await self._download_single_track(track, prefer_bitrate)

            if success:
                downloaded += 1
                total_bytes += size
            else:
                failed += 1
                failed_ids.append(track_id)

        logger.info(
            f"Download batch complete: {downloaded} downloaded, {skipped} skipped, {failed} failed"
        )

        return DownloadResult(
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            failed_track_ids=failed_ids,
            total_bytes=total_bytes,
        )

    @staticmethod
    def _sanitize_filename(title: str, max_len: int = 50) -> str:
        """Sanitize title for use in filename.

        Removes special characters (/ \\ : * ? " < > |), replaces spaces
        with underscores, converts to lowercase, truncates to max_len.

        Args:
            title: Track title to sanitize
            max_len: Maximum length (default: 50)

        Returns:
            Sanitized filename-safe string, or "untitled" if empty
        """
        # Remove special characters: / \ : * ? " < > |
        safe = re.sub(r'[/\\:*?"<>|]', "", title)
        # Replace spaces with underscores
        safe = safe.replace(" ", "_")
        # Replace multiple underscores with single
        safe = re.sub(r"_+", "_", safe)
        # Lowercase
        safe = safe.lower()
        # Truncate to max_len
        safe = safe[:max_len]
        # Remove trailing underscores
        safe = safe.rstrip("_")
        return safe or "untitled"
