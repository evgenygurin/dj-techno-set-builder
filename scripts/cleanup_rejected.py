#!/usr/bin/env python3
"""Remove rejected tracks from YM playlist, local DB, and disk.

Reads a rejection report JSON and performs 3-phase cleanup:
  Phase 1: Remove from YM playlist via API
  Phase 2: Remove from local DB (dj_playlist_items)
  Phase 3: Delete mp3 files from disk

Dry-run by default — pass --confirm to actually delete.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import text

from app.config import settings
from app.database import close_db, init_db, session_factory

# ── Logging ──────────────────────────────────────────────
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"cleanup_{datetime.now():%Y%m%d_%H%M%S}.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_console, _fh])
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────
YM_USER_ID = "250905515"
YM_PLAYLIST_KIND = 1271
LOCAL_PLAYLIST_ID = 2
AUDIO_DIR = Path(settings.dj_library_path).expanduser().parent / "techno-develop-recs"
YM_BASE = "https://api.music.yandex.net"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cleanup rejected tracks")
    p.add_argument("--confirm", action="store_true", help="Actually delete (dry-run without)")
    p.add_argument("--report", type=Path, help="Path to rejection report JSON")
    p.add_argument("--skip-ym", action="store_true", help="Skip YM phase (local only)")
    return p.parse_args()


def find_latest_report() -> Path:
    """Find the most recent rejection report in AUDIO_DIR."""
    reports = sorted(AUDIO_DIR.glob("rejection_report_*.json"), reverse=True)
    if not reports:
        raise FileNotFoundError(f"No rejection reports in {AUDIO_DIR}")
    return reports[0]


def load_report(path: Path) -> dict:
    """Load and validate the rejection report."""
    data = json.loads(path.read_text())
    ids = data.get("ym_ids_to_delete", [])
    if not ids:
        raise ValueError("Report has no ym_ids_to_delete")
    logger.info("Report: %s (%d IDs to delete)", path.name, len(ids))
    return data


async def _fetch_playlist(
    http: httpx.AsyncClient, headers: dict[str, str]
) -> tuple[int, list[dict]]:
    """Fetch current playlist, return (revision, tracks)."""
    resp = await http.get(
        f"{YM_BASE}/users/{YM_USER_ID}/playlists/{YM_PLAYLIST_KIND}",
        headers=headers,
    )
    resp.raise_for_status()
    playlist = resp.json()["result"]
    return playlist["revision"], playlist["tracks"]


def _find_first_match(tracks: list[dict], ym_ids: set[str]) -> tuple[int, str, str] | None:
    """Find first track in playlist matching ym_ids, return (idx, tid, aid)."""
    for i, t in enumerate(tracks):
        tid = str(t["id"])
        if tid in ym_ids:
            albums = t.get("track", {}).get("albums", [])
            aid = str(albums[0]["id"]) if albums else ""
            return (i, tid, aid)
    return None


async def phase1_ym_playlist(ym_ids: set[str], *, dry: bool) -> None:
    """Remove tracks from YM playlist via API.

    Strategy: always delete the FIRST matching track, then re-fetch.
    This avoids index-shift bugs and stale-snapshot issues with the YM API.
    """
    logger.info("Phase 1: YM playlist (%d tracks to remove)", len(ym_ids))
    token = settings.yandex_music_token
    if not token:
        raise RuntimeError("yandex_music_token not configured in .env")

    remaining = set(ym_ids)
    deleted = 0
    consecutive_412 = 0
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=30.0) as http:
        headers = {"Authorization": f"OAuth {token}"}

        revision, tracks = await _fetch_playlist(http, headers)
        logger.info("Playlist: %d tracks, revision=%d", len(tracks), revision)

        # Count how many we need to delete
        total = sum(1 for t in tracks if str(t["id"]) in remaining)
        logger.info("Found %d / %d tracks in current playlist", total, len(ym_ids))
        if total == 0:
            logger.info("Nothing to delete from YM")
            return

        while True:
            match = _find_first_match(tracks, remaining)
            if not match:
                break
            idx, tid, aid = match

            if dry:
                remaining.discard(tid)
                deleted += 1
                # In dry mode, just scan without re-fetching
                tracks = [t for t in tracks if str(t["id"]) != tid]
                continue

            diff = json.dumps(
                [
                    {
                        "op": "delete",
                        "from": idx,
                        "to": idx + 1,
                        "tracks": [{"id": tid, "albumId": aid}],
                    }
                ]
            )

            # Retry with backoff on 429
            ok = False
            for attempt in range(5):
                resp = await http.post(
                    f"{YM_BASE}/users/{YM_USER_ID}/playlists/{YM_PLAYLIST_KIND}/change",
                    headers=headers,
                    data={"diff": diff, "revision": str(revision)},
                )
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("  429 rate-limited, waiting %ds...", wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code == 412:
                    consecutive_412 += 1
                    if consecutive_412 > 5:
                        raise RuntimeError(f"Persistent 412 after {consecutive_412} attempts")
                    logger.warning("  412, re-fetching playlist...")
                    await asyncio.sleep(3)
                    revision, tracks = await _fetch_playlist(http, headers)
                    break  # retry with fresh data
                resp.raise_for_status()
                ok = True
                break
            else:
                raise RuntimeError(f"5 retries exhausted for track {tid}")

            if not ok:
                continue  # 412 handled, retry with fresh playlist

            # Success — update state
            result = resp.json().get("result", {})
            revision = result.get("revision", revision + 1)
            remaining.discard(tid)
            deleted += 1
            consecutive_412 = 0

            if deleted % 20 == 0:
                elapsed = time.monotonic() - start
                logger.info(
                    "  YM: %d/%d deleted (%.1f/min)",
                    deleted,
                    total,
                    deleted / (elapsed / 60) if elapsed > 0 else 0,
                )

            # Re-fetch every 10 deletions to keep indices fresh
            if deleted % 10 == 0:
                revision, tracks = await _fetch_playlist(http, headers)
            else:
                # Remove from local copy to avoid re-fetch every time
                tracks = [t for t in tracks if str(t["id"]) != tid]

            await asyncio.sleep(1.0)

    elapsed = time.monotonic() - start
    logger.info(
        "Phase 1 done: %d deleted in %.1f min%s", deleted, elapsed / 60, " (dry)" if dry else ""
    )


async def phase2_local_db(report: dict, *, dry: bool) -> None:
    """Delete rejected tracks from dj_playlist_items."""
    logger.info("Phase 2: Local DB cleanup")

    # Collect local track_ids from rejection report
    track_ids = set()
    for tier_tracks in report.get("rejected_by_tier", {}).values():
        for t in tier_tracks:
            track_ids.add(t["track_id"])

    if not track_ids:
        logger.info("No track_ids found in report")
        return

    logger.info("Track IDs to remove from playlist: %d", len(track_ids))

    await init_db()
    try:
        async with session_factory() as session:
            if dry:
                result = await session.execute(
                    text("""
                    SELECT COUNT(*) FROM dj_playlist_items
                    WHERE playlist_id = :pid AND track_id IN (SELECT value FROM json_each(:ids))
                """),
                    {"pid": LOCAL_PLAYLIST_ID, "ids": json.dumps(list(track_ids))},
                )
                count = result.scalar()
                logger.info("[DRY] Would delete %d rows from dj_playlist_items", count)
            else:
                result = await session.execute(
                    text("""
                    DELETE FROM dj_playlist_items
                    WHERE playlist_id = :pid AND track_id IN (SELECT value FROM json_each(:ids))
                """),
                    {"pid": LOCAL_PLAYLIST_ID, "ids": json.dumps(list(track_ids))},
                )
                await session.commit()
                logger.info("Deleted %d rows from dj_playlist_items", result.rowcount)
    finally:
        await close_db()

    logger.info("Phase 2 done")


def phase3_delete_files(report: dict, *, dry: bool) -> None:
    """Delete mp3 files for rejected tracks."""
    logger.info("Phase 3: MP3 file cleanup")

    track_ids = set()
    for tier_tracks in report.get("rejected_by_tier", {}).values():
        for t in tier_tracks:
            track_ids.add(t["track_id"])

    deleted = skipped = 0
    for tid in sorted(track_ids):
        candidates = list(AUDIO_DIR.glob(f"{tid}_*.mp3"))
        if not candidates:
            skipped += 1
            continue
        for path in candidates:
            if dry:
                size_mb = path.stat().st_size / 1e6
                logger.debug("[DRY] Would delete %s (%.1f MB)", path.name, size_mb)
                deleted += 1
            else:
                size_mb = path.stat().st_size / 1e6
                path.unlink()
                logger.debug("Deleted %s (%.1f MB)", path.name, size_mb)
                deleted += 1

    logger.info(
        "Phase 3 done: %d files %s, %d no file%s",
        deleted,
        "would delete" if dry else "deleted",
        skipped,
        " (dry)" if dry else "",
    )


async def main() -> None:
    args = parse_args()
    report_path = args.report or find_latest_report()
    report = load_report(report_path)
    ym_ids = set(report["ym_ids_to_delete"])
    dry = not args.confirm
    mode = "DRY RUN" if dry else "LIVE"
    logger.info("Mode: %s | Log: %s", mode, _log_file)

    # Phase 1: YM playlist
    if not args.skip_ym:
        await phase1_ym_playlist(ym_ids, dry=dry)
    else:
        logger.info("Phase 1 skipped (--skip-ym)")

    # Phase 2: Local DB
    await phase2_local_db(report, dry=dry)

    # Phase 3: MP3 files
    phase3_delete_files(report, dry=dry)

    print(f"\n{'=' * 50}")
    print(f"CLEANUP {'DRY RUN' if dry else 'COMPLETE'}")
    print(f"{'=' * 50}")
    print(f"  YM IDs to delete:     {len(ym_ids)}")
    print(f"  Mode:                 {mode}")
    print(f"{'=' * 50}")

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
