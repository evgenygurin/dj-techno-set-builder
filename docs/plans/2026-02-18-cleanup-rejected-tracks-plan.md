# Cleanup Rejected Tracks — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Delete 441 rejected tracks from YM playlist, local DB, and mp3 files on disk.

**Architecture:** Single script `scripts/cleanup_rejected.py` with 3 sequential phases — YM API removal (reverse-index strategy), local DB cleanup (single DELETE), file deletion. Dry-run by default.

**Tech Stack:** Python 3.12, httpx (direct YM API), SQLAlchemy async, argparse

---

### Task 1: Create the script skeleton with CLI and logging

**Files:**
- Create: `scripts/cleanup_rejected.py`

**Step 1: Write the script skeleton**

```python
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

from app.config import settings

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

    logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Verify script parses args and loads report**

Run: `uv run python scripts/cleanup_rejected.py --help`
Expected: usage help with `--confirm`, `--report`, `--skip-ym`

Run: `uv run python scripts/cleanup_rejected.py 2>&1 | head -5`
Expected: dry-run output showing report loaded, then NameError for undefined phase functions

**Step 3: Commit**

```bash
git add scripts/cleanup_rejected.py
git commit -m "feat: scaffold cleanup_rejected.py with CLI and logging"
```

---

### Task 2: Implement Phase 1 — YM playlist deletion

**Files:**
- Modify: `scripts/cleanup_rejected.py`

**Step 1: Add Phase 1 function**

The key challenge: after deleting a track at index N, all tracks above shift down. Solution: delete from **highest index to lowest**.

YM API endpoint: `POST /users/{uid}/playlists/{kind}/change`
Form data: `diff=<JSON>`, `revision=<int>`
Response: updated playlist with new `revision`.

```python
import httpx  # add to imports

async def phase1_ym_playlist(ym_ids: set[str], *, dry: bool) -> None:
    """Remove tracks from YM playlist via API."""
    logger.info("Phase 1: YM playlist (%d tracks to remove)", len(ym_ids))
    token = settings.yandex_music_token
    if not token:
        raise RuntimeError("yandex_music_token not configured in .env")

    async with httpx.AsyncClient(timeout=30.0) as http:
        headers = {"Authorization": f"OAuth {token}"}

        # 1. Fetch current playlist
        resp = await http.get(
            f"{YM_BASE}/users/{YM_USER_ID}/playlists/{YM_PLAYLIST_KIND}",
            headers=headers,
        )
        resp.raise_for_status()
        playlist = resp.json()["result"]
        revision = playlist["revision"]
        tracks = playlist["tracks"]
        logger.info("Playlist: %d tracks, revision=%d", len(tracks), revision)

        # 2. Build deletion list: (index, track_id, album_id)
        to_delete = []
        for i, t in enumerate(tracks):
            tid = str(t["id"])
            if tid in ym_ids:
                albums = t.get("track", {}).get("albums", [])
                aid = str(albums[0]["id"]) if albums else ""
                to_delete.append((i, tid, aid))

        logger.info("Found %d / %d tracks in current playlist", len(to_delete), len(ym_ids))
        if not to_delete:
            logger.info("Nothing to delete from YM")
            return

        # 3. Delete from highest index to lowest
        to_delete.sort(key=lambda x: x[0], reverse=True)

        deleted = 0
        start = time.monotonic()
        for idx, tid, aid in to_delete:
            if dry:
                logger.debug("[DRY] Would delete idx=%d id=%s", idx, tid)
                deleted += 1
                continue

            diff = json.dumps(
                {"diff": {"op": "delete", "from": idx, "to": idx + 1,
                           "tracks": [{"id": tid, "albumId": aid}]}}
            )
            resp = await http.post(
                f"{YM_BASE}/users/{YM_USER_ID}/playlists/{YM_PLAYLIST_KIND}/change",
                headers=headers,
                data={"diff": diff, "revision": str(revision)},
            )
            resp.raise_for_status()
            result = resp.json().get("result", {})
            revision = result.get("revision", revision + 1)
            deleted += 1

            if deleted % 50 == 0:
                elapsed = time.monotonic() - start
                logger.info(
                    "  YM: %d/%d deleted (%.1f/min)",
                    deleted, len(to_delete), deleted / (elapsed / 60) if elapsed > 0 else 0,
                )
            # Rate limit: 0.25s between calls
            await asyncio.sleep(0.25)

    elapsed = time.monotonic() - start
    logger.info("Phase 1 done: %d deleted in %.1f min%s",
                deleted, elapsed / 60, " (dry)" if dry else "")
