"""DJ set delivery tool — orchestrates scoring → file export → YM sync.

Visible stages via ctx.info():
  1. Score transitions (with elicitation checkpoint on hard conflicts)
  2. Write M3U8 + JSON + cheat_sheet.txt to output_dir
  3. Sync to Yandex Music (optional)

Each stage is atomic and visible. The tool does not hide decisions —
it surfaces them via ctx.elicit() so the operator can intervene.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yandex_music import YandexMusicClient
from app.config import settings
from app.errors import NotFoundError
from app.mcp.dependencies import (
    get_features_service,
    get_session,
    get_set_service,
    get_track_service,
    get_unified_scoring,
    get_ym_client,
)
from app.mcp.elicitation import resolve_conflict
from app.mcp.resolve import resolve_local_id
from app.mcp.tools._scoring_helpers import sanitize_filename, score_consecutive_transitions
from app.mcp.types.workflows import DeliveryResult, TransitionScoreResult, TransitionSummary
from app.services.features import AudioFeaturesService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.utils.audio.camelot import key_code_to_camelot

logger = logging.getLogger(__name__)

_WEAK_THRESHOLD = 0.85


# ── Internal helpers ──────────────────────────────────────────────────────────


def _safe_name(name: str) -> str:
    """Convert set name to a safe directory name."""
    s = sanitize_filename(name).strip(". ")
    return s.lower().replace(" ", "_")


def _output_dir(set_name: str) -> Path:
    """Resolve output directory from settings.dj_library_path."""
    library = Path(settings.dj_library_path).expanduser()
    base = library.parent / "generated-sets"
    return base / _safe_name(set_name)


async def _score_version(
    set_id: int,
    version_id: int,
    set_svc: DjSetService,
    unified_svc: UnifiedTransitionScoringService,
    features_svc: AudioFeaturesService,
    track_svc: TrackService,
) -> list[TransitionScoreResult]:
    """Score all transitions in a set version via shared helper."""
    items_list = await set_svc.list_items(version_id, offset=0, limit=500)
    items = sorted(items_list.items, key=lambda i: i.sort_index)
    return await score_consecutive_transitions(items, unified_svc, track_svc, features_svc)


def _build_transition_summary(scores: list[TransitionScoreResult]) -> TransitionSummary:
    scored = [s for s in scores if s.total > 0.0]
    return TransitionSummary(
        total=len(scores),
        hard_conflicts=sum(1 for s in scores if s.total == 0.0),
        weak=sum(1 for s in scored if s.total < _WEAK_THRESHOLD),
        avg_score=sum(s.total for s in scored) / len(scored) if scored else 0.0,
        min_score=min((s.total for s in scored), default=0.0),
    )


def _score_bar(score: float) -> str:
    """Render score as a compact 5-char visual bar."""
    if score <= 0:
        return "XXXXX"
    filled = round(score * 5)
    return "#" * filled + "." * (5 - filled)


def _energy_bar(lufs: float, lo: float, hi: float) -> str:
    """Render LUFS as a 10-char energy meter relative to set range."""
    if hi == lo:
        return "=" * 10
    ratio = (lufs - lo) / (hi - lo)
    filled = max(0, min(10, round(ratio * 10)))
    return "=" * filled + "-" * (10 - filled)


def _generate_cheat_sheet(
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
        f"{len(tracks)} tracks  {total_s // 3600}h{(total_s % 3600) // 60:02d}m"
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

    # Footer
    keys = [k for tr in tracks if (k := tr.get("key"))]
    lines += ["", "-" * 50]
    if keys:
        lines.append("Keys  " + " ".join(keys))
    if bpms:
        safe_lo = max(bpm_min - 2, 120)
        lines.append(f"BPM   {bpm_min:.0f}-{bpm_max:.0f}  safe {safe_lo:.0f}-{bpm_max + 2:.0f}")

    return "\n".join(lines) + "\n"


async def _collect_track_data(
    items: list[Any],
    track_svc: TrackService,
    features_svc: AudioFeaturesService,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """Collect per-track metadata + audio features for export."""
    track_ids = [item.track_id for item in items]
    artists_map = await track_svc.get_track_artists(track_ids)

    # Batch-load file paths from dj_library_items
    file_path_map: dict[int, str] = {}
    if session is not None:
        from app.models.dj import DjLibraryItem

        stmt = select(DjLibraryItem.track_id, DjLibraryItem.file_path).where(
            DjLibraryItem.track_id.in_(track_ids),
            DjLibraryItem.file_path.is_not(None),
        )
        rows = await session.execute(stmt)
        file_path_map = {r[0]: r[1] for r in rows if r[1]}

    tracks: list[dict[str, Any]] = []
    for pos, item in enumerate(items, 1):
        entry: dict[str, Any] = {"position": pos, "track_id": item.track_id}
        with contextlib.suppress(NotFoundError):
            track = await track_svc.get(item.track_id)
            entry["title"] = track.title
            entry["duration_s"] = track.duration_ms // 1000

        artists = artists_map.get(item.track_id, [])
        entry["artists"] = ", ".join(artists) if artists else ""

        with contextlib.suppress(Exception):
            feat = await features_svc.get_latest(item.track_id)
            entry["bpm"] = feat.bpm
            entry["lufs"] = feat.lufs_i
            with contextlib.suppress(ValueError):
                entry["key"] = key_code_to_camelot(feat.key_code)

        if item.track_id in file_path_map:
            entry["file_path"] = file_path_map[item.track_id]

        tracks.append(entry)

    return tracks


def _is_icloud_stub(path: Path) -> bool:
    """Check if a file is an iCloud stub (not fully downloaded)."""
    try:
        st = path.stat()
        return hasattr(st, "st_blocks") and st.st_blocks * 512 < st.st_size * 0.9
    except OSError:
        return True


def _copy_mp3_files(tracks: list[dict[str, Any]], out_dir: Path) -> tuple[int, int]:
    """Copy MP3 files from library to output dir with numbered names.

    Returns:
        (copied, skipped) counts.
    """
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
        dest = out_dir / f"{tr['position']:03d}. {safe}.mp3"
        shutil.copy2(src, dest)
        copied += 1
    return copied, skipped


def _write_m3u8(set_name: str, tracks: list[dict[str, Any]]) -> str:
    """Generate M3U8 content from track data."""
    lines = ["#EXTM3U", f"#PLAYLIST:{set_name}"]
    for tr in tracks:
        title = tr.get("title", f"Track {tr['track_id']}")
        artists = tr.get("artists", "")
        display = f"{artists} - {title}" if artists else title
        safe = sanitize_filename(display).strip(". ")
        duration = tr.get("duration_s", -1)
        lines.append(f"#EXTINF:{duration},{title}")
        if tr.get("bpm"):
            lines.append(f"#EXTDJ-BPM:{tr['bpm']}")
        if tr.get("key"):
            lines.append(f"#EXTDJ-KEY:{tr['key']}")
        if tr.get("lufs"):
            lines.append(f"#EXTDJ-ENERGY:{tr['lufs']}")
        lines.append(f"{tr['position']:03d}. {safe}.mp3")
    return "\n".join(lines) + "\n"


def _write_json_guide(
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


# ── YM sync helper ────────────────────────────────────────────────────────────


async def _sync_to_ym(
    set_name: str,
    tracks: list[dict[str, Any]],
    ym_user_id: int,
    ym_playlist_title: str,
    ym_client: YandexMusicClient,
    session: AsyncSession,
) -> int:
    """Create a YM playlist with set tracks. Returns playlist kind.

    Uses the injected session (from parent tool's DI) instead of importing
    session_factory directly. Uses ORM query instead of raw SQL to prevent
    SQL injection (Issue #64, findings 1+2).
    """
    from app.models.metadata_yandex import YandexMetadata

    track_ids = [tr["track_id"] for tr in tracks]
    ym_tracks: list[dict[str, str]] = []

    if track_ids:
        stmt = select(YandexMetadata).where(YandexMetadata.track_id.in_(track_ids))
        result = await session.execute(stmt)
        ym_map = {row.track_id: row for row in result.scalars()}
    else:
        ym_map = {}

    for tr in tracks:
        tid = tr["track_id"]
        row = ym_map.get(tid)
        if row and row.yandex_track_id and row.yandex_album_id:
            ym_tracks.append(
                {"id": str(row.yandex_track_id), "albumId": str(row.yandex_album_id)}
            )
        else:
            # YM-native track: track_id IS the ym_track_id (large int > 1_000_000)
            if tid > 1_000_000:
                # Need album id — skip if not available (set will be partial)
                logger.warning("No YM metadata for track_id=%d (YM native, no album)", tid)

    kind = await ym_client.create_playlist(ym_user_id, ym_playlist_title)
    if ym_tracks:
        await ym_client.add_tracks_to_playlist(ym_user_id, kind, ym_tracks, revision=1)

    return kind


# ── Tool registration ─────────────────────────────────────────────────────────


def register_delivery_tools(mcp: FastMCP) -> None:
    """Register deliver_set tool on the MCP server."""

    @mcp.tool(tags={"setbuilder"}, timeout=300)
    async def deliver_set(
        set_ref: str | int,
        version_id: int,
        ctx: Context,
        skip_conflicts: bool = False,
        sync_to_ym: bool = False,
        ym_user_id: int | None = None,
        ym_playlist_title: str | None = None,
        set_svc: DjSetService = Depends(get_set_service),
        unified_svc: UnifiedTransitionScoringService = Depends(get_unified_scoring),
        features_svc: AudioFeaturesService = Depends(get_features_service),
        track_svc: TrackService = Depends(get_track_service),
        ym_client: YandexMusicClient = Depends(get_ym_client),
        session: AsyncSession = Depends(get_session),
    ) -> DeliveryResult:
        """Deliver a DJ set: score transitions, write files, optionally sync to YM.

        Runs three visible stages with elicitation checkpoints:

        **Stage 1 — Score:** Evaluates every transition. Hard conflicts
        (Camelot dist ≥ 5, score = 0.0) trigger a checkpoint — you decide
        whether to continue or abort before any files are written.

        **Stage 2 — Write files:** Writes M3U8, JSON guide, and cheat_sheet.txt
        to generated-sets/{set_name}/. Skips iCloud stubs silently.

        **Stage 3 — YM sync** (if sync_to_ym=True): Creates or updates a
        Yandex Music playlist with the set's tracks. Requires ym_user_id.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            version_id: Set version to deliver.
            skip_conflicts: Skip hard-conflict checkpoint (for CLI/batch mode).
            sync_to_ym: Push set to Yandex Music as a playlist.
            ym_user_id: YM user ID (required when sync_to_ym=True).
            ym_playlist_title: YM playlist title (default: "{set_name} [set]").
        """
        set_id = resolve_local_id(set_ref, "set")
        dj_set = await set_svc.get(set_id)
        set_name = dj_set.name

        # ── Stage 1: Score transitions ────────────────────────────────────────
        await ctx.info(f"Stage 1/3 — Scoring transitions for '{set_name}'...")
        await ctx.report_progress(progress=0, total=3)

        scores = await _score_version(
            set_id, version_id, set_svc, unified_svc, features_svc, track_svc
        )
        summary = _build_transition_summary(scores)

        conflicts = [s for s in scores if s.total == 0.0]
        weak = [s for s in scores if 0.0 < s.total < _WEAK_THRESHOLD]

        await ctx.info(
            f"Scored {summary.total} transitions: "
            f"{summary.hard_conflicts} hard conflicts, "
            f"{summary.weak} weak (< {_WEAK_THRESHOLD}), "
            f"avg={summary.avg_score:.3f}"
        )

        if conflicts:
            conflict_lines = "\n".join(
                f"  • {c.from_title} → {c.to_title} (score=0.0)" for c in conflicts[:10]
            )
            if skip_conflicts:
                await ctx.info(
                    f"Skipping conflict checkpoint ({len(conflicts)} hard conflicts) "
                    f"— skip_conflicts=True"
                )
            else:
                decision = await resolve_conflict(
                    ctx,
                    f"Found {len(conflicts)} hard conflict(s) — tracks with no audio "
                    f"features or Camelot distance ≥ 5:\n{conflict_lines}\n\n"
                    f"Continue delivery anyway?",
                    options=["continue", "abort"],
                )
                if decision == "abort" or decision is None:
                    return DeliveryResult(
                        set_id=set_id,
                        version_id=version_id,
                        set_name=set_name,
                        output_dir="",
                        files_written=[],
                        transitions=summary,
                        status="aborted",
                    )

        # ── Stage 2: Write files ──────────────────────────────────────────────
        await ctx.report_progress(progress=1, total=3)
        items_list = await set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        tracks = await _collect_track_data(items, track_svc, features_svc, session)

        out_dir = _output_dir(set_name)
        out_dir.mkdir(parents=True, exist_ok=True)

        await ctx.info(f"Stage 2/3 — Writing files to {out_dir}...")

        files_written: list[str] = []

        m3u_path = out_dir / f"{set_name}.m3u8"
        m3u_path.write_text(_write_m3u8(set_name, tracks), encoding="utf-8")
        files_written.append(m3u_path.name)

        json_path = out_dir / f"{set_name}.json"
        json_path.write_text(_write_json_guide(set_name, tracks, scores), encoding="utf-8")
        files_written.append(json_path.name)

        cheat_path = out_dir / "cheat_sheet.txt"
        cheat_path.write_text(_generate_cheat_sheet(set_name, tracks, scores), encoding="utf-8")
        files_written.append(cheat_path.name)

        mp3_copied, mp3_skipped = _copy_mp3_files(tracks, out_dir)
        if mp3_copied:
            await ctx.info(
                f"Written: {', '.join(files_written)} + {mp3_copied} MP3 files"
                f" ({mp3_skipped} skipped — no file or iCloud stub)"
            )
        else:
            await ctx.info(f"Written: {', '.join(files_written)} (no MP3 files copied)")
        if weak:
            await ctx.info(
                f"Note: {len(weak)} weak transitions marked with !!! in cheat_sheet.txt"
            )

        # ── Stage 3: YM sync ──────────────────────────────────────────────────
        ym_kind: int | None = None
        if sync_to_ym:
            if ym_user_id is None:
                await ctx.info("Stage 3/3 — Skipped YM sync: ym_user_id not provided.")
            else:
                await ctx.report_progress(progress=2, total=3)
                title = ym_playlist_title or f"{set_name} [set]"
                await ctx.info(f"Stage 3/3 — Creating YM playlist '{title}'...")
                try:
                    ym_kind = await _sync_to_ym(
                        set_name=set_name,
                        tracks=tracks,
                        ym_user_id=ym_user_id,
                        ym_playlist_title=title,
                        ym_client=ym_client,
                        session=session,
                    )
                    await ctx.info(f"YM playlist created: kind={ym_kind}")
                except (httpx.HTTPStatusError, httpx.ConnectError, ValueError) as exc:
                    await ctx.info(f"YM sync failed: {exc}. Files already written.")

        await ctx.report_progress(progress=3, total=3)

        return DeliveryResult(
            set_id=set_id,
            version_id=version_id,
            set_name=set_name,
            output_dir=str(out_dir),
            files_written=files_written,
            transitions=summary,
            mp3_copied=mp3_copied,
            mp3_skipped=mp3_skipped,
            ym_playlist_kind=ym_kind,
            status="ok",
        )
