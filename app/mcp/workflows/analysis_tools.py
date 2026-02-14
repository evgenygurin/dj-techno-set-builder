"""Read-only analysis tools for DJ workflow MCP server."""

from __future__ import annotations

import contextlib

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError
from app.mcp.dependencies import get_features_service, get_playlist_service, get_track_service
from app.mcp.types import PlaylistStatus, TrackDetails
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.services.tracks import TrackService
from app.utils.audio.camelot import key_code_to_camelot


def register_analysis_tools(mcp: FastMCP) -> None:
    """Register read-only analysis tools on the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"analysis", "status"},
    )
    async def get_playlist_status(
        playlist_id: int,
        ctx: Context,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
        track_svc: TrackService = Depends(get_track_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> PlaylistStatus:
        """Get full status of a playlist: tracks, analysis progress, BPM/key/energy stats.

        Call this first to understand what's in a playlist before
        running analysis or building sets.
        """
        playlist = await playlist_svc.get(playlist_id)
        items_list = await playlist_svc.list_items(playlist_id, offset=0, limit=500)

        bpms: list[float] = []
        keys: list[str] = []
        energies: list[float] = []
        total_duration_ms = 0
        analyzed = 0

        for item in items_list.items:
            # Accumulate duration from track metadata
            with contextlib.suppress(NotFoundError):
                track = await track_svc.get(item.track_id)
                total_duration_ms += track.duration_ms

            try:
                features = await features_svc.get_latest(item.track_id)
            except NotFoundError:
                continue

            analyzed += 1
            bpms.append(features.bpm)
            energies.append(features.lufs_i)

            try:
                camelot = key_code_to_camelot(features.key_code)
                if camelot not in keys:
                    keys.append(camelot)
            except ValueError:
                pass

        bpm_range: tuple[float, float] | None = None
        if bpms:
            bpm_range = (min(bpms), max(bpms))

        avg_energy: float | None = None
        if energies:
            avg_energy = sum(energies) / len(energies)

        duration_minutes = total_duration_ms / 60_000.0

        return PlaylistStatus(
            playlist_id=playlist.playlist_id,
            name=playlist.name,
            total_tracks=items_list.total,
            analyzed_tracks=analyzed,
            bpm_range=bpm_range,
            keys=keys,
            avg_energy=avg_energy,
            duration_minutes=round(duration_minutes, 1),
        )

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"analysis", "details"},
    )
    async def get_track_details(
        track_id: int,
        ctx: Context,
        track_svc: TrackService = Depends(get_track_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> TrackDetails:
        """Get full details of a track including audio features.

        Returns metadata and extracted audio features (BPM, key, energy).
        """
        track = await track_svc.get(track_id)

        bpm: float | None = None
        key: str | None = None
        energy_lufs: float | None = None
        has_features = False

        try:
            features = await features_svc.get_latest(track_id)
            has_features = True
            bpm = features.bpm
            energy_lufs = features.lufs_i
            with contextlib.suppress(ValueError):
                key = key_code_to_camelot(features.key_code)
        except NotFoundError:
            pass

        return TrackDetails(
            track_id=track.track_id,
            title=track.title,
            artists="",
            duration_ms=track.duration_ms,
            bpm=bpm,
            key=key,
            energy_lufs=energy_lufs,
            has_features=has_features,
        )
