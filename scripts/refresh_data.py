#!/usr/bin/env python3
"""Unified data refresh pipeline: re-extract audio features + sections.

Modes:
  features  — extract audio features for tracks missing them or with old pipeline
  sections  — (placeholder) re-compute sections for tracks with features but no sections
  all       — features then sections

Uses subprocess worker isolation (same pattern as analyze_techno_develop.py).

Usage:
    uv run python scripts/refresh_data.py --mode features --workers 4
    uv run python scripts/refresh_data.py --mode all --dry-run
    uv run python scripts/refresh_data.py --mode features --force --playlist-id 2
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# fmt: off
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# fmt: on

from sqlalchemy import text

from app.infrastructure.database import close_db, init_db, session_factory

WORKER_SCRIPT = Path(__file__).parent / "_analyze_worker.py"
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"refresh_data_{datetime.now():%Y%m%d_%H%M%S}.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_console, _file_handler])
logger = logging.getLogger(__name__)
logger.info("Log file: %s", _log_file)

# Current pipeline version — skip tracks already analyzed with this version
CURRENT_PIPELINE = "1.0"

# Graceful shutdown
_shutdown_requested = False


def _handle_signal(sig: int, _frame: object) -> None:
    global _shutdown_requested
    if _shutdown_requested:
        logger.warning("Force quit!")
        sys.exit(1)
    logger.warning("Ctrl+C — finishing current tracks, then stopping...")
    _shutdown_requested = True


signal.signal(signal.SIGINT, _handle_signal)


def is_file_available(path: Path) -> bool:
    """Check if file is fully downloaded (not an iCloud stub)."""
    try:
        s = path.stat()
        if s.st_size <= 0:
            return False
        return s.st_blocks * 512 >= s.st_size * 0.9
    except OSError:
        return False


async def get_tracks_needing_features(
    *,
    force: bool = False,
    playlist_id: int | None = None,
) -> list[tuple[int, str, str]]:
    """Return [(track_id, title, file_path)] for tracks needing feature extraction.

    Priority 1: tracks with audio files but NO features at all
    Priority 2: tracks with OLD pipeline features (not CURRENT_PIPELINE)
    """
    async with session_factory() as session:
        await session.execute(text("PRAGMA journal_mode=WAL"))
        await session.execute(text("PRAGMA busy_timeout=30000"))

        playlist_join = ""
        playlist_where = ""
        params: dict = {"current": CURRENT_PIPELINE}

        if playlist_id is not None:
            playlist_join = "JOIN dj_playlist_items pi ON pi.track_id = t.track_id"
            playlist_where = "AND pi.playlist_id = :pid"
            params["pid"] = playlist_id

        if force:
            # All tracks with files
            query = f"""
                SELECT t.track_id, t.title, dli.file_path
                FROM tracks t
                JOIN dj_library_items dli ON dli.track_id = t.track_id
                {playlist_join}
                WHERE t.status = 0
                AND dli.file_path IS NOT NULL
                {playlist_where}
                ORDER BY t.track_id
            """
        else:
            # Priority 1: no features at all
            # Priority 2: only old pipeline features
            query = f"""
                SELECT t.track_id, t.title, dli.file_path
                FROM tracks t
                JOIN dj_library_items dli ON dli.track_id = t.track_id
                {playlist_join}
                LEFT JOIN track_audio_features_computed f ON f.track_id = t.track_id
                LEFT JOIN feature_extraction_runs r ON r.run_id = f.run_id
                WHERE t.status = 0
                AND dli.file_path IS NOT NULL
                {playlist_where}
                GROUP BY t.track_id
                HAVING MAX(CASE WHEN r.pipeline_version = :current THEN 1 ELSE 0 END) = 0
                ORDER BY
                    CASE WHEN MAX(f.run_id) IS NULL THEN 0 ELSE 1 END,
                    t.track_id
            """

        result = await session.execute(text(query), params)
        return [(row[0], row[1], row[2]) for row in result.fetchall()]


async def get_tracks_needing_sections() -> list[tuple[int, str]]:
    """Return [(track_id, title)] for tracks with features but no sections."""
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT DISTINCT f.track_id, t.title
                FROM track_audio_features_computed f
                JOIN tracks t ON t.track_id = f.track_id AND t.status = 0
                LEFT JOIN track_sections s ON s.track_id = f.track_id
                WHERE s.track_id IS NULL
                ORDER BY f.track_id
            """)
        )
        return [(row[0], row[1]) for row in result.fetchall()]


def _call_worker(audio_path: str, track_id: int) -> dict:
    """Spawn worker subprocess, wait, return parsed JSON."""
    import subprocess

    cmd = [sys.executable, str(WORKER_SCRIPT), audio_path, str(track_id)]
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode(errors="replace")[:500]
        raise RuntimeError(f"worker exit {proc.returncode}: {err}")
    if not proc.stdout:
        raise RuntimeError("worker produced no output")
    return json.loads(proc.stdout.decode())  # type: ignore[no-any-return]


async def analyze_in_subprocess(audio_path: str, track_id: int) -> dict:
    """Run analysis in a subprocess via thread pool."""
    return await asyncio.to_thread(_call_worker, audio_path, track_id)


