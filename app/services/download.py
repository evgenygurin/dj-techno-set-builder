"""Service for downloading tracks from Yandex Music."""

import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.yandex_music_client import YandexMusicClient


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

    def _generate_filename(self, track) -> str:
        """Generate sanitized filename for track.

        Format: {track_id}_{sanitized_title}.mp3

        Args:
            track: Track model instance

        Returns:
            Filename string (e.g. "42_fire_eyes.mp3")
        """
        sanitized = self._sanitize_filename(track.title)
        return f"{track.track_id}_{sanitized}.mp3"

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
        safe = re.sub(r'[/\\:*?"<>|]', '', title)
        # Replace spaces with underscores
        safe = safe.replace(' ', '_')
        # Replace multiple underscores with single
        safe = re.sub(r'_+', '_', safe)
        # Lowercase
        safe = safe.lower()
        # Truncate to max_len
        safe = safe[:max_len]
        # Remove trailing underscores
        safe = safe.rstrip('_')
        return safe or "untitled"
