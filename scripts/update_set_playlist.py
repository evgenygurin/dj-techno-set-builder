#!/usr/bin/env python3
"""Replace all tracks in YM playlist kind=1275 with version 14 of set local:9."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

YM_BASE = "https://api.music.yandex.net"
YM_USER_ID = "250905515"
YM_KIND = 1275

# Version 14 tracks (sort_index → ym_track_id, ym_album_id) from SQL + YM API
NEW_TRACKS = [
    ("68923354", "11472170"),  # 0  Virtual Reality
    ("56871112", "12088901"),  # 1  Just Gonna Be Me
    ("43670809", "9995498"),  # 2  Luminophor
    ("29341200", "3527622"),  # 3  Destination  [PINNED]
    ("136644397", "35626916"),  # 4  Mothership
    ("3913276", "440075"),  # 5  Verbatim
    ("20045777", "2261719"),  # 6  Box
    ("118279416", "27769222"),  # 7  Shadowed Descent
    ("54991810", "7981779"),  # 8  In Front of Falsehood III
    ("135569227", "35156925"),  # 9  Fractal Collapse  [PINNED]
    ("139205497", "36647201"),  # 10 The Moment
    ("144954571", "39094980"),  # 11 Pryme
    ("128241463", "32181832"),  # 12 Time & Space  [PINNED]
    ("143646847", "38509324"),  # 13 Don't Look Away
    ("131851442", "33640536"),  # 14 Darkness  [PINNED]
]


async def fetch_playlist(http: httpx.AsyncClient, headers: dict) -> tuple[int, list[dict]]:
    """Return (revision, tracks). Retries on 429."""
    for attempt in range(8):
        resp = await http.get(f"{YM_BASE}/users/{YM_USER_ID}/playlists/{YM_KIND}", headers=headers)
        if resp.status_code == 200:
            pl = resp.json()["result"]
            return pl["revision"], pl["tracks"]
        if resp.status_code == 429:
            wait = 2**attempt
            logger.warning("GET 429 rate-limit, waiting %ds (attempt %d)", wait, attempt + 1)
            await asyncio.sleep(wait)
        else:
            resp.raise_for_status()
    raise RuntimeError("Failed to fetch playlist after retries")


async def delete_one(
    http: httpx.AsyncClient,
    headers: dict,
    revision: int,
    idx: int,
    tid: str,
    aid: str,
) -> int | None:
    """Delete track at idx. Return new revision or None on failure."""
    diff = json.dumps(
        [{"op": "delete", "from": idx, "to": idx + 1, "tracks": [{"id": tid, "albumId": aid}]}]
    )
    for attempt in range(5):
        resp = await http.post(
            f"{YM_BASE}/users/{YM_USER_ID}/playlists/{YM_KIND}/change",
            headers=headers,
            data={"diff": diff, "revision": str(revision)},
        )
        if resp.status_code == 200:
            return resp.json()["result"]["revision"]
        if resp.status_code == 429:
            wait = 2**attempt
            logger.warning("429 rate-limit, waiting %ds", wait)
            await asyncio.sleep(wait)
        else:
            logger.error("DELETE failed %s: %s", resp.status_code, resp.text[:200])
            return None
    return None


async def insert_tracks(
    http: httpx.AsyncClient,
    headers: dict,
    revision: int,
) -> bool:
    """Insert all NEW_TRACKS at position 0."""
    tracks_payload = [{"id": tid, "albumId": aid} for tid, aid in NEW_TRACKS]
    diff = json.dumps([{"op": "insert", "at": 0, "tracks": tracks_payload}])
    for attempt in range(5):
        resp = await http.post(
            f"{YM_BASE}/users/{YM_USER_ID}/playlists/{YM_KIND}/change",
            headers=headers,
            data={"diff": diff, "revision": str(revision)},
        )
        if resp.status_code == 200:
            new_rev = resp.json()["result"]["revision"]
            logger.info("Inserted %d tracks → revision=%d", len(NEW_TRACKS), new_rev)
            return True
        if resp.status_code == 429:
            wait = 2**attempt
            logger.warning("429 rate-limit, waiting %ds", wait)
            await asyncio.sleep(wait)
        else:
            logger.error("INSERT failed %s: %s", resp.status_code, resp.text[:300])
            return False
    return False


async def main() -> None:
    token = settings.yandex_music_token
    if not token:
        raise RuntimeError("yandex_music_token not set")

    async with httpx.AsyncClient(timeout=30.0) as http:
        headers = {"Authorization": f"OAuth {token}"}

        # ── Phase 1: delete all existing tracks ────────────────
        revision, tracks = await fetch_playlist(http, headers)
        logger.info("Playlist: %d tracks, revision=%d", len(tracks), revision)

        deleted = 0
        while True:
            revision, tracks = await fetch_playlist(http, headers)
            if not tracks:
                break
            t = tracks[0]
            tid = str(t["id"])
            albums = t.get("track", {}).get("albums", [])
            aid = str(albums[0]["id"]) if albums else "0"
            logger.info("Deleting [0] tid=%s (%s)", tid, t.get("track", {}).get("title", "?"))
            new_rev = await delete_one(http, headers, revision, 0, tid, aid)
            if new_rev is None:
                logger.error("Delete failed, aborting")
                return
            revision = new_rev
            deleted += 1
            await asyncio.sleep(1.5)

        logger.info("Deleted %d tracks. Revision=%d", deleted, revision)

        # ── Phase 2: insert version 14 tracks ──────────────────
        logger.info("Inserting %d new tracks...", len(NEW_TRACKS))
        revision, _ = await fetch_playlist(http, headers)
        ok = await insert_tracks(http, headers, revision)
        if ok:
            logger.info("Done! Playlist updated with version 14 tracks.")
        else:
            logger.error("Insert failed!")


if __name__ == "__main__":
    asyncio.run(main())
