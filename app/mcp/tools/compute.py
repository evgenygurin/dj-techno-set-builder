"""Compute-only tools — return data without DB writes.

Agent decides when to persist results using save_features / create_set.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError, ValidationError
from app.mcp.dependencies import get_session
from app.mcp.refs import RefType, parse_ref
from app.utils.audio._errors import AudioAnalysisError, AudioValidationError


def register_compute_tools(mcp: FastMCP) -> None:
    """Register compute-only tools on the MCP server."""

    @mcp.tool(tags={"compute", "analysis"}, timeout=300)
    async def analyze_track(
        track_ref: str | None = None,
        audio_path: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Run full audio analysis pipeline on a track. Returns features WITHOUT saving.

        Accepts either track_ref (resolves to local file) or direct audio_path.
        To persist results, call save_features() with the returned data.

        Requires audio dependencies (essentia, soundfile, scipy).

        Args:
            track_ref: Track reference to analyze (resolves to local file via DjLibraryItem).
            audio_path: Direct path to audio file (alternative to track_ref).
        """
        file_path: str | None = audio_path

        if track_ref and not file_path:
            ref = parse_ref(track_ref)
            if ref.ref_type != RefType.LOCAL or ref.local_id is None:
                return json.dumps({"error": "analyze requires local track ref or audio_path"})

            # Look up file path from DjLibraryItem
            from sqlalchemy import select

            from app.models.dj import DjLibraryItem

            stmt = select(DjLibraryItem).where(DjLibraryItem.track_id == ref.local_id)
            result = await session.execute(stmt)
            lib_item = result.scalar_one_or_none()
            if lib_item is None:
                return json.dumps(
                    {
                        "error": "No local file found for track",
                        "ref": track_ref,
                        "hint": "Download the track first using download_tracks",
                    }
                )
            file_path = lib_item.file_path

        if not file_path:
            return json.dumps({"error": "Provide track_ref or audio_path"})

        # Run analysis pipeline (imports are heavy — lazy load)
        try:
            from app.utils.audio.pipeline import extract_all_features

            features = extract_all_features(file_path)

            # Convert dataclass to dict (numpy arrays need special handling)
            features_dict = {
                "bpm": features.bpm.bpm,
                "bpm_confidence": features.bpm.confidence,
                "key": features.key.key,
                "scale": features.key.scale,
                "key_code": features.key.key_code,
                "key_confidence": features.key.confidence,
                "lufs_i": features.loudness.lufs_i,
                "lufs_s_mean": features.loudness.lufs_s_mean,
                "energy_sub": features.band_energy.sub,
                "energy_low": features.band_energy.low,
                "energy_mid": features.band_energy.mid,
                "energy_high": features.band_energy.high,
                "spectral_centroid": features.spectral.centroid_mean_hz,
                "spectral_rolloff": features.spectral.rolloff_85_hz,
            }

            # Return computed features as JSON (agent calls save_features to persist)
            return json.dumps(
                {
                    "track_ref": track_ref,
                    "audio_path": file_path,
                    "features": features_dict,
                    "hint": "Call save_features(track_ref, features_json) to persist",
                },
                ensure_ascii=False,
            )

        except ImportError as e:
            return json.dumps(
                {
                    "error": f"Audio dependencies not available: {e}",
                    "hint": "Install with: uv sync --extra audio",
                }
            )
        except (
            AudioAnalysisError,
            AudioValidationError,
            NotFoundError,
            ValueError,
            OSError,
        ) as e:
            return json.dumps({"error": f"Analysis failed: {e}"})

    @mcp.tool(tags={"compute", "setbuilder"}, timeout=120)
    async def compute_set_order(
        playlist_id: int,
        template: str | None = None,
        energy_arc: str = "classic",
        exclude_track_ids: list[int] | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Compute optimal track ordering WITHOUT saving to DB.

        Runs GA optimization on tracks from a playlist. Returns the
        ordered track list + scores. Agent then calls create_set(...)
        with the returned track_ids to persist.

        Args:
            playlist_id: Source playlist with candidate tracks.
            template: Template name (classic_60, peak_hour_60, etc.) or None.
            energy_arc: Energy arc shape — classic, progressive, roller, wave.
            exclude_track_ids: Track IDs to exclude from selection.
        """
        from app.mcp.dependencies import get_set_generation_service
        from app.repositories.sets import (
            DjSetItemRepository,
            DjSetRepository,
            DjSetVersionRepository,
        )
        from app.schemas.set_generation import SetGenerationRequest
        from app.schemas.sets import DjSetCreate
        from app.services.sets import DjSetService

        try:
            # We need to create a temp set (GA needs a set_id) — will delete after
            set_repo = DjSetRepository(session)
            version_repo = DjSetVersionRepository(session)
            item_repo = DjSetItemRepository(session)
            set_svc = DjSetService(set_repo, version_repo, item_repo)

            temp_set = await set_svc.create(DjSetCreate(name="__temp_compute__"))

            gen_svc = get_set_generation_service(session)
            request = SetGenerationRequest(
                energy_arc_type=energy_arc,
                playlist_id=playlist_id,
                template_name=template,
                exclude_track_ids=exclude_track_ids,
            )
            gen_result = await gen_svc.generate(temp_set.set_id, request)

            avg_score = 0.0
            if gen_result.transition_scores:
                avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

            result = {
                "track_ids": gen_result.track_ids,
                "track_count": len(gen_result.track_ids),
                "total_score": gen_result.score,
                "avg_transition_score": round(avg_score, 3),
                "transition_scores": [round(s, 3) for s in gen_result.transition_scores],
                "energy_arc_score": gen_result.energy_arc_score,
                "bpm_smoothness_score": gen_result.bpm_smoothness_score,
                "hint": (
                    "Call create_set(name=..., track_ids=[...]) to persist. "
                    "The temporary set has been cleaned up."
                ),
            }

            # Cleanup temp set
            await set_svc.delete(temp_set.set_id)

            return json.dumps(result, ensure_ascii=False)

        except (NotFoundError, ValidationError, ValueError) as e:
            return json.dumps({"error": f"Set computation failed: {e}"})
