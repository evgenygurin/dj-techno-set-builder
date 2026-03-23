"""Library-wide statistics for response envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.mcp.types import LibraryStats
from app.core.models.catalog import Track
from app.core.models.dj import DjPlaylist
from app.core.models.features import TrackAudioFeaturesComputed
from app.core.models.sets import DjSet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_library_stats(session: AsyncSession) -> LibraryStats:
    """Get library-wide counts (4 lightweight COUNT queries)."""
    tracks = (await session.execute(select(func.count(Track.track_id)))).scalar_one()
    analyzed = (
        await session.execute(
            select(func.count(func.distinct(TrackAudioFeaturesComputed.track_id)))
        )
    ).scalar_one()
    playlists = (await session.execute(select(func.count(DjPlaylist.playlist_id)))).scalar_one()
    sets = (await session.execute(select(func.count(DjSet.set_id)))).scalar_one()

    return LibraryStats(
        total_tracks=tracks,
        analyzed_tracks=analyzed,
        total_playlists=playlists,
        total_sets=sets,
    )
