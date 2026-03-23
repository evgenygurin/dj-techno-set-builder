#!/usr/bin/env python3
"""Staged analysis of 'Techno Develop Recs' playlist.

Tier 0: Metadata filter (instant) — genre, duration
Tier 1-3: Full audio analysis in ONE PASS per track:
  - Load audio once
  - BPM → reject if outside range (saves DB write)
  - Key + Loudness → reject if too quiet/loud
  - Band energy, spectral, MFCC, beats, structure

PARALLEL: CONCURRENCY tracks processed simultaneously.
Each track runs in its own subprocess via _analyze_worker.py.
Subprocess isolation: SIGBUS/SIGSEGV from essentia on a corrupt file
kills only that worker process, not this orchestrator.
Idempotent: skips already-analyzed tracks. Safe to re-run.
"""

import asyncio
import contextlib
import json
import logging
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.database import close_db, init_db, session_factory
from app.audio._types import TrackFeatures
from app.audio.bpm import estimate_bpm
from app.audio.energy import compute_band_energies
from app.audio.key_detect import detect_key
from app.audio.loader import load_audio, validate_audio
from app.audio.loudness import measure_loudness
from app.audio.spectral import extract_spectral_features

# Worker script that runs each track in an isolated subprocess
WORKER_SCRIPT = Path(__file__).parent / "_analyze_worker.py"

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"analysis_{datetime.now():%Y%m%d_%H%M%S}.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_console, _file_handler])
logger = logging.getLogger(__name__)
logger.info("Log file: %s", _log_file)

# ── Config ──────────────────────────────────────────────────
PLAYLIST_ID = 2
AUDIO_DIR = Path(settings.dj_library_path).expanduser().parent / "techno-develop-recs"
OUTPUT_DIR = Path(settings.dj_library_path).expanduser().parent / "techno-develop-recs"

# Tier 0: metadata
ALLOWED_GENRES = {"techno"}
MIN_DURATION_MS = 180_000  # 3 min
MAX_DURATION_MS = 600_000  # 10 min

# Tier 1: BPM
BPM_MIN = 120.0
BPM_MAX = 150.0

# Tier 2: loudness
LUFS_MIN = -14.0  # too quiet
LUFS_MAX = -3.0  # too loud / clipping

# Parallelism
CONCURRENCY = 4  # simultaneous tracks (8 CPU cores, leave headroom)


# ── Data structures ─────────────────────────────────────────
@dataclass
class RejectedTrack:
    track_id: int
    ym_track_id: str
    title: str
    artist: str
    reason: str
    tier: int
    details: dict = field(default_factory=dict)


@dataclass
class TrackMeta:
    track_id: int
    ym_track_id: str
    title: str
    artist: str
    duration_ms: int
    genre: str | None