```

**Step 2: Test dry-run**

Run: `uv run python scripts/cleanup_rejected.py 2>&1 | tail -10`
Expected: "Phase 1: YM playlist (441 tracks to remove)", "Found 441 / 441 tracks in current playlist", "Phase 1 done: 441 deleted in 0.0 min (dry)"

**Step 3: Commit**

```bash
git add scripts/cleanup_rejected.py
git commit -m "feat: add Phase 1 — YM playlist deletion (reverse-index)"
```

---

### Task 3: Implement Phase 2 — Local DB cleanup

**Files:**
- Modify: `scripts/cleanup_rejected.py`

**Step 1: Add Phase 2 function**

Need to map `ym_track_id` → `track_id` for the DB delete. The rejection report has both.

```python
from sqlalchemy import text  # add to imports
from app.database import init_db, close_db, session_factory  # add to imports

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
                result = await session.execute(text("""
                    SELECT COUNT(*) FROM dj_playlist_items
                    WHERE playlist_id = :pid AND track_id IN (SELECT value FROM json_each(:ids))
                """), {"pid": LOCAL_PLAYLIST_ID, "ids": json.dumps(list(track_ids))})
                count = result.scalar()
                logger.info("[DRY] Would delete %d rows from dj_playlist_items", count)
            else:
                result = await session.execute(text("""
                    DELETE FROM dj_playlist_items
                    WHERE playlist_id = :pid AND track_id IN (SELECT value FROM json_each(:ids))
                """), {"pid": LOCAL_PLAYLIST_ID, "ids": json.dumps(list(track_ids))})
                await session.commit()
                logger.info("Deleted %d rows from dj_playlist_items", result.rowcount)
    finally:
        await close_db()

    logger.info("Phase 2 done")
```

**Step 2: Test dry-run**

Run: `uv run python scripts/cleanup_rejected.py 2>&1 | grep "Phase 2"`
Expected: "Phase 2: Local DB cleanup", "[DRY] Would delete 441 rows", "Phase 2 done"

**Step 3: Commit**

```bash
git add scripts/cleanup_rejected.py
git commit -m "feat: add Phase 2 — local DB cleanup"
```

---

### Task 4: Implement Phase 3 — MP3 file deletion

**Files:**
- Modify: `scripts/cleanup_rejected.py`

**Step 1: Add Phase 3 function**

```python
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
                logger.debug("[DRY] Would delete %s (%.1f MB)", path.name, path.stat().st_size / 1e6)
                deleted += 1
            else:
                size_mb = path.stat().st_size / 1e6
                path.unlink()
                logger.debug("Deleted %s (%.1f MB)", path.name, size_mb)
                deleted += 1

    logger.info("Phase 3 done: %d files %s, %d no file%s",
                deleted, "would delete" if dry else "deleted", skipped,
                " (dry)" if dry else "")
```

**Step 2: Test dry-run**

Run: `uv run python scripts/cleanup_rejected.py 2>&1 | grep "Phase 3"`
Expected: "Phase 3: MP3 file cleanup", "Phase 3 done: N files would delete, M no file (dry)"

**Step 3: Commit**

```bash
git add scripts/cleanup_rejected.py
git commit -m "feat: add Phase 3 — MP3 file deletion"
```

---

### Task 5: Add summary report and test full dry-run

**Files:**
- Modify: `scripts/cleanup_rejected.py`

**Step 1: Add summary output to main()**

After all phases, print a summary table:

```python
# Add to end of main(), before logger.info("Done.")
print(f"\n{'=' * 50}")
print(f"CLEANUP {'DRY RUN' if dry else 'COMPLETE'}")
print(f"{'=' * 50}")
print(f"  YM IDs to delete:     {len(ym_ids)}")
print(f"  Mode:                 {mode}")
print(f"{'=' * 50}")
```

**Step 2: Run full dry-run end-to-end**

Run: `uv run python scripts/cleanup_rejected.py 2>&1`
Expected: all 3 phases complete in dry-run mode, summary printed, log file created in `logs/`

Verify log file:
Run: `ls -la logs/cleanup_*.log | tail -1`
Expected: non-empty log file

**Step 3: Run lint**

Run: `uv run ruff check scripts/cleanup_rejected.py && uv run ruff format --check scripts/cleanup_rejected.py`
Expected: no errors

**Step 4: Commit**

```bash
git add scripts/cleanup_rejected.py
git commit -m "feat: complete cleanup_rejected.py with dry-run support"
```

---

### Task 6: Live execution with --confirm

**Step 1: Run with --confirm**

```bash
uv run python scripts/cleanup_rejected.py --confirm 2>&1
```

Expected:
- Phase 1: 441 tracks removed from YM playlist (~2 min at 0.25s/track)
- Phase 2: 441 rows deleted from dj_playlist_items
- Phase 3: N mp3 files deleted

**Step 2: Verify YM playlist**

Call `ym_get_playlist_by_id(userId=250905515, kind=1271)` and confirm trackCount = 559.

**Step 3: Verify local DB**

```bash
sqlite3 "path/to/dev.db" "SELECT COUNT(*) FROM dj_playlist_items WHERE playlist_id=2;"
```
Expected: 559

**Step 4: Verify disk**

```bash
ls techno-develop-recs/*.mp3 | wc -l
```
Expected: 559 (only kept tracks remain)

**Step 5: Commit log**

```bash
git add scripts/cleanup_rejected.py
git commit -m "chore: run cleanup — 441 rejected tracks removed"
```
