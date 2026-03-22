"""Tests for TrackMapper using ProviderTrackId table."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.sync.track_mapper import DbTrackMapper
from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider


@pytest.fixture
async def seed_data(session: AsyncSession) -> None:
    """Seed providers, tracks, and provider_track_ids."""
    # Provider — use merge() to handle pre-existing rows from other tests
    await session.merge(Provider(provider_id=4, provider_code="ym", name="Yandex Music"))
    await session.flush()
    # Tracks — use merge() to handle pre-existing rows
    for t in [
        Track(track_id=1, title="Alpha", duration_ms=300000, status=0),
        Track(track_id=2, title="Beta", duration_ms=300000, status=0),
        Track(track_id=3, title="Gamma", duration_ms=300000, status=0),
    ]:
        await session.merge(t)
    await session.flush()
    # Provider track IDs — use merge() to handle pre-existing rows
    for ptid in [
        ProviderTrackId(id=90001, track_id=1, provider_id=4, provider_track_id="ym_111"),
        ProviderTrackId(id=90002, track_id=2, provider_id=4, provider_track_id="ym_222"),
        # track 3 has no YM mapping
    ]:
        await session.merge(ptid)
    await session.flush()


class TestDbTrackMapper:
    async def test_local_to_platform(self, session: AsyncSession, seed_data: None) -> None:
        mapper = DbTrackMapper(session)
        result = await mapper.local_to_platform([1, 2, 3], "ym")

        assert result[1] == "ym_111"
        assert result[2] == "ym_222"
        assert 3 not in result  # no mapping

    async def test_platform_to_local(self, session: AsyncSession, seed_data: None) -> None:
        mapper = DbTrackMapper(session)
        result = await mapper.platform_to_local(["ym_111", "ym_222", "ym_999"], "ym")

        assert result["ym_111"] == 1
        assert result["ym_222"] == 2
        assert result["ym_999"] is None  # unknown

    async def test_local_to_platform_empty(self, session: AsyncSession, seed_data: None) -> None:
        mapper = DbTrackMapper(session)
        result = await mapper.local_to_platform([], "ym")
        assert result == {}

    async def test_platform_to_local_empty(self, session: AsyncSession, seed_data: None) -> None:
        mapper = DbTrackMapper(session)
        result = await mapper.platform_to_local([], "ym")
        assert result == {}

    async def test_unknown_provider(self, session: AsyncSession, seed_data: None) -> None:
        mapper = DbTrackMapper(session)
        result = await mapper.local_to_platform([1, 2], "spotify")
        assert result == {}  # no spotify mappings
