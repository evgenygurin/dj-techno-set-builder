#!/usr/bin/env python3
"""Analyze kept vs deleted playlist pair to understand filtering logic.

Compares two playlists (main and deleted) to understand what signals
distinguish between kept and deleted tracks. Produces actionable filtering
recommendations based on actual data rather than arbitrary thresholds.

Usage:
    uv run python scripts/analyze_playlist_pair.py --main-kind 1280 --deleted-kind 1282
    uv run python scripts/analyze_playlist_pair.py --main-kind 1280 \
        --deleted-kind 1282 --output-report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

import httpx
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.infrastructure.database import close_db, init_db, session_factory
from app.core.models.features import TrackAudioFeaturesComputed
from app.core.models.ingestion import ProviderTrackId
from app.core.models.metadata_yandex import YandexMetadata


@dataclass
class PlaylistAnalysis:
    """Analysis results for a single playlist."""

    kind: str
    name: str
    track_count: int
    ym_track_ids: list[str]
    local_track_ids: list[int] = field(default_factory=list)
    tracks_with_files: int = 0
    tracks_with_features: int = 0
    tracks_without_features: list[str] = field(default_factory=list)

    # Audio feature statistics
    bpm_values: list[float] = field(default_factory=list)
    lufs_values: list[float] = field(default_factory=list)
    energy_values: list[float] = field(default_factory=list)

    # Metadata statistics
    album_years: list[int] = field(default_factory=list)
    compilation_like_count: int = 0

    # YM user feedback
    liked_intersect: set[str] = field(default_factory=set)
    disliked_intersect: set[str] = field(default_factory=set)


@dataclass
class ComparisonReport:
    """Full comparison report between kept and deleted playlists."""

    main: PlaylistAnalysis
    deleted: PlaylistAnalysis

    def summary_stats(self) -> dict[str, Any]:
        """Generate summary statistics comparing the two playlists."""
        return {
            "track_counts": {
                "main": self.main.track_count,
                "deleted": self.deleted.track_count,
            },
            "feature_coverage": {
                "main_with_features": (
                    f"{self.main.tracks_with_features}/{self.main.track_count}"
                ),
                "deleted_with_features": (
                    f"{self.deleted.tracks_with_features}/{self.deleted.track_count}"
                ),
                "main_percentage": round(
                    self.main.tracks_with_features / self.main.track_count * 100, 1
                ),
                "deleted_percentage": round(
                    self.deleted.tracks_with_features / self.deleted.track_count * 100, 1
                ),
            },
            "audio_features": {
                "main_median_bpm": median(self.main.bpm_values) if self.main.bpm_values else None,
                "deleted_median_bpm": median(self.deleted.bpm_values)
                if self.deleted.bpm_values
                else None,
                "main_median_lufs": median(self.main.lufs_values)
                if self.main.lufs_values
                else None,
                "deleted_median_lufs": median(self.deleted.lufs_values)
                if self.deleted.lufs_values
                else None,
                "main_median_energy": median(self.main.energy_values)
                if self.main.energy_values
                else None,
                "deleted_median_energy": median(self.deleted.energy_values)
                if self.deleted.energy_values
                else None,
            },
            "metadata_signals": {
                "main_median_year": median(self.main.album_years)
                if self.main.album_years
                else None,
                "deleted_median_year": median(self.deleted.album_years)
                if self.deleted.album_years
                else None,
                "main_compilation_rate": round(
                    self.main.compilation_like_count / self.main.track_count * 100, 1
                ),
                "deleted_compilation_rate": round(
                    self.deleted.compilation_like_count / self.deleted.track_count * 100, 1
                ),
            },
            "user_feedback": {
                "main_liked_count": len(self.main.liked_intersect),
                "main_disliked_count": len(self.main.disliked_intersect),
                "deleted_liked_count": len(self.deleted.liked_intersect),
                "deleted_disliked_count": len(self.deleted.disliked_intersect),
            },
        }

    def filtering_recommendations(self) -> dict[str, Any]:
        """Generate filtering policy recommendations based on the data."""
        stats = self.summary_stats()
        recommendations = {
            "must_block": [],
            "strong_negative_signals": [],
            "soft_score_signals": [],
            "signals_too_weak": [],
        }

        # User feedback is the strongest signal
        if (
            stats["user_feedback"]["deleted_disliked_count"]
            > stats["user_feedback"]["main_disliked_count"]
        ):
            recommendations["must_block"].append("YM user dislikes")

        # Check if missing features is a strong signal
        deleted_missing_rate = (
            len(self.deleted.tracks_without_features) / self.deleted.track_count
        ) * 100
        main_missing_rate = (len(self.main.tracks_without_features) / self.main.track_count) * 100

        if deleted_missing_rate > main_missing_rate + 10:
            recommendations["strong_negative_signals"].append("Missing audio features")
        elif deleted_missing_rate > main_missing_rate + 5:
            recommendations["soft_score_signals"].append(
                "Missing audio features (moderate penalty)"
            )
        else:
            recommendations["signals_too_weak"].append(
                "Missing audio features (insufficient signal)"
            )

        # Metadata year signal
        if (
            stats["metadata_signals"]["main_median_year"]
            and stats["metadata_signals"]["deleted_median_year"]
        ):
            year_diff = (
                stats["metadata_signals"]["main_median_year"]
                - stats["metadata_signals"]["deleted_median_year"]
            )
            if year_diff >= 2:
                recommendations["soft_score_signals"].append(
                    f"Album year (prefer newer, ~{year_diff} year bias)"
                )
            else:
                recommendations["signals_too_weak"].append("Album year (weak signal)")

        # Compilation signal
        comp_diff = (
            stats["metadata_signals"]["main_compilation_rate"]
            - stats["metadata_signals"]["deleted_compilation_rate"]
        )
        if comp_diff < -10:
            recommendations["soft_score_signals"].append("Compilation albums (moderate negative)")
        elif comp_diff < -5:
            recommendations["soft_score_signals"].append("Compilation albums (weak negative)")
        else:
            recommendations["signals_too_weak"].append("Compilation albums (insufficient signal)")

        return recommendations


class YmApi:
    """Minimal YM API client for playlist fetching."""

    def __init__(self, token: str):
        self.token = token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def get(self, url: str) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.get(url, headers={"Authorization": f"OAuth {self.token}"})
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


async def fetch_playlist_tracks(api: YmApi, user_id: str, kind: str) -> tuple[str, list[str]]:
    """Fetch playlist name and track IDs."""
    url = f"https://api.music.yandex.net/users/{user_id}/playlists/{kind}"
    data = await api.get(url)
    result = data.get("result", data)

    name = result.get("title", f"Playlist {kind}")
    tracks = result.get("tracks", [])
    track_ids = []

    for item in tracks:
        track = item.get("track", item)
        if track_id := track.get("id"):
            track_ids.append(str(track_id))

    return name, track_ids


async def get_user_feedback(api: YmApi, user_id: str) -> tuple[set[str], set[str]]:
    """Get user's liked and disliked track IDs."""
    liked_ids: set[str] = set()
    disliked_ids: set[str] = set()

    try:
        # Liked tracks
        data = await api.get(f"https://api.music.yandex.net/users/{user_id}/likes/tracks")
        result = data.get("result", data)
        lib = result.get("library", result)
        tracks = lib.get("tracks", [])
        for t in tracks:
            if track_id := t.get("id"):
                liked_ids.add(str(track_id))
    except Exception as e:
        print(f"Could not fetch likes: {e}")

    try:
        # Disliked tracks
        data = await api.get(f"https://api.music.yandex.net/users/{user_id}/dislikes/tracks")
        result = data.get("result", data)
        lib = result.get("library", result)
        tracks = lib.get("tracks", [])
        for t in tracks:
            if track_id := t.get("id"):
                disliked_ids.add(str(track_id))
    except Exception as e:
        print(f"Could not fetch dislikes: {e}")

    return liked_ids, disliked_ids


