#!/usr/bin/env python3
"""Refresh Yandex Music metadata for tracks missing or with stale data.

Fetches track metadata from YM API in batches, handles rate limiting,
and upserts into yandex_metadata table.

Usage:
    uv run python scripts/refresh_ym_metadata.py --mode missing
    uv run python scripts/refresh_ym_metadata.py --mode stale --days 14
    uv run python scripts/refresh_ym_metadata.py --mode all --dry-run
    uv run python scripts/refresh_ym_metadata.py --mode missing --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# fmt: off
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# fmt: on

import httpx
from sqlalchemy import text

from app.config import settings
from app.database import close_db, init_db, session_factory

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"refresh_ym_{datetime.now():%Y%m%d_%H%M%S}.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_console, _file_handler])
logger = logging.getLogger(__name__)
logger.info("Log file: %s", _log_file)

# YM provider_id
YM_PROVIDER_ID = 4
# Rate limit: 1.5s between requests
REQUEST_DELAY = 1.5
MAX_BATCH_SIZE = 100
MAX_RETRIES = 5


async def get_tracks_missing_metadata() -> list[tuple[int, str]]:
    """Return [(track_id, ym_track_id)] for tracks without yandex_metadata."""
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT pti.track_id, pti.provider_track_id
                FROM provider_track_ids pti
                JOIN tracks t ON t.track_id = pti.track_id AND t.status = 0
                LEFT JOIN yandex_metadata ym ON ym.track_id = pti.track_id
                WHERE pti.provider_id = :pid
                AND ym.track_id IS NULL
                ORDER BY pti.track_id
            """),
            {"pid": YM_PROVIDER_ID},
        )
        return [(row[0], row[1]) for row in result.fetchall()]


