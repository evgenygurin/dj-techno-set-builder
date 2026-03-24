#!/usr/bin/env python3
"""Live smoke-test for YandexMusicClient — hits real YM API.

Usage:
    uv run python scripts/test_ym_client_live.py
    uv run python scripts/test_ym_client_live.py --verbose
    uv run python scripts/test_ym_client_live.py --skip-write   # skip mutating ops

Requires YANDEX_MUSIC_TOKEN and YANDEX_MUSIC_USER_ID in .env
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.yandex_music import create_ym_client  # noqa: E402
from app.config import settings  # noqa: E402


@dataclass
class TestResult:
    name: str
    ok: bool
    detail: str
    error: str = ""


@dataclass
class Report:
    results: list[TestResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, error: str = "") -> None:
        self.results.append(TestResult(name=name, ok=ok, detail=detail, error=error))

    def print(self) -> None:
        passed = sum(1 for r in self.results if r.ok)
        failed = sum(1 for r in self.results if not r.ok)
        print()
        print("=" * 60)
        for r in self.results:
            icon = "✅" if r.ok else "❌"
            line = f"{icon} {r.name}: {r.detail}"
            if r.error:
                line += f" — {r.error}"
            print(line)
        print("=" * 60)
        print(f"  {passed} passed, {failed} failed, {len(self.results)} total")
        if failed:
            print("  SOME TESTS FAILED")
        else:
            print("  ALL PASSED")


async def run_tests(*, verbose: bool = False, skip_write: bool = False) -> int:
    token = settings.yandex_music_token
    user_id = settings.yandex_music_user_id
    if not token or not user_id:
        print("ERROR: YANDEX_MUSIC_TOKEN and YANDEX_MUSIC_USER_ID must be set in .env")
        return 1

    uid = int(user_id)
    client = create_ym_client(token=token, user_id=user_id)
    report = Report()

    try:
        # ── Search ──────────────────────────────────────
        try:
            results = await client.search_tracks("Boris Brejcha")
            assert len(results) > 0, "empty results"
            report.add("search_tracks", True, f"{len(results)} results")
        except Exception as e:
            report.add("search_tracks", False, "FAILED", str(e))

        # search pagination
        try:
            p0 = await client.search_tracks("techno", page=0)
            p1 = await client.search_tracks("techno", page=1)
            ids0 = {t["id"] for t in p0}
            ids1 = {t["id"] for t in p1}
            assert p1 and ids0 != ids1, "pages identical"
            report.add("search_tracks(page)", True, f"p0={len(p0)}, p1={len(p1)}")
        except Exception as e:
            report.add("search_tracks(page)", False, "FAILED", str(e))

        # search nocorrect
        try:
            r = await client.search_tracks("techno minimal", nocorrect=True)
            report.add("search_tracks(nocorrect)", True, f"{len(r)} results")
        except Exception as e:
            report.add("search_tracks(nocorrect)", False, "FAILED", str(e))

        # ── Tracks ──────────────────────────────────────
        test_track_id = str(results[0]["id"]) if results else "103119407"

        try:
            data = await client.fetch_tracks([test_track_id])
            assert test_track_id in data, "track not in result"
            title = data[test_track_id].get("title", "?")
            report.add("fetch_tracks", True, f"'{title}'")
        except Exception as e:
            report.add("fetch_tracks", False, "FAILED", str(e))

        try:
            meta = await client.fetch_tracks_metadata([test_track_id])
            assert len(meta) == 1, f"expected 1, got {len(meta)}"
            report.add("fetch_tracks_metadata", True, f"{len(meta)} track(s)")
        except Exception as e:
            report.add("fetch_tracks_metadata", False, "FAILED", str(e))

        try:
            sim = await client.get_similar_tracks(test_track_id)
            report.add("get_similar_tracks", True, f"{len(sim)} similar")
        except Exception as e:
            report.add("get_similar_tracks", False, "FAILED", str(e))

        try:
            supp = await client.get_track_supplement(test_track_id)
            report.add("get_track_supplement", True, f"keys={list(supp.keys())[:4]}")
        except Exception as e:
            report.add("get_track_supplement", False, "FAILED", str(e))

        # ── Albums ──────────────────────────────────────
        album_id = results[0].get("albums", [{}])[0].get("id") if results else 36081872

        try:
            album = await client.get_album(album_id)
            report.add("get_album", True, f"'{album.get('title', '?')}'")
        except Exception as e:
            report.add("get_album", False, "FAILED", str(e))

        try:
            album_wt = await client.get_album_with_tracks(album_id)
            vols = album_wt.get("volumes", [])
            track_count = sum(len(v) for v in vols)
            report.add("get_album_with_tracks", True, f"{track_count} tracks")
        except Exception as e:
            report.add("get_album_with_tracks", False, "FAILED", str(e))

        # ── Artists ─────────────────────────────────────
        artist_id = results[0].get("artists", [{}])[0].get("id") if results else 3976138

        try:
            at = await client.get_artist_tracks(artist_id, page=0, page_size=5)
            report.add("get_artist_tracks", True, f"{len(at)} tracks")
        except Exception as e:
            report.add("get_artist_tracks", False, "FAILED", str(e))

        # artist tracks pagination
        try:
            at0 = await client.get_artist_tracks(artist_id, page=0, page_size=3)
            at1 = await client.get_artist_tracks(artist_id, page=1, page_size=3)
            overlap = {t["id"] for t in at0} & {t["id"] for t in at1}
            report.add("get_artist_tracks(page)", True, f"p0={len(at0)}, p1={len(at1)}, overlap={len(overlap)}")
        except Exception as e:
            report.add("get_artist_tracks(page)", False, "FAILED", str(e))

        try:
            pop = await client.get_popular_tracks(artist_id)
            report.add("get_popular_tracks", True, f"{len(pop)} tracks")
        except Exception as e:
            report.add("get_popular_tracks", False, "FAILED", str(e))

        # ── Genres ──────────────────────────────────────
        try:
            genres = await client.get_genres()
            assert len(genres) > 0, "empty"
            report.add("get_genres", True, f"{len(genres)} genres")
        except Exception as e:
            report.add("get_genres", False, "FAILED", str(e))

        # ── Playlists ───────────────────────────────────
        try:
            pls = await client.fetch_user_playlists(user_id)
            report.add("fetch_user_playlists", True, f"{len(pls)} playlists")
        except Exception as e:
            report.add("fetch_user_playlists", False, "FAILED", str(e))

        try:
            tracks = await client.fetch_playlist_tracks(user_id, "1280")
            report.add("fetch_playlist_tracks", True, f"{len(tracks)} tracks in kind=1280")
        except Exception as e:
            report.add("fetch_playlist_tracks", False, "FAILED", str(e))

        try:
            recs = await client.get_playlist_recommendations(uid, 1280)
            report.add("get_playlist_recommendations", True, f"{len(recs)} recommended")
        except Exception as e:
            report.add("get_playlist_recommendations", False, "FAILED", str(e))

        # ── Likes ───────────────────────────────────────
        try:
            liked = await client.get_liked_track_ids(uid)
            report.add("get_liked_track_ids", True, f"{len(liked)} liked")
        except Exception as e:
            report.add("get_liked_track_ids", False, "FAILED", str(e))

        try:
            disliked = await client.get_disliked_track_ids(uid)
            report.add("get_disliked_track_ids", True, f"{len(disliked)} disliked")
        except Exception as e:
            report.add("get_disliked_track_ids", False, "FAILED", str(e))

        # ── Download ────────────────────────────────────
        try:
            url = await client.resolve_download_url(test_track_id)
            assert url.startswith("https://"), f"bad url: {url[:30]}"
            report.add("resolve_download_url", True, f"{url[:50]}...")
        except Exception as e:
            report.add("resolve_download_url", False, "FAILED", str(e))

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
                size = await client.download_track(test_track_id, tmp.name)
                report.add("download_track", True, f"{size:,} bytes")
        except Exception as e:
            report.add("download_track", False, "FAILED", str(e))

        # ── Write operations (playlist CRUD) ────────────
        if skip_write:
            report.add("create_playlist", True, "SKIPPED (--skip-write)")
            report.add("rename_playlist", True, "SKIPPED (--skip-write)")
            report.add("set_playlist_visibility", True, "SKIPPED (--skip-write)")
            report.add("add_tracks_to_playlist", True, "SKIPPED (--skip-write)")
            report.add("remove_tracks_from_playlist", True, "SKIPPED (--skip-write)")
            report.add("delete_playlist", True, "SKIPPED (--skip-write)")
            report.add("like_tracks", True, "SKIPPED (--skip-write)")
            report.add("unlike_tracks", True, "SKIPPED (--skip-write)")
        else:
            test_kind: int | None = None
            try:
                test_kind = await client.create_playlist(uid, "__test_ym_client_live__")
                report.add("create_playlist", True, f"kind={test_kind}")
            except Exception as e:
                report.add("create_playlist", False, "FAILED", str(e))

            if test_kind:
                try:
                    await client.rename_playlist(uid, test_kind, "__test_renamed__")
                    report.add("rename_playlist", True, "OK")
                except Exception as e:
                    report.add("rename_playlist", False, "FAILED", str(e))

                try:
                    await client.set_playlist_visibility(uid, test_kind, "private")
                    report.add("set_playlist_visibility", True, "OK")
                except Exception as e:
                    report.add("set_playlist_visibility", False, "FAILED", str(e))

                try:
                    # albumId is REQUIRED by YM API — empty string causes 400
                    test_album_id = str(
                        results[0].get("albums", [{}])[0].get("id", "")
                    ) if results else ""
                    await client.add_tracks_to_playlist(
                        uid, test_kind,
                        [{"id": test_track_id, "albumId": test_album_id}],
                        revision=1,
                    )
                    report.add("add_tracks_to_playlist", True, "1 track added")
                except Exception as e:
                    report.add("add_tracks_to_playlist", False, "FAILED", str(e))

                try:
                    await client.remove_tracks_from_playlist(uid, test_kind, 0, 1, revision=2)
                    report.add("remove_tracks_from_playlist", True, "OK")
                except Exception as e:
                    report.add("remove_tracks_from_playlist", False, "FAILED", str(e))

                try:
                    await client.delete_playlist(uid, test_kind)
                    report.add("delete_playlist", True, "OK")
                except Exception as e:
                    report.add("delete_playlist", False, "FAILED", str(e))

            # like/unlike
            try:
                await client.like_tracks(uid, [test_track_id])
                report.add("like_tracks", True, "OK")
                await asyncio.sleep(0.5)
                await client.unlike_tracks(uid, [test_track_id])
                report.add("unlike_tracks", True, "OK")
            except Exception as e:
                report.add("like_tracks", False, "FAILED", str(e))
                report.add("unlike_tracks", False, "SKIPPED", "like failed")

    finally:
        await client.close()

    report.print()
    return 0 if all(r.ok for r in report.results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Live YM API smoke test")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--skip-write", action="store_true", help="Skip mutating operations")
    args = parser.parse_args()

    exit_code = asyncio.run(run_tests(verbose=args.verbose, skip_write=args.skip_write))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
