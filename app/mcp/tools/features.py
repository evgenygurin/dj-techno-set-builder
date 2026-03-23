"""AudioFeatures CRUD tools for DJ workflow MCP server.

list_features — paginated list of tracks with computed features
get_features — full features for a single track (Level 3: Full, ~2 KB)
save_features — persist computed features from analyze_track
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.infrastructure.repositories.audio_features import AudioFeaturesRepository
from app.infrastructure.repositories.tracks import TrackRepository
from app.mcp.converters import track_to_summary
from app.mcp.dependencies import get_session
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types import ActionResponse, EntityDetailResponse, EntityListResponse
from app.services.features import AudioFeaturesService


def register_features_tools(mcp: FastMCP) -> None:
    """Register AudioFeatures CRUD tools on the MCP server."""

    @mcp.tool(tags={"crud", "features"}, annotations={"readOnlyHint": True})
    async def list_features(
        limit: int = 20,
        cursor: str | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> EntityListResponse:
        """List tracks that have computed audio features.

        Returns TrackSummary with BPM/key/energy populated from features.
        Optional BPM range filter.

        Args:
            limit: Max results per page.
            cursor: Pagination cursor.
            bpm_min: Minimum BPM filter.
            bpm_max: Maximum BPM filter.
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        features_repo = AudioFeaturesRepository(session)
        track_repo = TrackRepository(session)

        if bpm_min is not None or bpm_max is not None:
            features_list, total = await features_repo.filter_by_criteria(
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                offset=offset,
                limit=clamped,
            )
        else:
            all_features = await features_repo.list_all()
            total = len(all_features)
            features_list = all_features[offset : offset + clamped]

        track_ids = [f.track_id for f in features_list]
        tracks_by_id = {}
        artists_map: dict[int, list[str]] = {}
        if track_ids:
            for tid in track_ids:
                t = await track_repo.get_by_id(tid)
                if t:
                    tracks_by_id[tid] = t
            artists_map = await track_repo.get_artists_for_tracks(track_ids)

        summaries = []
        for f in features_list:
            track = tracks_by_id.get(f.track_id)
            if track:
                summaries.append(track_to_summary(track, artists_map, features=f))

        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "features"}, annotations={"readOnlyHint": True})
    async def get_features(
        track_ref: str | int,
        session: AsyncSession = Depends(get_session),
    ) -> EntityDetailResponse:
        """Get full audio features for a track (Level 3: Full, ~2 KB).

        Returns all computed audio parameters: BPM, key, loudness, energy,
        spectral, rhythm, MFCC.

        Args:
            track_ref: Track reference (must resolve to exact ID).
        """
        ref = parse_ref(track_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            raise ToolError(f"get_features requires exact ref: {track_ref}")

        svc = AudioFeaturesService(
            AudioFeaturesRepository(session),
            TrackRepository(session),
        )
        try:
            features = await svc.get_latest(ref.local_id)
        except (NotFoundError, ValueError):
            raise ToolError(f"No features found: {track_ref}") from None

        return await wrap_detail(features, session)

    @mcp.tool(tags={"crud", "features"}, annotations={"idempotentHint": True})
    async def save_features(
        track_ref: str | int,
        features_json: str,
        session: AsyncSession = Depends(get_session),
    ) -> ActionResponse:
        """Persist computed audio features for a track.

        Use after analyze_track() to save the computed result to DB.
        Creates a new feature extraction run.

        Args:
            track_ref: Track reference (must resolve to exact ID).
            features_json: JSON string with feature values from analyze_track output.
        """
        ref = parse_ref(track_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            raise ToolError(f"save_features requires exact ref: {track_ref}")

        try:
            features_data = json.loads(features_json)
        except json.JSONDecodeError as e:
            raise ToolError(f"Invalid JSON: {e}") from None

        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        features_repo = AudioFeaturesRepository(session)

        # Create ORM instance directly from JSON dict.
        # All NOT NULL model fields must be provided with defaults.
        try:
            await features_repo.create(
                track_id=ref.local_id,
                run_id=features_data.get("run_id", 0),
                # Tempo
                bpm=features_data.get("bpm", 0.0),
                tempo_confidence=features_data.get("tempo_confidence", 0.0),
                bpm_stability=features_data.get("bpm_stability", 0.0),
                is_variable_tempo=features_data.get("is_variable_tempo", False),
                # Loudness
                lufs_i=features_data.get("lufs_i", 0.0),
                lufs_s_mean=features_data.get("lufs_s_mean"),
                lufs_m_max=features_data.get("lufs_m_max"),
                rms_dbfs=features_data.get("rms_dbfs", 0.0),
                true_peak_db=features_data.get("true_peak_db"),
                crest_factor_db=features_data.get("crest_factor_db"),
                lra_lu=features_data.get("lra_lu"),
                # Energy (NOT NULL fields need defaults)
                energy_mean=features_data.get("energy_mean", 0.0),
                energy_max=features_data.get("energy_max", 0.0),
                energy_std=features_data.get("energy_std", 0.0),
                energy_slope_mean=features_data.get("energy_slope_mean"),
                # Band energies
                sub_energy=features_data.get("sub_energy"),
                low_energy=features_data.get("low_energy"),
                lowmid_energy=features_data.get("lowmid_energy"),
                mid_energy=features_data.get("mid_energy"),
                highmid_energy=features_data.get("highmid_energy"),
                high_energy=features_data.get("high_energy"),
                low_high_ratio=features_data.get("low_high_ratio"),
                sub_lowmid_ratio=features_data.get("sub_lowmid_ratio"),
                # Spectral
                centroid_mean_hz=features_data.get("centroid_mean_hz"),
                rolloff_85_hz=features_data.get("rolloff_85_hz"),
                rolloff_95_hz=features_data.get("rolloff_95_hz"),
                flatness_mean=features_data.get("flatness_mean"),
                flux_mean=features_data.get("flux_mean"),
                flux_std=features_data.get("flux_std"),
                slope_db_per_oct=features_data.get("slope_db_per_oct"),
                contrast_mean_db=features_data.get("contrast_mean_db"),
                hnr_mean_db=features_data.get("hnr_mean_db"),
                # Key
                key_code=features_data.get("key_code", 0),
                key_confidence=features_data.get("key_confidence", 0.0),
                is_atonal=features_data.get("is_atonal", False),
                chroma=features_data.get("chroma"),
                chroma_entropy=features_data.get("chroma_entropy"),
                # MFCC
                mfcc_vector=features_data.get("mfcc_vector"),
                # Rhythm / Groove
                hp_ratio=features_data.get("hp_ratio"),
                onset_rate_mean=features_data.get("onset_rate_mean"),
                onset_rate_max=features_data.get("onset_rate_max"),
                pulse_clarity=features_data.get("pulse_clarity"),
                kick_prominence=features_data.get("kick_prominence"),
            )
        except SAIntegrityError:
            await session.rollback()
            run = features_data.get("run_id", 0)
            raise ToolError(
                f"Features already exist for track {ref.local_id} (run_id={run}). "
                "Use a different run_id or delete existing features first."
            ) from None

        return await wrap_action(
            success=True,
            message=f"Saved features for track local:{ref.local_id}",
            session=session,
        )