async def analyze_playlist(
    playlist: PlaylistAnalysis, liked_ids: set[str], disliked_ids: set[str]
) -> None:
    """Analyze a playlist's tracks against local DB and user feedback."""

    # Map YM track IDs to local track IDs
    async with session_factory() as session:
        for ym_id in playlist.ym_track_ids:
            row = await session.execute(
                select(ProviderTrackId.track_id).where(ProviderTrackId.provider_track_id == ym_id)
            )
            if track_id := row.scalar():
                playlist.local_track_ids.append(track_id)

    print(
        f"  {playlist.name}: {len(playlist.local_track_ids)}/"
        f"{len(playlist.ym_track_ids)} tracks in local DB"
    )

    # Check file presence and features
    for track_id in playlist.local_track_ids:
        async with session_factory() as session:
            # Check if file exists
            file_row = await session.execute(
                text("SELECT file_path FROM dj_library_items WHERE track_id = :tid"),
                {"tid": track_id},
            )
            if (file_path := file_row.scalar()) and Path(file_path).exists():
                playlist.tracks_with_files += 1

            # Check for computed features
            feat_row = await session.execute(
                select(TrackAudioFeaturesComputed).where(
                    TrackAudioFeaturesComputed.track_id == track_id
                )
            )
            if feat := feat_row.scalars().first():
                playlist.tracks_with_features += 1
                playlist.bpm_values.append(feat.bpm)
                playlist.lufs_values.append(feat.lufs_i)
                if feat.energy_mean is not None:
                    playlist.energy_values.append(feat.energy_mean)

            # Get metadata
            meta_row = await session.execute(
                select(YandexMetadata).where(YandexMetadata.track_id == track_id)
            )
            if meta := meta_row.scalars().first():
                if meta.album_year:
                    playlist.album_years.append(meta.album_year)

                # Detect compilation-like albums
                if meta.album_title and any(
                    word in meta.album_title.lower()
                    for word in ["compilation", "best", "hits", "collection", "various", "mixed"]
                ):
                    playlist.compilation_like_count += 1

    # Find tracks without features
    for ym_id in playlist.ym_track_ids:
        if ym_id not in [str(tid) for tid in playlist.local_track_ids]:
            continue

        # Find local track ID
        async with session_factory() as session:
            row = await session.execute(
                select(ProviderTrackId.track_id).where(ProviderTrackId.provider_track_id == ym_id)
            )
            if not (track_id := row.scalar()):
                continue

            feat_row = await session.execute(
                select(TrackAudioFeaturesComputed.track_id).where(
                    TrackAudioFeaturesComputed.track_id == track_id
                )
            )
            if not feat_row.scalar():
                playlist.tracks_without_features.append(ym_id)

    # Check user feedback intersection
    playlist.liked_intersect = set(playlist.ym_track_ids) & liked_ids
    playlist.disliked_intersect = set(playlist.ym_track_ids) & disliked_ids

    print(
        f"  {playlist.name}: {playlist.tracks_with_files} have files, "
        f"{playlist.tracks_with_features} have features"
    )
    print(f"  {playlist.name}: {len(playlist.tracks_without_features)} missing features")
    print(
        f"  {playlist.name}: {len(playlist.liked_intersect)} liked, "
        f"{len(playlist.disliked_intersect)} disliked"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze playlist pair for filtering insights")
    parser.add_argument("--main-kind", required=True, help="Main playlist kind ID")
    parser.add_argument("--deleted-kind", required=True, help="Deleted playlist kind ID")
    parser.add_argument(
        "--user-id", default=settings.yandex_music_user_id or "250905515", help="YM user ID"
    )
    parser.add_argument(
        "--output-report", action="store_true", help="Write analysis report to file"
    )
    args = parser.parse_args()

    if not settings.yandex_music_token:
        raise RuntimeError("YANDEX_MUSIC_TOKEN not set")

    await init_db()

    api = YmApi(settings.yandex_music_token)

    try:
        print("Fetching playlists...")
        main_name, main_tracks = await fetch_playlist_tracks(api, args.user_id, args.main_kind)
        deleted_name, deleted_tracks = await fetch_playlist_tracks(
            api, args.user_id, args.deleted_kind
        )

        print(f"Main playlist '{main_name}': {len(main_tracks)} tracks")
        print(f"Deleted playlist '{deleted_name}': {len(deleted_tracks)} tracks")

        print("\nFetching user feedback...")
        liked_ids, disliked_ids = await get_user_feedback(api, args.user_id)
        print(f"User has {len(liked_ids)} likes, {len(disliked_ids)} dislikes")

        # Initialize analysis objects
        main_analysis = PlaylistAnalysis(
            kind=args.main_kind,
            name=main_name,
            track_count=len(main_tracks),
            ym_track_ids=main_tracks,
        )

        deleted_analysis = PlaylistAnalysis(
            kind=args.deleted_kind,
            name=deleted_name,
            track_count=len(deleted_tracks),
            ym_track_ids=deleted_tracks,
        )

        print("\nAnalyzing main playlist...")
        await analyze_playlist(main_analysis, liked_ids, disliked_ids)

        print("\nAnalyzing deleted playlist...")
        await analyze_playlist(deleted_analysis, liked_ids, disliked_ids)

        # Generate report
        report = ComparisonReport(main=main_analysis, deleted=deleted_analysis)
        stats = report.summary_stats()
        recommendations = report.filtering_recommendations()

        print(f"\n{'=' * 60}")
        print("PLAYLIST PAIR ANALYSIS RESULTS")
        print(f"{'=' * 60}")

        print("\nTRACK COUNTS:")
        print(f"  Main: {stats['track_counts']['main']} tracks")
        print(f"  Deleted: {stats['track_counts']['deleted']} tracks")

        print("\nFEATURE COVERAGE:")
        main_features = stats["feature_coverage"]["main_with_features"]
        main_pct = stats["feature_coverage"]["main_percentage"]
        print(f"  Main: {main_features} ({main_pct}%)")
        deleted_features = stats["feature_coverage"]["deleted_with_features"]
        deleted_pct = stats["feature_coverage"]["deleted_percentage"]
        print(f"  Deleted: {deleted_features} ({deleted_pct}%)")

        if (
            stats["audio_features"]["main_median_bpm"]
            and stats["audio_features"]["deleted_median_bpm"]
        ):
            print("\nAUDIO FEATURES:")
            print(f"  Main median BPM: {stats['audio_features']['main_median_bpm']:.1f}")
            print(f"  Deleted median BPM: {stats['audio_features']['deleted_median_bpm']:.1f}")
            print(f"  Main median LUFS: {stats['audio_features']['main_median_lufs']:.1f}")
            print(f"  Deleted median LUFS: {stats['audio_features']['deleted_median_lufs']:.1f}")

        print("\nMETADATA SIGNALS:")
        if stats["metadata_signals"]["main_median_year"]:
            print(f"  Main median year: {stats['metadata_signals']['main_median_year']}")
            print(f"  Deleted median year: {stats['metadata_signals']['deleted_median_year']}")
        print(
            f"  Main compilation rate: {stats['metadata_signals']['main_compilation_rate']:.1f}%"
        )
        deleted_comp_rate = stats["metadata_signals"]["deleted_compilation_rate"]
        print(f"  Deleted compilation rate: {deleted_comp_rate:.1f}%")

        print("\nUSER FEEDBACK:")
        print(f"  Main liked: {stats['user_feedback']['main_liked_count']}")
        print(f"  Main disliked: {stats['user_feedback']['main_disliked_count']}")
        print(f"  Deleted liked: {stats['user_feedback']['deleted_liked_count']}")
        print(f"  Deleted disliked: {stats['user_feedback']['deleted_disliked_count']}")

        print(f"\n{'=' * 60}")
        print("FILTERING POLICY RECOMMENDATIONS")
        print(f"{'=' * 60}")

        for category, signals in recommendations.items():
            if signals:
                print(f"\n{category.replace('_', ' ').upper()}:")
                for signal in signals:
                    print(f"  • {signal}")

        # Write report file if requested
        if args.output_report:
            report_data = {
                "analysis_metadata": {
                    "main_playlist_kind": args.main_kind,
                    "deleted_playlist_kind": args.deleted_kind,
                    "user_id": args.user_id,
                },
                "summary_stats": stats,
                "filtering_recommendations": recommendations,
                "raw_data": {
                    "main_without_features": main_analysis.tracks_without_features,
                    "deleted_without_features": deleted_analysis.tracks_without_features,
                },
            }

            report_path = f"playlist_pair_analysis_{args.main_kind}_{args.deleted_kind}.json"
            with open(report_path, "w") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)

            print(f"\nDetailed report written to: {report_path}")

    finally:
        await api.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
