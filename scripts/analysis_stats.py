#!/usr/bin/env python3
"""Collect detailed statistics on analysis progress for playlist 2.

Reports:
  - Total tracks, tier 0 metadata filter results
  - Already analyzed (in DB) vs remaining
  - Audio file availability (real vs iCloud stub vs missing)
  - Per-track file sizes for remaining candidates
  - DB state: feature runs, sections counts
"""

import asyncio
from pathlib import Path

from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.database import close_db, init_db, session_factory

PLAYLIST_ID = 2
AUDIO_DIR = Path(settings.dj_library_path).expanduser().parent / "techno-develop-recs"
ALLOWED_GENRES = {"techno"}
MIN_DURATION_MS = 180_000
MAX_DURATION_MS = 600_000


def file_status(path: Path) -> str:
    """Return 'real', 'icloud_stub', or 'missing'."""
    try:
        s = path.stat()
        if s.st_size <= 0:
            return "empty"
        if s.st_blocks * 512 >= s.st_size * 0.9:
            return "real"
        return "icloud_stub"
    except OSError:
        return "missing"


async def main() -> None:
    await init_db()

    async with session_factory() as session:
        # ── All playlist tracks ──────────────────────────────
        rows = (
            await session.execute(
                text("""
            SELECT
                t.track_id, t.title, t.duration_ms,
                ym.album_genre, ym.yandex_track_id
            FROM dj_playlist_items pi
            JOIN tracks t ON t.track_id = pi.track_id
            LEFT JOIN yandex_metadata ym ON ym.track_id = t.track_id
            WHERE pi.playlist_id = :pid
            ORDER BY pi.sort_index
        """),
                {"pid": PLAYLIST_ID},
            )
        ).fetchall()
        total = len(rows)

        # ── Tier 0 filter ────────────────────────────────────
        tier0_reject_genre = 0
        tier0_reject_dur = 0
        tier0_kept_ids = set()
        for r in rows:
            track_id, _title, dur, genre, _ym_id = r
            if genre not in ALLOWED_GENRES:
                tier0_reject_genre += 1
            elif dur and (dur < MIN_DURATION_MS or dur > MAX_DURATION_MS):
                tier0_reject_dur += 1
            else:
                tier0_kept_ids.add(track_id)

        # ── Already analyzed ─────────────────────────────────
        analyzed_rows = (
            await session.execute(
                text("""
            SELECT taf.track_id
            FROM track_audio_features_computed taf
            JOIN dj_playlist_items pi ON taf.track_id = pi.track_id
            WHERE pi.playlist_id = :pid
        """),
                {"pid": PLAYLIST_ID},
            )
        ).fetchall()
        analyzed_ids = {r[0] for r in analyzed_rows}

        # ── Feature runs stats ───────────────────────────────
        run_stats = (
            await session.execute(
                text("""
            SELECT fr.status, COUNT(*)
            FROM feature_extraction_runs fr
            GROUP BY fr.status
        """)
            )
        ).fetchall()

        # ── Sections count ───────────────────────────────────
        sections_count = (
            await session.execute(
                text("""
            SELECT COUNT(*) FROM track_sections ts
            JOIN dj_playlist_items pi ON ts.track_id = pi.track_id
            WHERE pi.playlist_id = :pid
        """),
                {"pid": PLAYLIST_ID},
            )
        ).scalar()

    # ── File availability for remaining ──────────────────────
    remaining_ids = tier0_kept_ids - analyzed_ids
    file_real = file_stub = file_missing = file_no_match = 0
    problem_tracks = []

    for tid in sorted(remaining_ids):
        candidates = list(AUDIO_DIR.glob(f"{tid}_*.mp3"))
        if not candidates:
            file_no_match += 1
            continue
        path = candidates[0]
        status = file_status(path)
        if status == "real":
            file_real += 1
        elif status == "icloud_stub":
            file_stub += 1
            problem_tracks.append((tid, "icloud_stub", path.name))
        else:
            file_missing += 1
            problem_tracks.append((tid, status, path.name))

    # ── Print report ─────────────────────────────────────────
    print(f"{'=' * 60}")
    print(f"PLAYLIST {PLAYLIST_ID} ANALYSIS STATS")
    print(f"{'=' * 60}")
    print()
    print(f"Total tracks:              {total:>5}")
    print(f"Tier 0 reject (genre):     {tier0_reject_genre:>5}")
    print(f"Tier 0 reject (duration):  {tier0_reject_dur:>5}")
    print(f"Tier 0 kept:               {len(tier0_kept_ids):>5}")
    print()
    print(f"Already analyzed (in DB):  {len(analyzed_ids):>5}")
    print(f"  - in tier0 kept:         {len(analyzed_ids & tier0_kept_ids):>5}")
    print(f"Remaining to analyze:      {len(remaining_ids):>5}")
    print()
    print(f"{'─' * 60}")
    print(f"FILE AVAILABILITY (remaining {len(remaining_ids)} tracks):")
    print(f"  Real (on disk):          {file_real:>5}")
    print(f"  iCloud stub:             {file_stub:>5}")
    print(f"  Missing/empty:           {file_missing:>5}")
    print(f"  No file match:           {file_no_match:>5}")
    print()
    print(f"{'─' * 60}")
    print("DB STATE:")
    for status, cnt in run_stats:
        print(f"  Runs [{status}]:  {cnt:>8}")
    print(f"  Sections (playlist):     {sections_count:>5}")
    print()

    if problem_tracks:
        print(f"{'─' * 60}")
        print(f"PROBLEM FILES ({len(problem_tracks)}):")
        for tid, status, name in problem_tracks[:20]:
            print(f"  [{tid}] {status}: {name}")
        if len(problem_tracks) > 20:
            print(f"  ... and {len(problem_tracks) - 20} more")

    print(f"\n{'=' * 60}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
