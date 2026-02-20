"""Tests for v2 response models — summary/detail/full + stats + pagination."""

from __future__ import annotations

from app.mcp.types_v2 import (
    ArtistSummary,
    FindResult,
    LibraryStats,
    MatchStats,
    PaginationInfo,
    PlaylistSummary,
    SearchResponse,
    SetSummary,
    TrackDetail,
    TrackSummary,
)


class TestTrackSummary:
    def test_create_minimal(self):
        t = TrackSummary(ref="local:42", title="Gravity", artist="Boris Brejcha")
        assert t.ref == "local:42"
        assert t.bpm is None

    def test_create_full(self):
        t = TrackSummary(
            ref="local:42",
            title="Gravity",
            artist="Boris Brejcha",
            bpm=140.0,
            key="5A",
            energy_lufs=-8.3,
            duration_ms=360000,
            mood="peak_time",
            match_score=0.95,
        )
        assert t.bpm == 140.0
        assert t.match_score == 0.95


class TestTrackDetail:
    def test_extends_summary(self):
        d = TrackDetail(
            ref="local:42",
            title="Gravity",
            artist="Boris Brejcha",
            bpm=140.0,
            has_features=True,
            genres=["Techno"],
            labels=["Fckng Serious"],
            albums=["Gravity EP"],
            sections_count=5,
            platform_ids={"ym": "12345"},
        )
        assert d.has_features is True
        assert d.platform_ids["ym"] == "12345"


class TestPlaylistSummary:
    def test_create(self):
        p = PlaylistSummary(ref="local:5", name="Techno develop", track_count=247)
        assert p.track_count == 247


class TestSetSummary:
    def test_create(self):
        s = SetSummary(
            ref="local:3", name="Friday night", version_count=2, track_count=15
        )
        assert s.version_count == 2


class TestArtistSummary:
    def test_create(self):
        a = ArtistSummary(ref="local:10", name="Boris Brejcha", tracks_in_db=5)
        assert a.tracks_in_db == 5


class TestSearchResponse:
    def test_empty_search(self):
        r = SearchResponse(
            results={},
            stats=MatchStats(total_matches={}, match_profile={}),
            library=LibraryStats(
                total_tracks=0,
                analyzed_tracks=0,
                total_playlists=0,
                total_sets=0,
            ),
            pagination=PaginationInfo(limit=20, has_more=False),
        )
        assert r.library.total_tracks == 0

    def test_search_with_results(self):
        r = SearchResponse(
            results={
                "tracks": [
                    TrackSummary(
                        ref="local:42",
                        title="Gravity",
                        artist="Boris Brejcha",
                        match_score=0.95,
                    )
                ]
            },
            stats=MatchStats(
                total_matches={"tracks": 23, "ym_tracks": 156},
                match_profile={"bpm_range": [128, 142]},
            ),
            library=LibraryStats(
                total_tracks=3247,
                analyzed_tracks=2890,
                total_playlists=15,
                total_sets=8,
            ),
            pagination=PaginationInfo(limit=20, has_more=True, cursor="abc"),
        )
        assert r.stats.total_matches["tracks"] == 23
        assert r.pagination.has_more is True


class TestFindResult:
    def test_exact(self):
        r = FindResult(
            exact=True,
            entities=[TrackSummary(ref="local:42", title="X", artist="Y")],
            source="local",
        )
        assert r.exact is True
        assert len(r.entities) == 1

    def test_fuzzy(self):
        r = FindResult(
            exact=False,
            entities=[
                TrackSummary(ref="local:42", title="X", artist="Y", match_score=0.9),
                TrackSummary(ref="local:43", title="Z", artist="Y", match_score=0.7),
            ],
            source="local",
        )
        assert len(r.entities) == 2
