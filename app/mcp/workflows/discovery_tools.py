"""Discovery tools for DJ workflow MCP server."""

from __future__ import annotations

import contextlib

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError
from app.mcp.dependencies import get_features_service, get_playlist_service
from app.mcp.types import SimilarTracksResult, TrackDetails
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.utils.audio.camelot import key_code_to_camelot


def register_discovery_tools(mcp: FastMCP) -> None:
    """Register discovery tools on the MCP server."""

    @mcp.tool(tags={"discovery"})
    async def find_similar_tracks(
        playlist_id: int,
        ctx: Context,
        count: int = 10,
        criteria: str = "bpm,key,energy",
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> SimilarTracksResult:
        """Find tracks similar to those in a playlist using LLM-assisted search.

        Analyses the playlist's audio profile (BPM range, keys, energy) and
        uses ctx.sample() to generate a smart search strategy.  Falls back
        to a basic profile summary when the MCP client does not support
        sampling / elicitation.

        Note: The actual Yandex Music search is not yet wired — this tool
        builds a profile and returns zero candidates until the full pipeline
        is connected.

        Args:
            playlist_id: Local playlist to base the search on.
            count: How many candidates to find.
            criteria: Comma-separated similarity criteria
                      (bpm, key, energy).
        """
        # 1. Build playlist audio profile
        items_list = await playlist_svc.list_items(
            playlist_id,
            offset=0,
            limit=500,
        )
        bpms: list[float] = []
        keys: list[str] = []
        energies: list[float] = []

        for item in items_list.items:
            try:
                feat = await features_svc.get_latest(item.track_id)
            except NotFoundError:
                continue
            bpms.append(feat.bpm)
            energies.append(feat.lufs_i)
            with contextlib.suppress(ValueError):
                cam = key_code_to_camelot(feat.key_code)
                if cam not in keys:
                    keys.append(cam)

        if not bpms:
            return SimilarTracksResult(
                playlist_id=playlist_id,
                candidates_found=0,
                candidates_selected=0,
                added_count=0,
            )

        bpm_range = (min(bpms), max(bpms))
        energy_range = (min(energies), max(energies))

        # 2. Try LLM-assisted strategy via ctx.sample()
        profile_text = (
            f"Playlist profile: BPM {bpm_range[0]:.0f}-{bpm_range[1]:.0f}, "
            f"keys {', '.join(keys[:8])}, "
            f"energy {energy_range[0]:.1f} to {energy_range[1]:.1f} LUFS. "
            f"Criteria: {criteria}. "
            f"Find {count} similar tracks."
        )

        await ctx.info(
            f"Playlist profile built: {len(bpms)} analysed tracks, "
            f"BPM {bpm_range[0]:.0f}-{bpm_range[1]:.0f}"
        )

        # Sampling requires client support — gracefully degrade
        strategy_text: str | None = None
        try:
            result = await ctx.sample(profile_text)
            strategy_text = result.text if hasattr(result, "text") else str(result)
        except (NotImplementedError, AttributeError, TypeError):
            strategy_text = None

        if strategy_text:
            with contextlib.suppress(Exception):
                await ctx.info(f"LLM search strategy: {strategy_text[:200]}")

        # 3. Return result (actual YM search would happen here)
        return SimilarTracksResult(
            playlist_id=playlist_id,
            candidates_found=0,
            candidates_selected=0,
            added_count=0,
        )

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"discovery"},
    )
    async def search_by_criteria(
        ctx: Context,
        features_svc: AudioFeaturesService = Depends(get_features_service),
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        keys: list[str] | None = None,
        energy_min: float | None = None,
        energy_max: float | None = None,
    ) -> list[TrackDetails]:
        """Search local tracks by audio feature criteria.

        Filters the analysed tracks in the database by BPM range,
        Camelot key list, and energy (LUFS) range.

        Args:
            bpm_min: Minimum BPM (inclusive).
            bpm_max: Maximum BPM (inclusive).
            keys: List of Camelot keys to match (e.g. ["8A", "9A"]).
            energy_min: Minimum integrated LUFS.
            energy_max: Maximum integrated LUFS.
        """
        all_features = await features_svc.list_all()

        results: list[TrackDetails] = []
        target_keys = set(keys) if keys else None

        for feat in all_features:
            if bpm_min is not None and feat.bpm < bpm_min:
                continue
            if bpm_max is not None and feat.bpm > bpm_max:
                continue
            if energy_min is not None and feat.lufs_i < energy_min:
                continue
            if energy_max is not None and feat.lufs_i > energy_max:
                continue

            if target_keys is not None:
                try:
                    cam = key_code_to_camelot(feat.key_code)
                except ValueError:
                    continue
                if cam not in target_keys:
                    continue

            camelot: str | None = None
            with contextlib.suppress(ValueError):
                camelot = key_code_to_camelot(feat.key_code)

            results.append(
                TrackDetails(
                    track_id=feat.track_id,
                    title="",
                    artists="",
                    duration_ms=None,
                    bpm=feat.bpm,
                    key=camelot,
                    energy_lufs=feat.lufs_i,
                    has_features=True,
                )
            )

        return results
