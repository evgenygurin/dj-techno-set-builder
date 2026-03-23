"""DJ set delivery service — scoring, file export, YM sync.

Extracted from app/mcp/tools/delivery.py to separate business logic
from MCP adapter concerns.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import NotFoundError
from app.mcp.tools._scoring_helpers import score_consecutive_transitions
from app.services.base import BaseService
from app.services.features import AudioFeaturesService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.services.transition_types import TransitionScoreResult, TransitionSummary
from app.services.yandex_music_client import YandexMusicClient
from app.utils.audio.camelot import key_code_to_camelot
from app.utils.text_sort import sanitize_filename

logger = logging.getLogger(__name__)

_WEAK_THRESHOLD = 0.85


def _safe_name(name: str) -> str:
    s = sanitize_filename(name).strip(". ")
    return s.lower().replace(" ", "_")


def output_dir(set_name: str) -> Path:
    """Resolve output directory from settings.dj_library_path."""
    library = Path(settings.dj_library_path).expanduser()
    base = library.parent / "generated-sets"
    return base / _safe_name(set_name)


def _is_icloud_stub(path: Path) -> bool:
    try:
        st = path.stat()
        return hasattr(st, "st_blocks") and st.st_blocks * 512 < st.st_size * 0.9
    except OSError:
        return True


def _score_bar(score: float) -> str:
    if score <= 0:
        return "XXXXX"
    filled = round(score * 5)
    return "#" * filled + "." * (5 - filled)


def _energy_bar(lufs: float, lo: float, hi: float) -> str:
    if hi == lo:
        return "=" * 10
    ratio = (lufs - lo) / (hi - lo)
    filled = max(0, min(10, round(ratio * 10)))
    return "=" * filled + "-" * (10 - filled)


class DeliveryService(BaseService):
    """Orchestrates set delivery: score → export files → optional YM sync."""

    def __init__(
        self,
        set_svc: DjSetService,
        unified_svc: UnifiedTransitionScoringService,
        features_svc: AudioFeaturesService,
        track_svc: TrackService,
        session: AsyncSession,
        ym_client: YandexMusicClient | None = None,
    ) -> None:
        super().__init__()
        self.set_svc = set_svc
        self.unified_svc = unified_svc
        self.features_svc = features_svc
        self.track_svc = track_svc
        self.session = session
        self.ym_client = ym_client

    async def score_version(
        self,
        version_id: int,
    ) -> list[TransitionScoreResult]:
        """Score all transitions in a set version."""
        items_list = await self.set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)
        return await score_consecutive_transitions(
            items, self.unified_svc, self.track_svc, self.features_svc
        )

    @staticmethod
    def build_transition_summary(
        scores: list[TransitionScoreResult],
    ) -> TransitionSummary:
        scored = [s for s in scores if s.total > 0.0]
        return TransitionSummary(
            total=len(scores),
            hard_conflicts=sum(1 for s in scores if s.total == 0.0),
            weak=sum(1 for s in scored if s.total < _WEAK_THRESHOLD),
            avg_score=(sum(s.total for s in scored) / len(scored) if scored else 0.0),
            min_score=min((s.total for s in scored), default=0.0),
        )

    async def collect_track_data(
        self,
        items: list[Any],
    ) -> list[dict[str, Any]]:
        """Collect per-track metadata + audio features for export."""
        track_ids = [item.track_id for item in items]
        artists_map = await self.track_svc.get_track_artists(track_ids)

        # Batch-load file paths from dj_library_items
        from app.models.dj import DjLibraryItem

        file_path_map: dict[int, str] = {}
        stmt = select(DjLibraryItem.track_id, DjLibraryItem.file_path).where(
            DjLibraryItem.track_id.in_(track_ids),
            DjLibraryItem.file_path.is_not(None),
        )
        rows = await self.session.execute(stmt)
        file_path_map = {r[0]: r[1] for r in rows if r[1]}

        tracks: list[dict[str, Any]] = []
        for pos, item in enumerate(items, 1):
            entry: dict[str, Any] = {"position": pos, "track_id": item.track_id}
            with contextlib.suppress(NotFoundError):
                track = await self.track_svc.get(item.track_id)
                entry["title"] = track.title
                entry["duration_s"] = track.duration_ms // 1000

            artists = artists_map.get(item.track_id, [])
            entry["artists"] = ", ".join(artists) if artists else ""

            with contextlib.suppress(Exception):
                feat = await self.features_svc.get_latest(item.track_id)
                entry["bpm"] = feat.bpm
                entry["lufs"] = feat.lufs_i
                with contextlib.suppress(ValueError):
                    entry["key"] = key_code_to_camelot(feat.key_code)

            if item.track_id in file_path_map:
                entry["file_path"] = file_path_map[item.track_id]

            tracks.append(entry)

        return tracks

    @staticmethod
    def copy_mp3_files(
        tracks: list[dict[str, Any]],
        out: Path,
    ) -> tuple[int, int]:
        """Copy MP3 files from library to output dir. Returns (copied, skipped)."""
        copied = skipped = 0
        for tr in tracks:
            src_str = tr.get("file_path")
            if not src_str:
                skipped += 1
                continue
            src = Path(src_str)
            if not src.exists() or _is_icloud_stub(src):
                skipped += 1
                continue
            title = tr.get("title", f"Track {tr['track_id']}")
            artists = tr.get("artists", "")
            display = f"{artists} - {title}" if artists else title
            safe = sanitize_filename(display).strip(". ")
            dest = out / f"{tr['position']:03d}. {safe}.mp3"
            shutil.copy2(src, dest)
            copied += 1
        return copied, skipped

    @staticmethod
    def set_local_paths(tracks: list[dict[str, Any]]) -> None:
        """Set local 'path' and 'energy' keys for M3U export."""
        for tr in tracks:
            title = tr.get("title", f"Track {tr['track_id']}")
            artists = tr.get("artists", "")
            display = f"{artists} - {title}" if artists else title
            safe = sanitize_filename(display).strip(". ")
            tr["path"] = f"{tr['position']:03d}. {safe}.mp3"
            if "lufs" in tr and "energy" not in tr:
                tr["energy"] = tr["lufs"]

    @staticmethod
    def generate_cheat_sheet(
        set_name: str,
        tracks: list[dict[str, Any]],
        scores: list[TransitionScoreResult],
    ) -> str:
        """Generate a compact infographic cheat sheet for the DJ booth."""
        tx_by_from: dict[int, TransitionScoreResult] = {s.from_track_id: s for s in scores}

        bpms = [tr["bpm"] for tr in tracks if tr.get("bpm")]
        bpm_min = min(bpms) if bpms else 0
        bpm_max = max(bpms) if bpms else 0
        lufs_vals = [tr["lufs"] for tr in tracks if tr.get("lufs")]
        lufs_lo = min(lufs_vals) if lufs_vals else -12
        lufs_hi = max(lufs_vals) if lufs_vals else -5
        total_s = sum(tr.get("duration_s") or 0 for tr in tracks)
        avg_sc = [s.total for s in scores if s.total > 0]
        avg_score = sum(avg_sc) / len(avg_sc) if avg_sc else 0

        lines = [
            f"{set_name}",
            f"{len(tracks)} tracks  {total_s // 3600}h"
            f"{(total_s % 3600) // 60:02d}m"
            f"  BPM {bpm_min:.0f}-{bpm_max:.0f}"
            f"  avg {avg_score:.2f} [{_score_bar(avg_score)}]",
            "",
            "  #  TRACK                       BPM  KEY  ENERGY",
        ]

        for tr in tracks:
            pos = tr["position"]
            title = tr.get("title", "?")[:27]
            bpm = tr.get("bpm") or 0
            key = tr.get("key") or "?"
            lufs = tr.get("lufs") or 0
            ebar = _energy_bar(lufs, lufs_lo, lufs_hi)
            lines.append(f" {pos:2d}  {title:<27s} {bpm:5.0f}  {key:>3s}  [{ebar}] {lufs:.0f}")

            tx = tx_by_from.get(tr["track_id"])
            if tx is not None and tx.total > 0:
                warn = " !" if tx.total < _WEAK_THRESHOLD else ""
                bar = _score_bar(tx.total)
                typ = tx.recommended_type or "?"
                alt = f"/{tx.alt_type}" if tx.alt_type else ""
                meta = ""
                if tx.bpm_delta and abs(tx.bpm_delta) > 0.5:
                    meta += f" bpm{tx.bpm_delta:+.0f}"
                if tx.from_key and tx.to_key and tx.from_key != tx.to_key:
                    meta += f" {tx.from_key}>{tx.to_key}"
                lines.append(f"     [{bar}] {tx.total:.2f}{warn}  {typ}{alt}{meta}")
            elif tx is not None:
                lines.append("     [XXXXX] 0.00 !  CONFLICT")

        keys = [k for tr in tracks if (k := tr.get("key"))]
        lines += ["", "-" * 50]
        if keys:
            lines.append("Keys  " + " ".join(keys))
        if bpms:
            safe_lo = max(bpm_min - 2, 120)
            lines.append(
                f"BPM   {bpm_min:.0f}-{bpm_max:.0f}  safe {safe_lo:.0f}-{bpm_max + 2:.0f}"
            )

        return "\n".join(lines) + "\n"

    @staticmethod
    def write_json_guide(
        set_name: str,
        tracks: list[dict[str, Any]],
        scores: list[TransitionScoreResult],
    ) -> str:
        """Generate JSON export."""
        bpms = [tr["bpm"] for tr in tracks if tr.get("bpm")]
        total_s = sum(tr.get("duration_s") or 0 for tr in tracks)
        guide = {
            "set_name": set_name,
            "track_count": len(tracks),
            "tracks": tracks,
            "transitions": [s.model_dump() for s in scores],
            "analytics": {
                "bpm_range": [min(bpms), max(bpms)] if bpms else [],
                "total_duration_s": total_s,
            },
        }
        return json.dumps(guide, ensure_ascii=False, indent=2)

    async def sync_to_ym(
        self,
        tracks: list[dict[str, Any]],
        ym_user_id: int,
        ym_playlist_title: str,
    ) -> int:
        """Create a YM playlist with set tracks. Returns playlist kind."""
        if self.ym_client is None:
            msg = "YM client not configured"
            raise ValueError(msg)

        from app.models.metadata_yandex import YandexMetadata

        track_ids = [tr["track_id"] for tr in tracks]
        ym_tracks: list[dict[str, str]] = []

        if track_ids:
            stmt = select(YandexMetadata).where(YandexMetadata.track_id.in_(track_ids))
            result = await self.session.execute(stmt)
            ym_map = {row.track_id: row for row in result.scalars()}
        else:
            ym_map = {}

        for tr in tracks:
            tid = tr["track_id"]
            row = ym_map.get(tid)
            if row and row.yandex_track_id:
                ym_tracks.append(
                    {
                        "id": str(row.yandex_track_id),
                        "albumId": str(row.yandex_album_id or ""),
                    }
                )
            elif tid > 1_000_000:
                logger.warning("No YM metadata for track_id=%d (YM native, no album)", tid)

        kind = await self.ym_client.create_playlist(ym_user_id, ym_playlist_title)
        if ym_tracks:
            await self.ym_client.add_tracks_to_playlist(ym_user_id, kind, ym_tracks, revision=1)

        return kind

    async def write_files(
        self,
        set_name: str,
        version_id: int,
        scores: list[TransitionScoreResult],
    ) -> dict[str, Any]:
        """Write M3U, JSON, cheat sheet, and copy MP3s. Returns result dict."""
        from app.services.set_export import export_m3u

        items_list = await self.set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)
        tracks = await self.collect_track_data(items)

        out = output_dir(set_name)
        out.mkdir(parents=True, exist_ok=True)

        mp3_copied, mp3_skipped = self.copy_mp3_files(tracks, out)
        self.set_local_paths(tracks)

        files_written: list[str] = []

        m3u_path = out / f"{set_name}.m3u8"
        m3u_path.write_text(export_m3u(tracks, set_name=set_name), encoding="utf-8")
        files_written.append(m3u_path.name)

        json_path = out / f"{set_name}.json"
        json_path.write_text(self.write_json_guide(set_name, tracks, scores), encoding="utf-8")
        files_written.append(json_path.name)

        cheat_path = out / "cheat_sheet.txt"
        cheat_path.write_text(
            self.generate_cheat_sheet(set_name, tracks, scores), encoding="utf-8"
        )
        files_written.append(cheat_path.name)

        return {
            "output_dir": str(out),
            "files_written": files_written,
            "mp3_copied": mp3_copied,
            "mp3_skipped": mp3_skipped,
            "tracks": tracks,
        }
