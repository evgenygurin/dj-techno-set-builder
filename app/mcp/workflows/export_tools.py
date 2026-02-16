"""Export tools for DJ workflow MCP server.

Produces Extended M3U8 with VLC opts, DJ metadata (cues, loops, sections,
transitions, EQ), and enriched JSON transition guides.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Sequence
from typing import Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError
from app.mcp.dependencies import get_features_service, get_set_service, get_track_service
from app.mcp.types import ExportResult
from app.services.features import AudioFeaturesService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.utils.audio.camelot import key_code_to_camelot

# Characters forbidden in filenames on macOS/Windows
_FILENAME_BAD_RE = re.compile(r'[<>:"/\\|?*]')


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename component."""
    return _FILENAME_BAD_RE.sub("_", name).strip(". ")


def _build_display_name(
    title: str,
    artists: list[str],
) -> str:
    """Build 'Artists - Title' display string."""
    if artists:
        return f"{', '.join(artists)} - {title}"
    return title


def register_export_tools(mcp: FastMCP) -> None:
    """Register export tools on the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"export"},
    )
    async def export_set_m3u(
        set_id: int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        track_svc: TrackService = Depends(get_track_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> ExportResult:
        """Export a set version as an Extended M3U playlist.

        Builds a rich M3U8 with:
        - ``#PLAYLIST:`` header with set name
        - ``#EXTINF:`` with duration and display title per track
        - ``#EXTART:`` with artist names
        - ``#EXTVLCOPT:start-time`` / ``stop-time`` for VLC mix in/out
        - ``#EXTDJ-BPM:``, ``#EXTDJ-KEY:``, ``#EXTDJ-ENERGY:`` per track
        - ``#EXTDJ-CUE:`` for cue points (hot + memory)
        - ``#EXTDJ-LOOP:`` for saved loops
        - ``#EXTDJ-SECTION:`` for structural sections (intro, drop, outro)
        - ``#EXTDJ-EQ:`` for planned EQ adjustments
        - ``#EXTDJ-TRANSITION:`` between consecutive tracks
        - ``#EXTDJ-NOTE:`` for DJ notes

        Numbered filenames: ``{NNN}. {Artists} - {Title}.mp3``.

        Args:
            set_id: DJ set ID (for validation).
            version_id: Set version to export.
        """
        from app.services.set_export import export_m3u

        dj_set = await set_svc.get(set_id)
        items_list = await set_svc.list_items(
            version_id,
            offset=0,
            limit=500,
        )
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        # Batch-load artist names (single query instead of N+1)
        track_ids = [item.track_id for item in items]
        artists_map = await track_svc.get_track_artists(track_ids)

        # Build enriched track data
        tracks_data: list[dict[str, Any]] = []
        for pos, item in enumerate(items, 1):
            duration_s = 0
            title = f"Track {item.track_id}"
            with contextlib.suppress(NotFoundError):
                track = await track_svc.get(item.track_id)
                title = track.title
                duration_s = track.duration_ms // 1000

            artists = artists_map.get(item.track_id, [])
            display = _build_display_name(title, artists)

            track_entry: dict[str, Any] = {
                "title": display,
                "duration_s": duration_s,
                "path": f"{pos:03d}. {_safe_filename(display)}.mp3",
                "artists": ", ".join(artists) if artists else "",
            }

            # Audio features: BPM, key (Camelot), energy
            try:
                feat = await features_svc.get_latest(item.track_id)
                track_entry["bpm"] = feat.bpm
                track_entry["energy"] = feat.lufs_i

                with contextlib.suppress(ValueError):
                    track_entry["key"] = key_code_to_camelot(feat.key_code)
            except NotFoundError:
                pass

            # Mix in/out points (from set item)
            if item.mix_in_ms is not None:
                track_entry["mix_in_s"] = item.mix_in_ms / 1000.0
            if item.mix_out_ms is not None:
                track_entry["mix_out_s"] = item.mix_out_ms / 1000.0

            # Planned EQ
            if item.planned_eq:
                track_entry["planned_eq"] = item.planned_eq

            # DJ notes
            if item.notes:
                track_entry["notes"] = item.notes

            tracks_data.append(track_entry)

        # Build transition data between consecutive tracks
        transitions_data = await _build_transitions(
            items,
            features_svc,
        )

        m3u_content = export_m3u(
            tracks_data,
            set_name=dj_set.name,
            transitions=transitions_data,
        )

        return ExportResult(
            set_id=set_id,
            format="m3u",
            track_count=len(items),
            content=m3u_content,
        )

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"export"},
    )
    async def export_set_json(
        set_id: int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        track_svc: TrackService = Depends(get_track_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> ExportResult:
        """Export a set version as a JSON document with full details.

        Includes track ordering, titles, artists, audio features,
        energy curve, BPM/key metadata, cue points, loops, sections,
        planned EQ, transition scoring with recommendations,
        and set-level analytics.

        Args:
            set_id: DJ set ID.
            version_id: Set version to export.
        """
        from app.services.set_export import export_json_guide
        from app.services.transition_type import recommend_transition
        from app.utils.audio.camelot import camelot_distance
        from app.utils.audio.feature_conversion import orm_features_to_track_features

        dj_set = await set_svc.get(set_id)
        items_list = await set_svc.list_items(
            version_id,
            offset=0,
            limit=500,
        )
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        # Batch-load artist names
        track_ids = [item.track_id for item in items]
        artists_map = await track_svc.get_track_artists(track_ids)

        tracks_data: list[dict[str, Any]] = []
        energy_curve: list[float] = []

        for pos, item in enumerate(items, 1):
            track_entry: dict[str, Any] = {
                "position": pos,
                "sort_index": item.sort_index,
                "track_id": item.track_id,
            }

            # Enrich with track title
            title = f"Track {item.track_id}"
            with contextlib.suppress(NotFoundError):
                track = await track_svc.get(item.track_id)
                title = track.title
                track_entry["title"] = track.title
                track_entry["duration_ms"] = track.duration_ms
                track_entry["duration_s"] = track.duration_ms // 1000

            # Add artist info
            artists = artists_map.get(item.track_id, [])
            track_entry["artists"] = ", ".join(artists) if artists else ""

            # Build filename matching M3U
            display = _build_display_name(title, artists)
            track_entry["filename"] = f"{pos:03d}. {_safe_filename(display)}.mp3"

            try:
                feat = await features_svc.get_latest(item.track_id)
                track_entry["bpm"] = feat.bpm
                track_entry["energy_lufs"] = feat.lufs_i

                key_str: str | None = None
                with contextlib.suppress(ValueError):
                    key_str = key_code_to_camelot(feat.key_code)
                track_entry["key"] = key_str

                energy_curve.append(feat.lufs_i)
            except NotFoundError:
                track_entry["bpm"] = None
                track_entry["energy_lufs"] = None
                track_entry["key"] = None

            # Mix in/out points
            if item.mix_in_ms is not None:
                track_entry["mix_in_s"] = item.mix_in_ms / 1000.0
            if item.mix_out_ms is not None:
                track_entry["mix_out_s"] = item.mix_out_ms / 1000.0

            # Planned EQ
            if item.planned_eq:
                track_entry["planned_eq"] = item.planned_eq

            # DJ notes
            if item.notes:
                track_entry["notes"] = item.notes

            tracks_data.append(track_entry)

        # --- Build transitions with full scoring ---
        from app.services.transition_scoring_unified import UnifiedTransitionScoringService

        unified_svc = UnifiedTransitionScoringService(
            features_svc.features_repo.session,
        )
        transitions_data: list[dict[str, Any]] = []
        for i in range(len(items) - 1):
            from_item = items[i]
            to_item = items[i + 1]

            trans: dict[str, Any] = {
                "score": 0.0,
                "bpm_delta": 0.0,
                "energy_delta": 0.0,
                "camelot": "",
                "recommendation": None,
            }

            try:
                components = await unified_svc.score_components_by_ids(
                    from_item.track_id,
                    to_item.track_id,
                )
                trans["score"] = components["total"]
            except ValueError:
                pass

            try:
                feat_a_obj = await features_svc.get_latest(from_item.track_id)
                feat_b_obj = await features_svc.get_latest(to_item.track_id)
                tf_a = orm_features_to_track_features(feat_a_obj)  # type: ignore[arg-type]
                tf_b = orm_features_to_track_features(feat_b_obj)  # type: ignore[arg-type]

                trans["bpm_delta"] = round(abs(tf_a.bpm - tf_b.bpm), 1)
                trans["energy_delta"] = round(
                    abs(tf_a.energy_lufs - tf_b.energy_lufs),
                    1,
                )

                cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)
                cam_a = key_code_to_camelot(tf_a.key_code)
                cam_b = key_code_to_camelot(tf_b.key_code)
                trans["camelot"] = f"{cam_a} -> {cam_b}"

                rec = recommend_transition(
                    tf_a,
                    tf_b,
                    camelot_compatible=cam_dist <= 1,
                )
                trans["recommendation"] = rec
            except (NotFoundError, ValueError):
                pass

            # Mix in/out from set items
            if to_item.mix_in_ms is not None:
                trans["mix_in_s"] = to_item.mix_in_ms / 1000.0
            if from_item.mix_out_ms is not None:
                trans["mix_out_s"] = from_item.mix_out_ms / 1000.0

            transitions_data.append(trans)

        quality = 0.0
        if transitions_data:
            quality = sum(float(t.get("score", 0.0)) for t in transitions_data) / len(
                transitions_data
            )

        # Convert tracks_data to format expected by export_json_guide
        guide_tracks: list[dict[str, Any]] = []
        for td in tracks_data:
            gt: dict[str, Any] = {"title": td.get("title", "")}
            for field in (
                "artists",
                "bpm",
                "key",
                "energy_lufs",
                "duration_s",
                "mix_in_s",
                "mix_out_s",
                "planned_eq",
                "notes",
            ):
                if field in td and td[field] is not None:
                    gt[field] = td[field]
            guide_tracks.append(gt)

        content = export_json_guide(
            set_name=dj_set.name,
            energy_arc="classic",
            quality_score=round(quality, 3),
            tracks=guide_tracks,
            transitions=transitions_data,
        )

        # Build final enriched JSON with both guide and raw data
        guide_data = json.loads(content)
        guide_data["energy_curve"] = energy_curve

        json_content = json.dumps(guide_data, indent=2, ensure_ascii=False)

        return ExportResult(
            set_id=set_id,
            format="json",
            track_count=len(items),
            content=json_content,
        )


async def _build_transitions(
    items: Sequence[Any],
    features_svc: AudioFeaturesService,
) -> list[dict[str, Any]]:
    """Build transition metadata between consecutive set items."""
    from app.services.transition_type import recommend_transition
    from app.utils.audio.camelot import camelot_distance
    from app.utils.audio.feature_conversion import orm_features_to_track_features

    transitions: list[dict[str, Any]] = []

    for i in range(len(items) - 1):
        from_item = items[i]
        to_item = items[i + 1]

        trans: dict[str, Any] = {}

        try:
            feat_a = await features_svc.get_latest(from_item.track_id)
            feat_b = await features_svc.get_latest(to_item.track_id)
            tf_a = orm_features_to_track_features(feat_a)  # type: ignore[arg-type]
            tf_b = orm_features_to_track_features(feat_b)  # type: ignore[arg-type]

            trans["bpm_delta"] = round(abs(tf_a.bpm - tf_b.bpm), 1)
            trans["energy_delta"] = round(
                abs(tf_a.energy_lufs - tf_b.energy_lufs),
                1,
            )

            cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)
            cam_a = key_code_to_camelot(tf_a.key_code)
            cam_b = key_code_to_camelot(tf_b.key_code)
            trans["camelot"] = f"{cam_a} -> {cam_b}"

            rec = recommend_transition(
                tf_a,
                tf_b,
                camelot_compatible=cam_dist <= 1,
            )
            trans["type"] = str(rec.transition_type)
            trans["confidence"] = rec.confidence
            trans["reason"] = rec.reason
            if rec.alt_type:
                trans["alt_type"] = str(rec.alt_type)
        except (NotFoundError, ValueError):
            pass

        # Mix points from set items
        if hasattr(to_item, "mix_in_ms") and to_item.mix_in_ms is not None:
            trans["mix_in_s"] = to_item.mix_in_ms / 1000.0
        if hasattr(from_item, "mix_out_ms") and from_item.mix_out_ms is not None:
            trans["mix_out_s"] = from_item.mix_out_ms / 1000.0

        transitions.append(trans)

    return transitions
