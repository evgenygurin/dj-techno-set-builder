#!/usr/bin/env python3
"""Analyze tracks from 'Techno develop' playlist (playlist_id=2).

Uses file paths from dj_library_items (tracks in both library/ and
techno-develop-recs/ dirs). Runs analysis in isolated subprocesses.
Idempotent: skips already-analyzed tracks.
"""

import asyncio
import contextlib
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

# fmt: off
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# fmt: on

from app.database import close_db, init_db, session_factory

# Worker script for subprocess isolation
WORKER_SCRIPT = Path(__file__).parent / "_analyze_worker.py"

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"analyze_td_{datetime.now():%Y%m%d_%H%M%S}.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_console, _file_handler])
logger = logging.getLogger(__name__)
logger.info("Log file: %s", _log_file)

PLAYLIST_ID = 2
CONCURRENCY = 4


def _call_worker(audio_path: str, track_id: int) -> dict:
    """Spawn worker subprocess, wait, return parsed JSON."""
    import subprocess

    cmd = [sys.executable, str(WORKER_SCRIPT), audio_path, str(track_id)]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode(errors="replace")[:400]
        raise RuntimeError(f"worker exit {proc.returncode}: {err}")
    if not proc.stdout:
        raise RuntimeError("worker produced no output")
    return json.loads(proc.stdout.decode())  # type: ignore[no-any-return]


async def analyze_in_subprocess(audio_path: str, track_id: int) -> dict:
    return await asyncio.to_thread(_call_worker, audio_path, track_id)


def is_file_available(path: Path) -> bool:
    """Check if file is fully downloaded locally (not iCloud placeholder)."""
    try:
        s = path.stat()
        if s.st_size <= 0:
            return False
        return s.st_blocks * 512 >= s.st_size * 0.9
    except OSError:
        return False


async def get_tracks_needing_analysis() -> list[tuple[int, str, str]]:
    """Return [(track_id, title, file_path)] for tracks without features."""
    async with session_factory() as session:
        await session.execute(text("PRAGMA journal_mode=WAL"))
        await session.execute(text("PRAGMA busy_timeout=30000"))

        result = await session.execute(
            text("""
            SELECT pi.track_id, t.title, dli.file_path
            FROM dj_playlist_items pi
            JOIN tracks t ON t.track_id = pi.track_id
            JOIN dj_library_items dli ON dli.track_id = pi.track_id
            LEFT JOIN track_audio_features_computed taf ON taf.track_id = pi.track_id
            WHERE pi.playlist_id = :pid
              AND taf.track_id IS NULL
            ORDER BY pi.sort_index
        """),
            {"pid": PLAYLIST_ID},
        )
        return [(row[0], row[1], row[2]) for row in result.fetchall()]


async def main() -> None:
    await init_db()

    tracks = await get_tracks_needing_analysis()
    logger.info("Tracks needing analysis: %d", len(tracks))

    if not tracks:
        logger.info("Nothing to analyze!")
        await close_db()
        return

    # Check file availability
    available = []
    no_file = icloud_pending = 0
    for track_id, title, file_path in tracks:
        p = Path(file_path)
        if not p.exists():
            no_file += 1
            logger.debug("[%d] file not found: %s", track_id, file_path)
        elif not is_file_available(p):
            icloud_pending += 1
            logger.debug("[%d] iCloud pending: %s", track_id, file_path)
        else:
            available.append((track_id, title, file_path))

    logger.info(
        "Available: %d | No file: %d | iCloud pending: %d",
        len(available),
        no_file,
        icloud_pending,
    )

    if not available:
        await close_db()
        return

    # Parallel analysis
    total = len(available)
    completed = rejected = failed = processed = 0
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    start = time.monotonic()

    async def process_one(track_id: int, title: str, file_path: str) -> None:
        nonlocal completed, rejected, failed, processed

        async with semaphore:
            try:
                result = await analyze_in_subprocess(file_path, track_id)
            except Exception as e:
                logger.warning("[%d] %s: worker failed: %s", track_id, title, e)
                async with lock:
                    failed += 1
                    processed += 1
                return

            if result["status"] == "rejected":
                logger.info("[%d] REJECT %s — %s", track_id, title, result["reject_reason"])
                async with lock:
                    rejected += 1
                    processed += 1
                return

            logger.info(
                "[%d] OK %s — BPM=%.1f key=%d LUFS=%.1f%s (run %d)",
                track_id,
                title,
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

    logger.info("Starting analysis: %d tracks, concurrency=%d", total, CONCURRENCY)
    progress_task = asyncio.create_task(report_progress())
    await asyncio.gather(*(process_one(tid, title, fp) for tid, title, fp in available))
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
    print(f"{'=' * 60}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