# ── Single-pass analysis (CPU-bound, runs in thread) ────────
def analyze_single_pass(audio_path: str, track_id: int) -> dict:
    """Extract ALL features in one pass. Single load_audio call.

    Returns dict with 'features', 'sections', 'bpm', 'lufs_i',
    or 'reject_reason'/'reject_tier' if track should be rejected.
    """
    signal = load_audio(audio_path)
    validate_audio(signal)

    # ── BPM (cheapest check first) ────────────────────────
    bpm_result = estimate_bpm(signal)
    if bpm_result.bpm < BPM_MIN or bpm_result.bpm > BPM_MAX:
        return {
            "reject_reason": f"bpm:{bpm_result.bpm:.1f}",
            "reject_tier": 1,
            "details": {"bpm": round(bpm_result.bpm, 1)},
        }

    # ── Key + Loudness ────────────────────────────────────
    key_result = detect_key(signal)
    loudness_result = measure_loudness(signal)

    if loudness_result.lufs_i < LUFS_MIN:
        return {
            "reject_reason": f"too_quiet:lufs={loudness_result.lufs_i:.1f}",
            "reject_tier": 2,
            "details": {"lufs_i": round(loudness_result.lufs_i, 1)},
        }
    if loudness_result.lufs_i > LUFS_MAX:
        return {
            "reject_reason": f"too_loud:lufs={loudness_result.lufs_i:.1f}",
            "reject_tier": 2,
            "details": {"lufs_i": round(loudness_result.lufs_i, 1)},
        }

    # ── Remaining Phase 1 features ────────────────────────
    band_energy_result = compute_band_energies(signal)
    spectral_result = extract_spectral_features(signal)

    mfcc_result = None
    try:
        from app.audio.mfcc import extract_mfcc

        mfcc_result = extract_mfcc(signal)
    except Exception:
        pass

    # ── Phase 2: beats + structure ────────────────────────
    beats_result = None
    sections_list = []
    try:
        from app.audio.beats import detect_beats
        from app.audio.structure import segment_structure

        beats_result = detect_beats(signal)
        sections_list = segment_structure(
            signal,
            beat_times=beats_result.beat_times,
            track_pulse_clarity=beats_result.pulse_clarity,
        )
    except Exception:
        logger.debug("[%d] beats/structure failed (non-fatal)", track_id)

    features = TrackFeatures(
        bpm=bpm_result,
        key=key_result,
        loudness=loudness_result,
        band_energy=band_energy_result,
        spectral=spectral_result,
        mfcc=mfcc_result,
        beats=beats_result,
    )

    # Validate no NaN/Inf
    for name, val in [
        ("bpm", features.bpm.bpm),
        ("confidence", features.bpm.confidence),
        ("lufs_i", features.loudness.lufs_i),
        ("rms_dbfs", features.loudness.rms_dbfs),
        ("centroid_mean_hz", features.spectral.centroid_mean_hz),
    ]:
        if math.isnan(val) or math.isinf(val):
            return {
                "reject_reason": f"nan_inf:{name}",
                "reject_tier": 3,
                "details": {"field": name},
            }

    return {
        "features": features,
        "sections": sections_list,
        "bpm": bpm_result.bpm,
        "key_code": key_result.key_code,
        "lufs_i": loudness_result.lufs_i,
        "is_atonal": key_result.is_atonal,
    }


# ── Subprocess wrapper ───────────────────────────────────────
def _call_worker(audio_path: str, track_id: int) -> dict:
    """Synchronous: spawn worker subprocess, wait, return parsed JSON.

    Arguments are passed as a list (no shell interpolation), so there
    is no injection risk even if audio_path contains special characters.
    Running in a thread via asyncio.to_thread keeps the event loop free.
    """
    import subprocess

    cmd = [sys.executable, str(WORKER_SCRIPT), audio_path, str(track_id)]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)  # 3 min max
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode(errors="replace")[:400]
        raise RuntimeError(f"worker exit {proc.returncode}: {err}")
    if not proc.stdout:
        raise RuntimeError("worker produced no output")
    return json.loads(proc.stdout.decode())  # type: ignore[no-any-return]


async def analyze_in_subprocess(audio_path: str, track_id: int) -> dict:
    """Analyze one track in an isolated subprocess.  Returns a JSON dict.

    Each track runs as a separate Python process so that SIGBUS / SIGSEGV
    from essentia on a corrupt file kills only that worker, not the main
    orchestrator.  asyncio.to_thread keeps the event loop free while the
    subprocess runs (analysis takes 25-35 s per track).
    """
    return await asyncio.to_thread(_call_worker, audio_path, track_id)


# ── Helpers ─────────────────────────────────────────────────
def is_file_available(path: Path) -> bool:
    """Check if file is fully downloaded locally (not iCloud placeholder)."""
    try:
        s = path.stat()
        if s.st_size <= 0:
            return False
        return s.st_blocks * 512 >= s.st_size * 0.9
    except OSError:
        return False


async def enable_wal_mode() -> None:
    async with session_factory() as session:
        await session.execute(text("PRAGMA journal_mode=WAL"))
        await session.execute(text("PRAGMA busy_timeout=30000"))
        await session.commit()
    logger.info("SQLite WAL mode enabled, busy_timeout=30s")


async def load_playlist_metadata() -> list[TrackMeta]:
    async with session_factory() as session:
        result = await session.execute(
            text("""
            SELECT
                t.track_id,
                COALESCE(ym.yandex_track_id, '') as ym_id,
                t.title,
                COALESCE(
                    (SELECT GROUP_CONCAT(a.name, ', ')
                     FROM track_artists ta JOIN artists a ON ta.artist_id = a.artist_id
                     WHERE ta.track_id = t.track_id),
                    'Unknown'
                ) as artist,
                t.duration_ms,
                ym.album_genre
            FROM dj_playlist_items pi
            JOIN tracks t ON t.track_id = pi.track_id
            LEFT JOIN yandex_metadata ym ON ym.track_id = t.track_id
            WHERE pi.playlist_id = :pid
            ORDER BY pi.sort_index
        """),
            {"pid": PLAYLIST_ID},
        )
        return [
            TrackMeta(
                track_id=row[0],
                ym_track_id=str(row[1]),
                title=row[2] or "Unknown",
                artist=row[3] or "Unknown",
                duration_ms=row[4] or 0,
                genre=row[5],
            )
            for row in result.fetchall()
        ]


