"""Library-wide statistics — aggregate counts for response envelopes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.catalog import Track
from app.models.dj import DjPlaylist
from app.models.features import TrackAudioFeaturesComputed
from app.models.sets import DjSet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_library_stats(session: AsyncSession) -> dict[str, int]:
    """Get library-wide counts (4 lightweight COUNT queries).

    Returns dict with: total_tracks, analyzed_tracks, total_playlists, total_sets.
    """
    tracks = (await session.execute(select(func.count(Track.track_id)))).scalar_one()
    analyzed = (
        await session.execute(
            select(func.count(func.distinct(TrackAudioFeaturesComputed.track_id)))
        )
    ).scalar_one()
    playlists = (await session.execute(select(func.count(DjPlaylist.playlist_id)))).scalar_one()
    sets = (await session.execute(select(func.count(DjSet.set_id)))).scalar_one()

    return {
        "total_tracks": tracks,
        "analyzed_tracks": analyzed,
        "total_playlists": playlists,
        "total_sets": sets,
    }