async def run_features(
    *,
    workers: int,
    force: bool,
    playlist_id: int | None,
    dry_run: bool,
) -> None:
    """Extract audio features for tracks that need them."""
    global _shutdown_requested

    tracks = await get_tracks_needing_features(force=force, playlist_id=playlist_id)
    logger.info("Tracks needing features: %d", len(tracks))

    if not tracks:
        return

    # Filter by file availability
    available = []
    no_file = icloud_pending = 0
    for track_id, title, file_path in tracks:
        p = Path(file_path)
        if not p.exists():
            no_file += 1
        elif not is_file_available(p):
            icloud_pending += 1
        else:
            available.append((track_id, title, file_path))

    logger.info(
        "Available: %d | No file: %d | iCloud pending: %d",
        len(available),
        no_file,
        icloud_pending,
    )

    if not available:
        return

    if dry_run:
        logger.info("[dry-run] Would analyze %d tracks", len(available))
        for tid, title, fp in available[:10]:
            logger.info("  [%d] %s — %s", tid, title, fp)
        if len(available) > 10:
            logger.info("  ... and %d more", len(available) - 10)
        return

    # Parallel analysis
    total = len(available)
    completed = rejected = failed = processed = 0
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(workers)
    start = time.monotonic()

    async def process_one(track_id: int, title: str, file_path: str) -> None:
        nonlocal completed, rejected, failed, processed

        if _shutdown_requested:
            return

        async with semaphore:
            try:
                result = await analyze_in_subprocess(file_path, track_id)
            except Exception as e:
                logger.warning("[%d] %s: worker failed: %s", track_id, title, e)
                async with lock:
                    failed += 1
                    processed += 1
                return

            if result.get("status") == "rejected":
                logger.info("[%d] REJECT %s — %s", track_id, title, result.get("reject_reason"))
                async with lock:
                    rejected += 1
                    processed += 1
                return

            logger.info(
                "[%d] OK %s — BPM=%.1f key=%d LUFS=%.1f (run %d)",
                track_id,
                title,
                result.get("bpm", 0),
                result.get("key_code", 0),
                result.get("lufs_i", 0),
                result.get("run_id", 0),
            )
            async with lock:
                completed += 1
                processed += 1

    async def report_progress() -> None:
        while processed < total and not _shutdown_requested:
            await asyncio.sleep(30)
            elapsed = time.monotonic() - start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = total - processed
            eta = remaining / rate if rate > 0 else 0
            logger.info(
                "[%d/%d %.0f%%] %d OK | %d rejected | %d failed | %.1f tr/min | ETA %.0f min",
                processed,
                total,
                100 * processed / total,
                completed,
                rejected,
                failed,
                rate * 60,
                eta / 60,
            )

    logger.info("Starting analysis: %d tracks, workers=%d", total, workers)
    progress_task = asyncio.create_task(report_progress())

    tasks = [process_one(tid, title, fp) for tid, title, fp in available]
    await asyncio.gather(*tasks, return_exceptions=True)

    progress_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await progress_task

    elapsed = time.monotonic() - start
    print(f"\n{'=' * 60}")
    print(f"Completed:  {completed:4d} tracks")
    print(f"Rejected:   {rejected:4d} tracks")
    print(f"Failed:     {failed:4d} tracks")
    print(f"{'─' * 60}")
    print(f"Total:      {total:4d} tracks in {elapsed / 60:.1f} min")
    if completed > 0:
        print(f"Rate:       {completed / (elapsed / 60):.1f} tracks/min")
    if _shutdown_requested:
        print("(interrupted by Ctrl+C)")
    print(f"{'=' * 60}")


async def run_sections(*, dry_run: bool) -> None:
    """Re-compute sections for tracks with features but no sections."""
    tracks = await get_tracks_needing_sections()
    logger.info("Tracks needing sections: %d", len(tracks))

    if not tracks:
        return

    if dry_run:
        logger.info("[dry-run] Would compute sections for %d tracks", len(tracks))
        for tid, title in tracks[:10]:
            logger.info("  [%d] %s", tid, title)
        if len(tracks) > 10:
            logger.info("  ... and %d more", len(tracks) - 10)
        return

    # Section computation uses the same worker subprocess
    # The _analyze_worker.py already computes sections as part of full analysis
    # So tracks needing sections but having features = need re-analysis
    logger.info(
        "Section-only extraction not yet implemented — "
        "use --mode features --force to re-analyze these tracks"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Unified data refresh pipeline")
    parser.add_argument(
        "--mode",
        choices=["features", "sections", "all"],
        default="all",
        help="What to refresh (default: all)",
    )
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers (default: 4)")
    parser.add_argument("--force", action="store_true", help="Re-extract even for current pipe")
    parser.add_argument("--playlist-id", type=int, help="Limit to tracks in this playlist")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    await init_db()

    try:
        if args.mode in ("features", "all"):
            await run_features(
                workers=args.workers,
                force=args.force,
                playlist_id=args.playlist_id,
                dry_run=args.dry_run,
            )

        if args.mode in ("sections", "all"):
            await run_sections(dry_run=args.dry_run)

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
