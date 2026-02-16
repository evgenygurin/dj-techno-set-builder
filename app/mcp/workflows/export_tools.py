"""Export tools for DJ workflow MCP server."""

from __future__ import annotations

import contextlib
import json
import re

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
    ) -> ExportResult:
        """Export a set version as an M3U playlist for djay Pro.

        Builds an extended M3U (#EXTM3U) with numbered filenames
        in the format ``{NNN}. {Artists} - {Title}.mp3``.

        Args:
            set_id: DJ set ID (for validation).
            version_id: Set version to export.
        """
        await set_svc.get(set_id)  # validate set exists
        items_list = await set_svc.list_items(
            version_id,
            offset=0,
            limit=500,
        )
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        # Batch-load artist names (single query instead of N+1)
        track_ids = [item.track_id for item in items]
        artists_map = await track_svc.get_track_artists(track_ids)

        lines: list[str] = ["#EXTM3U"]
        for pos, item in enumerate(items, 1):
            duration_s = -1
            title = f"Track {item.track_id}"
            with contextlib.suppress(NotFoundError):
                track = await track_svc.get(item.track_id)
                title = track.title
                duration_s = track.duration_ms // 1000

            artists = artists_map.get(item.track_id, [])
            display = _build_display_name(title, artists)

            lines.append(f"#EXTINF:{duration_s},{display}")
            lines.append(f"{pos:03d}. {_safe_filename(display)}.mp3")

        m3u_content = "\n".join(lines) + "\n"

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
        energy curve, and numbered filenames for djay Pro.

        Args:
            set_id: DJ set ID.
            version_id: Set version to export.
        """
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

        tracks_data: list[dict[str, object]] = []
        energy_curve: list[float] = []

        for pos, item in enumerate(items, 1):
            track_entry: dict[str, object] = {
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

            tracks_data.append(track_entry)

        export_doc = {
            "set_id": set_id,
            "set_name": dj_set.name,
            "version_id": version_id,
            "track_count": len(items),
            "tracks": tracks_data,
            "energy_curve": energy_curve,
        }

        json_content = json.dumps(export_doc, indent=2, ensure_ascii=False)

        return ExportResult(
            set_id=set_id,
            format="json",
            track_count=len(items),
            content=json_content,
        )
