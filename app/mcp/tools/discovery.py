"""Discovery tools for DJ workflow MCP server."""

from __future__ import annotations

import contextlib

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError
from app.mcp.dependencies import get_features_service, get_playlist_service
from app.mcp.resolve import resolve_local_id
from app.mcp.types import SimilarTracksResult
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.utils.audio.camelot import key_code_to_camelot


def register_discovery_tools(mcp: FastMCP) -> None:
    """Register discovery tools on the MCP server."""

    @mcp.tool(tags={"discovery"})
    async def find_similar_tracks(
        playlist_ref: str | int,
        ctx: Context,
        count: int = 10,
        criteria: str = "bpm,key,energy",
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> SimilarTracksResult:
        """Find tracks similar to those in a playlist using LLM-assisted search.

        DEPRECATED: This tool always returns 0 candidates. The actual discovery
        pipeline is implemented in `discover_candidates` and `expand_playlist_full`
        in curation_discovery.py. Use those instead.

        Analyses the playlist's audio profile (BPM range, keys, energy) and
        uses ctx.sample() to generate a smart search strategy.  Falls back
        to a basic profile summary when the MCP client does not support
        sampling / elicitation.

        Note: The actual Yandex Music search is not yet wired — this tool
        builds a profile and returns zero candidates until the full pipeline
        is connected.

        Args:
            playlist_ref: Local playlist ref (int, "42", or "local:42").
            count: How many candidates to find.
            criteria: Comma-separated similarity criteria
                      (bpm, key, energy).
        """
        playlist_id = resolve_local_id(playlist_ref, "playlist")
        # 1. Build playlist audio profile
        await ctx.report_progress(progress=0, total=100)
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

        await ctx.report_progress(progress=25, total=100)

        # Define a local search tool for the LLM to call during sampling
        async def _search_local_tracks(
            bpm_min: float | None = None,
            bpm_max: float | None = None,
            target_keys: list[str] | None = None,
            energy_min: float | None = None,
            energy_max: float | None = None,
        ) -> list[dict[str, object]]:
            """Search local tracks by BPM, key, and energy criteria.

            Returns a list of matching tracks with their audio features.
            """
            all_feats = await features_svc.list_all()
            matches: list[dict[str, object]] = []
            for feat in all_feats:
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
                matches.append(
                    {
                        "track_id": feat.track_id,
                        "bpm": feat.bpm,
                        "key": camelot,
                        "energy_lufs": feat.lufs_i,
                    }
                )
                if len(matches) >= count * 3:
                    break
            return matches

        # Sampling requires client support — gracefully degrade
        from app.mcp.types import SearchStrategy

        strategy: SearchStrategy | None = None
        strategy_text: str | None = None
        try:
            result = await ctx.sample(
                messages=profile_text,
                system_prompt=(
                    "You are a DJ assistant. Analyze the playlist audio profile "
                    "and use the search tool to find similar tracks. "
                    "Try different search criteria to find the best matches. "
                    "Return a SearchStrategy with your findings."
                ),
                tools=[_search_local_tracks],
                result_type=SearchStrategy,
            )
            strategy = result.result
            strategy_text = result.text
        except (NotImplementedError, AttributeError, TypeError, ValueError):
            strategy = None
            strategy_text = None

        await ctx.report_progress(progress=75, total=100)

        if strategy:
            with contextlib.suppress(Exception):
                await ctx.info(
                    f"LLM strategy: {len(strategy.queries)} queries, "
                    f"BPM {strategy.target_bpm_range[0]:.0f}-"
                    f"{strategy.target_bpm_range[1]:.0f}, "
                    f"keys {', '.join(strategy.target_keys[:4])}"
                )
        elif strategy_text:
            with contextlib.suppress(Exception):
                await ctx.info(f"LLM search strategy: {strategy_text[:200]}")

        # 3. Return result (actual YM search would happen here)
        await ctx.report_progress(progress=100, total=100)
        return SimilarTracksResult(
            playlist_id=playlist_id,
            candidates_found=0,
            candidates_selected=0,
            added_count=0,
        )
