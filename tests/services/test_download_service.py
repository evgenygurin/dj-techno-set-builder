"""Tests for DownloadService."""

import asyncio
import hashlib
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.repositories.dj_library_items import DjLibraryItemRepository
from app.services.download import DownloadService


class TestDownloadService:
    def test_sanitize_filename_removes_special_chars(self):
        """_sanitize_filename removes / \\ : * ? " < > |"""
        result = DownloadService._sanitize_filename('Track / Name: Test?')
        assert result == "track_name_test"

    def test_sanitize_filename_replaces_spaces_with_underscores(self):
        """_sanitize_filename replaces spaces with underscores."""
        result = DownloadService._sanitize_filename('Fire Eyes')
        assert result == "fire_eyes"

    def test_sanitize_filename_truncates_to_max_len(self):
        """_sanitize_filename truncates to max_len (default 50)."""
        long_title = "A" * 100
        result = DownloadService._sanitize_filename(long_title)
        assert len(result) == 50
        assert result == "a" * 50

    def test_sanitize_filename_removes_trailing_underscores(self):
        """_sanitize_filename removes trailing underscores."""
        result = DownloadService._sanitize_filename('Track   ')
        assert result == "track"

    def test_sanitize_filename_returns_untitled_when_empty(self):
        """_sanitize_filename returns 'untitled' for empty input."""
        result = DownloadService._sanitize_filename('////')
        assert result == "untitled"

    def test_generate_filename_combines_track_id_and_title(self):
        """_generate_filename creates {track_id}_{sanitized_title}.mp3"""
        svc = DownloadService(Mock(), Mock(), Mock())
        track = Mock(track_id=42, title="Fire Eyes")
        result = svc._generate_filename(track)
        assert result == "42_fire_eyes.mp3"

    def test_generate_filename_sanitizes_title(self):
        """_generate_filename sanitizes track title."""
        svc = DownloadService(Mock(), Mock(), Mock())
        track = Mock(track_id=137, title="Track / Name?")
        result = svc._generate_filename(track)
        assert result == "137_track_name.mp3"

    async def test_get_yandex_track_id_returns_value_when_exists(
        self, session: AsyncSession, tmp_path
    ):
        """_get_yandex_track_id returns YM track_id from provider_track_ids."""
        # Create provider (Yandex)
        provider = Provider(provider_id=1, provider_code="yandex", name="Yandex Music")
        session.add(provider)
        await session.flush()

        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider track ID
        provider_track_id = ProviderTrackId(
            track_id=track.track_id,
            provider_id=provider.provider_id,
            provider_track_id="12345678",
        )
        session.add(provider_track_id)
        await session.commit()

        # Test
        svc = DownloadService(session, Mock(), tmp_path)
        result = await svc._get_yandex_track_id(track.track_id)

        assert result == "12345678"

    async def test_get_yandex_track_id_returns_none_when_not_exists(
        self, session: AsyncSession, tmp_path
    ):
        """_get_yandex_track_id returns None when no YM ID exists."""
        svc = DownloadService(session, Mock(), tmp_path)
        result = await svc._get_yandex_track_id(999)

        assert result is None

    async def test_download_single_track_success_creates_file_and_db_entry(
        self, session: AsyncSession, tmp_path: Path
    ):
        """_download_single_track downloads file and creates DjLibraryItem."""
        # Create provider
        provider = Provider(provider_id=1, provider_code="yandex", name="Yandex Music")
        session.add(provider)
        await session.flush()

        # Create track
        track = Track(title="Nova", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider ID
        provider_track_id = ProviderTrackId(
            track_id=track.track_id,
            provider_id=provider.provider_id,
            provider_track_id="12345",
        )
        session.add(provider_track_id)
        await session.commit()

        # Mock YM client
        mock_ym = Mock()
        mock_ym.download_track = AsyncMock(return_value=2048)

        # Mock file creation (YM client creates it)
        def mock_download(ym_id, dest_path, prefer_bitrate):
            Path(dest_path).write_bytes(b"fake mp3 data")
            return 2048

        mock_ym.download_track.side_effect = mock_download

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        success, size = await svc._download_single_track(track, prefer_bitrate=320)

        assert success is True
        assert size == 2048

        # Verify file exists
        expected_path = tmp_path / "1_nova.mp3"
        assert expected_path.exists()

        # Verify DjLibraryItem created
        repo = DjLibraryItemRepository(session)
        item = await repo.get_by_track_id(track.track_id)
        assert item is not None
        assert item.file_path == str(expected_path)
        assert item.file_size_bytes == 2048
        assert item.bitrate_kbps == 320

    async def test_download_single_track_retries_on_network_error(
        self, session: AsyncSession, tmp_path: Path
    ):
        """_download_single_track retries after network error."""
        # Create provider
        provider = Provider(provider_id=1, provider_code="yandex", name="Yandex Music")
        session.add(provider)
        await session.flush()

        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider ID
        provider_track_id = ProviderTrackId(
            track_id=track.track_id,
            provider_id=provider.provider_id,
            provider_track_id="12345",
        )
        session.add(provider_track_id)
        await session.commit()

        # Mock YM client: fail twice, succeed on third
        mock_ym = Mock()
        attempts = []

        async def mock_download(ym_id, dest_path, prefer_bitrate):
            attempts.append(1)
            if len(attempts) < 3:
                raise Exception("Network error")
            Path(dest_path).write_bytes(b"data")
            return 1024

        mock_ym.download_track = AsyncMock(side_effect=mock_download)

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        success, size = await svc._download_single_track(track, prefer_bitrate=320)

        assert success is True
        assert len(attempts) == 3  # Failed twice, succeeded on 3rd

    async def test_download_single_track_fails_after_max_retries(
        self, session: AsyncSession, tmp_path: Path
    ):
        """_download_single_track returns (False, 0) after max retries."""
        # Create provider
        provider = Provider(provider_id=1, provider_code="yandex", name="Yandex Music")
        session.add(provider)
        await session.flush()

        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider ID
        provider_track_id = ProviderTrackId(
            track_id=track.track_id,
            provider_id=provider.provider_id,
            provider_track_id="12345",
        )
        session.add(provider_track_id)
        await session.commit()

        # Mock YM client: always fail
        mock_ym = Mock()
        mock_ym.download_track = AsyncMock(side_effect=Exception("Always fail"))

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        success, size = await svc._download_single_track(track, prefer_bitrate=320)

        assert success is False
        assert size == 0
        assert mock_ym.download_track.call_count == 3  # 3 attempts