async def get_already_analyzed() -> set[int]:
    async with session_factory() as session:
        result = await session.execute(
            text("""
            SELECT taf.track_id FROM track_audio_features_computed taf
            JOIN dj_playlist_items pi ON taf.track_id = pi.track_id
            WHERE pi.playlist_id = :pid
        """),
            {"pid": PLAYLIST_ID},
        )
        return {row[0] for row in result.fetchall()}


def find_audio_file(track_id: int) -> Path | None:
    candidates = list(AUDIO_DIR.glob(f"{track_id}_*.mp3"))
    return candidates[0] if candidates else None


def tier0_metadata(tracks: list[TrackMeta]) -> tuple[list[TrackMeta], list[RejectedTrack]]:
    kept, rejected = [], []
    for t in tracks:
        if t.genre not in ALLOWED_GENRES:
            rejected.append(
                RejectedTrack(
                    t.track_id,
                    t.ym_track_id,
                    t.title,
                    t.artist,
                    f"genre:{t.genre}",
                    0,
                    {"genre": t.genre},
                )
            )
        elif t.duration_ms < MIN_DURATION_MS:
            rejected.append(
                RejectedTrack(
                    t.track_id,
                    t.ym_track_id,
                    t.title,
                    t.artist,
                    f"too_short:{t.duration_ms / 1000:.0f}s",
                    0,
                    {"duration_ms": t.duration_ms},
                )
            )
        elif t.duration_ms > MAX_DURATION_MS:
            rejected.append(
                RejectedTrack(
                    t.track_id,
                    t.ym_track_id,
                    t.title,
                    t.artist,
                    f"too_long:{t.duration_ms / 1000:.0f}s",
                    0,
                    {"duration_ms": t.duration_ms},
                )
            )
        else:
            kept.append(t)
    return kept, rejected


