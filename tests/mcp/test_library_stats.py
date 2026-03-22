"""Tests for library stats service."""

from unittest.mock import AsyncMock

from app.mcp.library_stats import get_library_stats
from app.mcp.types import LibraryStats


def _scalar(value: int) -> AsyncMock:
    """Create a mock result with scalar_one() returning value."""
    mock = AsyncMock()
    mock.scalar_one = lambda: value
    return mock


async def test_get_library_stats():
    session = AsyncMock()
    # Mock execute to return scalars for 4 COUNT queries
    session.execute = AsyncMock()
    session.execute.side_effect = [
        _scalar(3247),  # tracks
        _scalar(2890),  # analyzed (features)
        _scalar(15),  # playlists
        _scalar(8),  # sets
    ]

    stats = await get_library_stats(session)
    assert isinstance(stats, LibraryStats)
    assert stats.total_tracks == 3247
    assert stats.analyzed_tracks == 2890
    assert stats.total_playlists == 15
    assert stats.total_sets == 8


async def test_get_library_stats_empty():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.execute.side_effect = [
        _scalar(0),
        _scalar(0),
        _scalar(0),
        _scalar(0),
    ]

    stats = await get_library_stats(session)
    assert stats.total_tracks == 0
    assert stats.analyzed_tracks == 0
