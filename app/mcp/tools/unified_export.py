"""Unified export_set tool — single entrypoint for all export formats.

Merges export_set_m3u, export_set_json, export_set_rekordbox into one tool.
Delegates to the existing format-specific implementations in export_tools.py.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.dependencies import get_session
from app.mcp.refs import RefType, parse_ref


def register_unified_export_tools(mcp: FastMCP) -> None:
    """Register the unified export_set tool on the MCP server."""

    @mcp.tool(tags={"export"}, annotations={"readOnlyHint": True})
    async def export_set(
        set_ref: str,
        version_id: int,
        format: str = "json",
        base_path: str = "/Music",
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Export a DJ set version in the requested format.

        Unified export: one tool for all formats (m3u, json, rekordbox).

        Args:
            set_ref: Set reference (local:3 or 3).
            version_id: Set version to export.
            format: Export format — "m3u", "json", or "rekordbox".
            base_path: Base path for file URIs (rekordbox only).
        """
        ref = parse_ref(set_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "export requires exact ref", "ref": set_ref})

        set_id = ref.local_id

        # Import services
        from app.mcp.dependencies import get_features_service, get_set_service, get_track_service

        set_svc = get_set_service(session)
        track_svc = get_track_service(session)
        features_svc = get_features_service(session)

        try:
            dj_set = await set_svc.get(set_id)
        except Exception:
            return json.dumps({"error": "Set not found", "ref": set_ref})

        items_list = await set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        if format == "m3u":
            content = await _export_m3u(dj_set, items, set_svc, track_svc, features_svc)
        elif format == "json":
            content = await _export_json(dj_set, items, set_svc, track_svc, features_svc)
        elif format == "rekordbox":
            content = await _export_rekordbox(
                dj_set, items, track_svc, features_svc, base_path, session
            )
        else:
            return json.dumps(
                {
                    "error": f"Unknown format: {format}",
                    "supported": ["m3u", "json", "rekordbox"],
                }
            )

        result = {
            "set_id": set_id,
            "format": format,
            "track_count": len(items),
            "content": content,
        }
        return json.dumps(result, ensure_ascii=False)


async def _export_m3u(dj_set, items, set_svc, track_svc, features_svc) -> str:  # type: ignore[no-untyped-def]
    """Generate M3U8 content."""
    import contextlib
    import re
    from typing import Any

    from app.errors import NotFoundError
    from app.services.set_export import export_m3u
    from app.utils.audio.camelot import key_code_to_camelot

    bad_re = re.compile(r'[<>:"/\\|?*]')

    track_ids = [item.track_id for item in items]
    artists_map = await track_svc.get_track_artists(track_ids)

    tracks_data: list[dict[str, Any]] = []
    for pos, item in enumerate(items, 1):
        duration_s = 0
        title = f"Track {item.track_id}"
        with contextlib.suppress(NotFoundError):
            track = await track_svc.get(item.track_id)
            title = track.title
            duration_s = track.duration_ms // 1000

        artists = artists_map.get(item.track_id, [])
        display = f"{', '.join(artists)} - {title}" if artists else title
        safe = bad_re.sub("_", display).strip(". ")

        entry: dict[str, Any] = {
            "title": display,
            "duration_s": duration_s,
            "path": f"{pos:03d}. {safe}.mp3",
            "artists": ", ".join(artists) if artists else "",
        }

        try:
            feat = await features_svc.get_latest(item.track_id)
            entry["bpm"] = feat.bpm
            entry["energy"] = feat.lufs_i
            with contextlib.suppress(ValueError):
                entry["key"] = key_code_to_camelot(feat.key_code)
        except NotFoundError:
            pass

        if item.mix_in_ms is not None:
            entry["mix_in_s"] = item.mix_in_ms / 1000.0
        if item.mix_out_ms is not None:
            entry["mix_out_s"] = item.mix_out_ms / 1000.0
        if item.planned_eq:
            entry["planned_eq"] = item.planned_eq
        if item.notes:
            entry["notes"] = item.notes

        tracks_data.append(entry)

    return export_m3u(tracks_data, set_name=dj_set.name)


async def _export_json(dj_set, items, set_svc, track_svc, features_svc) -> str:  # type: ignore[no-untyped-def]
    """Generate JSON guide content."""
    import contextlib
    import json as json_mod
    from typing import Any

    from app.errors import NotFoundError
    from app.services.set_export import export_json_guide
    from app.utils.audio.camelot import key_code_to_camelot

    track_ids = [item.track_id for item in items]
    artists_map = await track_svc.get_track_artists(track_ids)

    tracks_data: list[dict[str, Any]] = []
    energy_curve: list[float] = []

    for pos, item in enumerate(items, 1):
        entry: dict[str, Any] = {"position": pos, "track_id": item.track_id}
        title = f"Track {item.track_id}"
        with contextlib.suppress(NotFoundError):
            track = await track_svc.get(item.track_id)
            title = track.title
            entry["title"] = title
            entry["duration_s"] = track.duration_ms // 1000

        artists = artists_map.get(item.track_id, [])
        entry["artists"] = ", ".join(artists) if artists else ""

        try:
            feat = await features_svc.get_latest(item.track_id)
            entry["bpm"] = feat.bpm
            entry["energy_lufs"] = feat.lufs_i
            with contextlib.suppress(ValueError):
                entry["key"] = key_code_to_camelot(feat.key_code)
            energy_curve.append(feat.lufs_i)
        except NotFoundError:
            pass

        tracks_data.append(entry)

    guide = export_json_guide(
        set_name=dj_set.name,
        energy_arc="classic",
        quality_score=0.0,
        tracks=tracks_data,
        transitions=[],
    )

    guide_data = json_mod.loads(guide)
    guide_data["energy_curve"] = energy_curve
    return json_mod.dumps(guide_data, indent=2, ensure_ascii=False)


async def _export_rekordbox(dj_set, items, track_svc, features_svc, base_path, session) -> str:  # type: ignore[no-untyped-def]
    """Generate Rekordbox XML content."""
    import contextlib
    import re
    from urllib.parse import quote

    from app.errors import NotFoundError
    from app.services.rekordbox_types import RekordboxTrackData
    from app.services.set_export import export_rekordbox_xml
    from app.utils.audio.camelot import key_code_to_camelot

    bad_re = re.compile(r'[<>:"/\\|?*]')

    track_ids = [item.track_id for item in items]
    artists_map = await track_svc.get_track_artists(track_ids)

    rb_tracks: list[RekordboxTrackData] = []
    for pos, item in enumerate(items, 1):
        title = f"Track {item.track_id}"
        duration_s = 0
        with contextlib.suppress(NotFoundError):
            track = await track_svc.get(item.track_id)
            title = track.title
            duration_s = track.duration_ms // 1000

        artists = artists_map.get(item.track_id, [])
        display = f"{', '.join(artists)} - {title}" if artists else title
        safe = bad_re.sub("_", display).strip(". ")
        location = f"file://localhost{base_path}/{quote(f'{pos:03d}. {safe}.mp3')}"

        bpm: float | None = None
        tonality: str | None = None
        try:
            feat = await features_svc.get_latest(item.track_id)
            bpm = feat.bpm
            with contextlib.suppress(ValueError):
                tonality = key_code_to_camelot(feat.key_code)
        except NotFoundError:
            pass

        rb_tracks.append(
            RekordboxTrackData(
                track_id=item.track_id,
                name=title,
                artist=", ".join(artists),
                duration_s=duration_s,
                location=location,
                bpm=bpm,
                tonality=tonality,
            )
        )

    return export_rekordbox_xml(rb_tracks, set_name=dj_set.name)
