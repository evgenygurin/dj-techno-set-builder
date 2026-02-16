"""Tests for DownloadService."""

import pytest
from unittest.mock import Mock
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
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