async def get_tracks_stale_metadata(days: int) -> list[tuple[int, str]]:
    """Return [(track_id, ym_track_id)] for tracks with metadata older than N days."""
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT pti.track_id, pti.provider_track_id
                FROM provider_track_ids pti
                JOIN yandex_metadata ym ON ym.track_id = pti.track_id
                JOIN tracks t ON t.track_id = pti.track_id AND t.status = 0
                WHERE pti.provider_id = :pid
                AND ym.updated_at < datetime('now', :age)
                ORDER BY ym.updated_at
            """),
            {"pid": YM_PROVIDER_ID, "age": f"-{days} days"},
        )
        return [(row[0], row[1]) for row in result.fetchall()]


async def fetch_tracks_from_ym(
    client: httpx.AsyncClient,
    ym_track_ids: list[str],
) -> list[dict]:
    """Fetch track data from YM API with retry and rate limiting."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(
                "/tracks",
                data={"track-ids": ",".join(ym_track_ids)},
            )
            if resp.status_code == 429:
                wait = (2**attempt) * 5 + random.uniform(0, 2)
                logger.warning("429 rate limited, waiting %.1fs (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", [])  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = (2**attempt) * 5 + random.uniform(0, 2)
                logger.warning("429 rate limited, waiting %.1fs (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise

    logger.error("Max retries exceeded for batch of %d tracks", len(ym_track_ids))
    return []


def extract_metadata(track_data: dict, internal_track_id: int) -> dict:
    """Extract metadata fields from YM API track response."""
    albums = track_data.get("albums", [])
    album = albums[0] if albums else {}
    labels = album.get("labels", [])
    label = labels[0] if labels else {}

    # Label can be a dict or a string
    label_name = label.get("name") if isinstance(label, dict) else str(label) if label else None

    return {
        "track_id": internal_track_id,
        "yandex_track_id": str(track_data.get("id", "")),
        "yandex_album_id": str(album.get("id", "")) if album else None,
        "album_title": album.get("title"),
        "album_type": album.get("type"),
        "album_genre": album.get("genre"),
        "album_year": album.get("year"),
        "label_name": label_name,
        "release_date": album.get("releaseDate"),
        "duration_ms": track_data.get("durationMs"),
        "cover_uri": track_data.get("coverUri"),
        "explicit": track_data.get("explicit", False),
        "extra": json.dumps(
            {
                k: v
                for k, v in track_data.items()
                if k
                not in {
                    "id",
                    "albums",
                    "durationMs",
                    "coverUri",
                    "explicit",
                    "title",
                    "artists",
                }
                and v is not None
            }
        ),
    }


async def upsert_metadata(metadata_list: list[dict]) -> int:
    """Upsert metadata into yandex_metadata table. Returns count of upserted rows."""
    if not metadata_list:
        return 0

    async with session_factory() as session:
        for meta in metadata_list:
            await session.execute(
                text("""
                    INSERT INTO yandex_metadata (
                        track_id, yandex_track_id, yandex_album_id,
                        album_title, album_type, album_genre, album_year,
                        label_name, release_date, duration_ms, cover_uri,
                        explicit, extra, created_at, updated_at
                    ) VALUES (
                        :track_id, :yandex_track_id, :yandex_album_id,
                        :album_title, :album_type, :album_genre, :album_year,
                        :label_name, :release_date, :duration_ms, :cover_uri,
                        :explicit, :extra, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    ) ON CONFLICT(track_id) DO UPDATE SET
                        yandex_album_id = excluded.yandex_album_id,
                        album_title = excluded.album_title,
                        album_type = excluded.album_type,
                        album_genre = excluded.album_genre,
                        album_year = excluded.album_year,
                        label_name = excluded.label_name,
                        release_date = excluded.release_date,
                        duration_ms = excluded.duration_ms,
                        cover_uri = excluded.cover_uri,
                        explicit = excluded.explicit,
                        extra = excluded.extra,
                        updated_at = CURRENT_TIMESTAMP
                """),
                meta,
            )
        await session.commit()
    return len(metadata_list)


async def process_batch(
    client: httpx.AsyncClient,
    batch: list[tuple[int, str]],
    ym_to_internal: dict[str, int],
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Process a batch of tracks. Returns (success_count, fail_count)."""
    ym_ids = [ym_id for _, ym_id in batch]
    tracks_data = await fetch_tracks_from_ym(client, ym_ids)

    if not tracks_data:
        return 0, len(batch)

    metadata_list = []
    for track_data in tracks_data:
        ym_id = str(track_data.get("id", ""))
        # YM can return "123:456" format (trackId:albumId)
        base_ym_id = ym_id.split(":")[0] if ":" in ym_id else ym_id
        internal_id = ym_to_internal.get(ym_id) or ym_to_internal.get(base_ym_id)
        if internal_id is None:
            logger.debug("No internal mapping for YM track %s", ym_id)
            continue
        metadata_list.append(extract_metadata(track_data, internal_id))

    if dry_run:
        logger.info("  [dry-run] would upsert %d tracks", len(metadata_list))
        return len(metadata_list), len(batch) - len(metadata_list)

    upserted = await upsert_metadata(metadata_list)
    failed = len(batch) - upserted
    return upserted, failed


async def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh YM metadata")
    parser.add_argument(
        "--mode",
        choices=["missing", "stale", "all"],
        default="all",
        help="What to refresh (default: all)",
    )
    parser.add_argument("--days", type=int, default=30, help="Staleness threshold (default: 30)")
    parser.add_argument("--batch", type=int, default=50, help="Tracks per API request (max 100)")
    parser.add_argument("--limit", type=int, help="Max tracks to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    if not settings.yandex_music_token:
        logger.error("YANDEX_MUSIC_TOKEN not set in .env")
        sys.exit(1)

    batch_size = min(args.batch, MAX_BATCH_SIZE)

    await init_db()

    try:
        # Collect tracks to process
        tracks: list[tuple[int, str]] = []
        if args.mode in ("missing", "all"):
            missing = await get_tracks_missing_metadata()
            logger.info("Missing metadata: %d tracks", len(missing))
            tracks.extend(missing)
        if args.mode in ("stale", "all"):
            stale = await get_tracks_stale_metadata(args.days)
            logger.info("Stale metadata (>%d days): %d tracks", args.days, len(stale))
            # Deduplicate
            existing_ids = {t[0] for t in tracks}
            tracks.extend(t for t in stale if t[0] not in existing_ids)

        if args.limit:
            tracks = tracks[: args.limit]

        if not tracks:
            logger.info("Nothing to refresh!")
            return

        logger.info("Total to process: %d tracks", len(tracks))
        if args.dry_run:
            logger.info("[dry-run mode]")

        # Build YM ID → internal ID mapping
        ym_to_internal = {ym_id: tid for tid, ym_id in tracks}

        # Process in batches
        headers = {"Authorization": f"OAuth {settings.yandex_music_token}"}
        total_success = total_fail = 0
        start = time.monotonic()

        async with httpx.AsyncClient(
            base_url=str(settings.yandex_music_base_url),
            headers=headers,
            timeout=30.0,
        ) as client:
            batches = [tracks[i : i + batch_size] for i in range(0, len(tracks), batch_size)]

            for batch_idx, batch in enumerate(batches, 1):
                logger.info("Batch %d/%d (%d tracks)...", batch_idx, len(batches), len(batch))
                success, fail = await process_batch(
                    client, batch, ym_to_internal, dry_run=args.dry_run
                )
                total_success += success
                total_fail += fail

                # Rate limiting between batches
                if batch_idx < len(batches):
                    await asyncio.sleep(REQUEST_DELAY)

        elapsed = time.monotonic() - start
        print(f"\n{'=' * 60}")
        print(f"Success:  {total_success:4d} tracks")
        print(f"Failed:   {total_fail:4d} tracks")
        print(f"{'─' * 60}")
        print(f"Total:    {len(tracks):4d} tracks in {elapsed:.1f}s")
        if args.dry_run:
            print("[dry-run — no DB updates]")
        print(f"{'=' * 60}")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
