"""Export tools for DJ workflow MCP server.

Rekordbox XML export for DJ sets.
"""

from __future__ import annotations

import contextlib
import re
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
    async def export_set_rekordbox(
        set_id: int,
        version_id: int,
        ctx: Context,
        include_cues: bool = True,
        include_loops: bool = True,
        include_beatgrid: bool = True,
        include_mix_points: bool = True,
        include_sections_as_cues: bool = True,
        include_load_point: bool = True,
        base_path: str = "/Music",
        set_svc: DjSetService = Depends(get_set_service),
        track_svc: TrackService = Depends(get_track_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> ExportResult:
        """Export a set version as Rekordbox XML (DJ_PLAYLISTS).

        Produces an XML file compatible with Rekordbox, djay Pro,
        Mixxx, and Traktor (via converter).  Includes:
        - Full COLLECTION with track metadata (BPM, key, artist, album, genre, label)
        - TEMPO elements (beatgrid, variable tempo support)
        - POSITION_MARK: hot cues, memory cues, loops, fade-in/out, load point
        - Auto-generated memory cues from section boundaries (intro/drop/outro)
        - PLAYLISTS tree with set name

        Args:
            set_id: DJ set ID (for validation).
            version_id: Set version to export.
            include_cues: Include hot + memory cue points.
            include_loops: Include saved loops (hot + memory).
            include_beatgrid: Include TEMPO elements from beatgrid.
            include_mix_points: Include Fade-In/Fade-Out markers.
            include_sections_as_cues: Convert detected sections to memory cues.
            include_load_point: Include Load Point marker.
            base_path: Base path prefix for file URIs.
        """
        from urllib.parse import quote

        from app.repositories.dj_beatgrid import DjBeatgridRepository
        from app.repositories.dj_cue_points import DjCuePointRepository
        from app.repositories.dj_saved_loops import DjSavedLoopRepository
        from app.repositories.keys import KeyRepository
        from app.repositories.sections import SectionsRepository
        from app.repositories.tracks import TrackRepository
        from app.services.rekordbox_types import (
            RekordboxCuePoint,
            RekordboxTempo,
            RekordboxTrackData,
        )
        from app.services.set_export import export_rekordbox_xml

        # Section type enum mapping for cue names
        section_names: dict[int, str] = {
            0: "Intro",
            1: "Build",
            2: "Drop",
            3: "Break",
            4: "Outro",
        }

        dj_set = await set_svc.get(set_id)
        items_list = await set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)
        track_ids = [item.track_id for item in items]

        # --- Batch-load all data (no N+1) ---
        artists_map = await track_svc.get_track_artists(track_ids)

        # Repos from session via features_svc (shares same session)
        session = features_svc.features_repo.session
        cue_repo = DjCuePointRepository(session)
        loop_repo = DjSavedLoopRepository(session)
        bg_repo = DjBeatgridRepository(session)
        sec_repo = SectionsRepository(session)
        key_repo = KeyRepository(session)
        track_repo = TrackRepository(session)

        cues_map = await cue_repo.get_by_track_ids(track_ids) if include_cues else {}
        loops_map = await loop_repo.get_by_track_ids(track_ids) if include_loops else {}
        bg_map = await bg_repo.get_canonical_by_track_ids(track_ids) if include_beatgrid else {}
        sections_map = (
            await sec_repo.get_latest_by_track_ids(track_ids) if include_sections_as_cues else {}
        )

        # Batch-load genres, labels, albums
        genres_map = await track_repo.get_genres_for_tracks(track_ids)
        labels_map = await track_repo.get_labels_for_tracks(track_ids)
        albums_map = await track_repo.get_albums_for_tracks(track_ids)

        # Batch-load key names
        key_codes: set[int] = set()
        features_map: dict[int, Any] = {}
        for item in items:
            with contextlib.suppress(NotFoundError):
                feat = await features_svc.get_latest(item.track_id)
                features_map[item.track_id] = feat
                key_codes.add(feat.key_code)
        key_names = await key_repo.get_key_names(list(key_codes)) if key_codes else {}

        # --- Build RekordboxTrackData list ---
        rb_tracks: list[RekordboxTrackData] = []
        for pos, item in enumerate(items, 1):
            title = f"Track {item.track_id}"
            duration_s = 0
            date_added = ""
            with contextlib.suppress(NotFoundError):
                track = await track_svc.get(item.track_id)
                title = track.title
                duration_s = track.duration_ms // 1000
                if hasattr(track, "created_at") and track.created_at:
                    date_added = track.created_at.strftime("%Y-%m-%d")

            artists = artists_map.get(item.track_id, [])
            display = _build_display_name(title, artists)
            safe = _safe_filename(display)
            location = f"file://localhost{base_path}/{quote(f'{pos:03d}. {safe}.mp3')}"

            # Audio features
            track_feat: Any = features_map.get(item.track_id)
            bpm = track_feat.bpm if track_feat else None
            tonality = key_names.get(track_feat.key_code) if track_feat else None

            # Tempos from beatgrid
            tempos: list[RekordboxTempo] = []
            bg = bg_map.get(item.track_id)
            if bg:
                tempos.append(
                    RekordboxTempo(
                        position_s=bg.first_downbeat_ms / 1000.0,
                        bpm=bg.bpm,
                    )
                )

            # Position marks
            marks: list[RekordboxCuePoint] = []

            # Cue points
            for cue in cues_map.get(item.track_id, []):
                is_hot = cue.hotcue_index is not None and cue.hotcue_index >= 0
                r, g, b = 0, 0, 0
                if cue.color_rgb is not None:
                    r = (cue.color_rgb >> 16) & 0xFF
                    g = (cue.color_rgb >> 8) & 0xFF
                    b = cue.color_rgb & 0xFF

                # Map cue_kind to Rekordbox Type
                rb_type = 0  # default: cue
                if cue.cue_kind == 3:  # FADE_IN
                    rb_type = 1
                elif cue.cue_kind == 4:  # FADE_OUT
                    rb_type = 2
                elif cue.cue_kind == 1:  # LOAD
                    rb_type = 3
                elif cue.cue_kind in (5, 6):  # LOOP_IN, LOOP_OUT — skip
                    continue

                hcn = cue.hotcue_index if is_hot and cue.hotcue_index is not None else -1
                marks.append(
                    RekordboxCuePoint(
                        position_s=cue.position_ms / 1000.0,
                        cue_type=rb_type,
                        hotcue_num=hcn,
                        name=cue.label or "",
                        red=r,
                        green=g,
                        blue=b,
                    )
                )

            # Saved loops
            for loop in loops_map.get(item.track_id, []):
                is_hot = loop.hotcue_index is not None and loop.hotcue_index >= 0
                r, g, b = 0, 0, 0
                if loop.color_rgb is not None:
                    r = (loop.color_rgb >> 16) & 0xFF
                    g = (loop.color_rgb >> 8) & 0xFF
                    b = loop.color_rgb & 0xFF
                hcn = loop.hotcue_index if is_hot and loop.hotcue_index is not None else -1
                marks.append(
                    RekordboxCuePoint(
                        position_s=loop.in_ms / 1000.0,
                        cue_type=4,
                        hotcue_num=hcn,
                        end_s=loop.out_ms / 1000.0,
                        name=loop.label or "",
                        red=r,
                        green=g,
                        blue=b,
                    )
                )

            # Mix points (fade-in/out from set items as fallback)
            if include_mix_points:
                has_fadein = any(m.cue_type == 1 for m in marks)
                has_fadeout = any(m.cue_type == 2 for m in marks)
                if not has_fadein and item.mix_in_ms is not None:
                    marks.append(
                        RekordboxCuePoint(
                            position_s=item.mix_in_ms / 1000.0,
                            cue_type=1,
                            hotcue_num=-1,
                            end_s=item.mix_in_ms / 1000.0 + 16,
                        )
                    )
                if not has_fadeout and item.mix_out_ms is not None:
                    marks.append(
                        RekordboxCuePoint(
                            position_s=item.mix_out_ms / 1000.0,
                            cue_type=2,
                            hotcue_num=-1,
                            end_s=float(duration_s),
                        )
                    )

            # Section boundaries → memory cues
            if include_sections_as_cues:
                seen_types: set[int] = set()
                for section in sections_map.get(item.track_id, []):
                    if section.section_type in seen_types:
                        continue
                    name = section_names.get(section.section_type)
                    if name:
                        seen_types.add(section.section_type)
                        marks.append(
                            RekordboxCuePoint(
                                position_s=section.start_ms / 1000.0,
                                cue_type=0,
                                hotcue_num=-1,
                                name=name,
                            )
                        )

            # Load point (first downbeat or position 0)
            if include_load_point:
                has_load = any(m.cue_type == 3 for m in marks)
                if not has_load:
                    load_pos = bg.first_downbeat_ms / 1000.0 if bg else 0.0
                    marks.append(
                        RekordboxCuePoint(
                            position_s=load_pos,
                            cue_type=3,
                            hotcue_num=-1,
                        )
                    )

            rb_tracks.append(
                RekordboxTrackData(
                    track_id=item.track_id,
                    name=title,
                    artist=", ".join(artists),
                    duration_s=duration_s,
                    location=location,
                    bpm=bpm,
                    tonality=tonality,
                    genre=next(iter(genres_map.get(item.track_id, [])), ""),
                    label=next(iter(labels_map.get(item.track_id, [])), ""),
                    album=next(iter(albums_map.get(item.track_id, [])), ""),
                    date_added=date_added,
                    comments=item.notes or "",
                    tempos=tempos,
                    position_marks=marks,
                )
            )

        xml_content = export_rekordbox_xml(rb_tracks, set_name=dj_set.name)

        return ExportResult(
            set_id=set_id,
            format="rekordbox_xml",
            track_count=len(items),
            content=xml_content,
        )