def save_results(rejected: list[RejectedTrack], kept_count: int, tier_stats: dict) -> Path:
    output_path = OUTPUT_DIR / f"rejection_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    by_tier: dict[str, list] = {}
    for r in rejected:
        by_tier.setdefault(f"tier_{r.tier}", []).append(
            {
                "track_id": r.track_id,
                "ym_track_id": r.ym_track_id,
                "title": r.title,
                "artist": r.artist,
                "reason": r.reason,
                **r.details,
            }
        )
    report = {
        "generated_at": datetime.now().isoformat(),
        "playlist_id": PLAYLIST_ID,
        "summary": {
            "total_tracks": tier_stats.get("total", 0),
            "kept": kept_count,
            "rejected": len(rejected),
            **{f"rejected_tier_{k}": v for k, v in tier_stats.items() if k != "total"},
        },
        "ym_ids_to_delete": [r.ym_track_id for r in rejected if r.ym_track_id],
        "rejected_by_tier": by_tier,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    logger.info("Report saved: %s", output_path)
    return output_path


# ── Main ────────────────────────────────────────────────────
async def main() -> None:
    await init_db()
    await enable_wal_mode()

    all_rejected: list[RejectedTrack] = []
    tier_stats: dict[str, int] = {}

    # ── Tier 0: Metadata ─────────────────────────────────
    all_tracks = await load_playlist_metadata()
    tier_stats["total"] = len(all_tracks)
    logger.info("Playlist %d: %d tracks", PLAYLIST_ID, len(all_tracks))

    already_analyzed = await get_already_analyzed()
    if already_analyzed:
        logger.info("Already analyzed: %d (skip)", len(already_analyzed))

    tier0_kept, tier0_rejected = tier0_metadata(all_tracks)
    all_rejected.extend(tier0_rejected)
    tier_stats["tier_0_metadata"] = len(tier0_rejected)
    logger.info(
        "Tier 0: %d → %d kept, %d rejected", len(all_tracks), len(tier0_kept), len(tier0_rejected)
    )

    # ── Find available audio ─────────────────────────────
    tracks_for_audio = []
    no_file = icloud_pending = 0
    for t in tier0_kept:
        if t.track_id in already_analyzed:
            continue
        path = find_audio_file(t.track_id)
        if path is None:
            no_file += 1
        elif not is_file_available(path):
            icloud_pending += 1
        else:
            tracks_for_audio.append((t, path))

    logger.info(
        "Candidates: %d | Done: %d | No file: %d | iCloud: %d",
        len(tracks_for_audio),
        len(already_analyzed & {t.track_id for t in tier0_kept}),
        no_file,
        icloud_pending,
    )

    if not tracks_for_audio:
        save_results(all_rejected, len(tier0_kept), tier_stats)
        await close_db()
        return

    # ── Parallel analysis ────────────────────────────────
    completed = 0
    t1_rejected = t2_rejected = t3_failed = processed = 0
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    start = time.monotonic()
    total = len(tracks_for_audio)

    async def process_one(track: TrackMeta, audio_path: Path) -> None:
        nonlocal completed, t1_rejected, t2_rejected, t3_failed, processed

        async with semaphore:
            # Each track runs in an isolated subprocess (subprocess isolation
            # prevents SIGBUS/SIGSEGV from essentia crashing the orchestrator).
            # The worker does analysis + DB persist; we receive a JSON summary.
            try:
                result = await analyze_in_subprocess(str(audio_path), track.track_id)
            except Exception as e:
                logger.warning("[%d] worker failed: %s", track.track_id, e)
                async with lock:
                    t3_failed += 1
                    processed += 1
                return

            # ── Rejected track ────────────────────────────
            if result["status"] == "rejected":
                tier = result["reject_tier"]
                async with lock:
                    all_rejected.append(
                        RejectedTrack(
                            track.track_id,
                            track.ym_track_id,
                            track.title,
                            track.artist,
                            result["reject_reason"],
                            tier,
                            result.get("details", {}),
                        )
                    )
                    if tier == 1:
                        t1_rejected += 1
                    else:
                        t2_rejected += 1
                    processed += 1
                logger.info("[%d] REJECT %s", track.track_id, result["reject_reason"])
                return

            # ── Success ───────────────────────────────────
            logger.info(
                "[%d] BPM=%.1f key=%d loud=%.1f LUFS%s (run %d)",
                track.track_id,
                result["bpm"],
                result["key_code"],
                result["lufs_i"],
                " [atonal]" if result["is_atonal"] else "",
                result["run_id"],
            )
            async with lock:
                completed += 1
                processed += 1

    async def report_progress() -> None:
        while processed < total:
            await asyncio.sleep(30)
            elapsed = time.monotonic() - start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = total - processed
            eta = remaining / rate if rate > 0 else 0
            logger.info(
                "[%d/%d %.0f%%] %d OK | rej: %d bpm, %d loud"
                " | %d err | %.1f tr/min | ETA %.0f min",
                processed,
                total,
                100 * processed / total,
                completed,
                t1_rejected,
                t2_rejected,
                t3_failed,
                rate * 60,
                eta / 60,
            )

    logger.info("Parallel analysis: %d tracks, concurrency=%d", total, CONCURRENCY)
    progress_task = asyncio.create_task(report_progress())
    await asyncio.gather(*(process_one(t, p) for t, p in tracks_for_audio))
    progress_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await progress_task

    tier_stats["tier_1_bpm"] = t1_rejected
    tier_stats["tier_2_key_loudness"] = t2_rejected
    tier_stats["tier_3_analysis_failed"] = t3_failed

    elapsed = time.monotonic() - start
    total_kept = len(tier0_kept) - t1_rejected - t2_rejected

    print(f"\n{'=' * 60}")
    print(f"TIER 0 (metadata):     -{len(tier0_rejected):4d} tracks")
    print(f"TIER 1 (BPM):          -{t1_rejected:4d} tracks")
    print(f"TIER 2 (key/loudness): -{t2_rejected:4d} tracks")
    print(f"TIER 3 (full):          {completed:4d} completed, {t3_failed} failed")
    print(f"{'─' * 60}")
    print(f"Total rejected:         {len(all_rejected):4d}")
    print(f"Tracks kept (est):      {total_kept:4d}")
    print(f"Time:                   {elapsed / 60:.1f} min")
    if completed > 0:
        print(f"Rate:                   {completed / (elapsed / 60):.1f} tracks/min")
    print(f"{'=' * 60}")

    report_path = save_results(all_rejected, total_kept, tier_stats)
    print(f"\nReport: {report_path}")
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
