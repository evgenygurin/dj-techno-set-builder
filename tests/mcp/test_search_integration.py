"""Integration tests for search + filter_tracks tools with real DB.

These tests seed data into an in-memory SQLite via the test session,
then invoke MCP tools via Client to verify end-to-end behavior
including DI, entity resolution, and response envelope structure.
"""

from __future__ import annotations

import json

from fastmcp import Client

from app.core.models.catalog import Track
from app.core.models.dj import DjPlaylist
from app.core.models.features import TrackAudioFeaturesComputed
from app.core.models.harmony import Key
from app.core.models.runs import FeatureExtractionRun
from app.core.models.sets import DjSet


async def _seed_keys(session) -> None:
    """Seed the keys lookup table (required FK for audio features)."""
    for kc in range(24):
        pitch_class = kc // 2
        mode = kc % 2
        name = f"key_{kc}"
        await session.merge(Key(key_code=kc, pitch_class=pitch_class, mode=mode, name=name))
    await session.flush()


async def _seed_tracks(session) -> dict[str, int]:
    """Seed tracks + playlists + sets for search tests. Returns track IDs."""
    t1 = Track(title="Gravity", title_sort="gravity", duration_ms=360000, status=0)
    t2 = Track(title="Space Motion", title_sort="space motion", duration_ms=300000, status=0)
    t3 = Track(title="Dark Gravity", title_sort="dark gravity", duration_ms=400000, status=0)
    session.add_all([t1, t2, t3])

    pl = DjPlaylist(name="My Gravity playlist")
    session.add(pl)

    s = DjSet(name="Gravity Live Set")
    session.add(s)

    await session.flush()
    return {"t1": t1.track_id, "t2": t2.track_id, "t3": t3.track_id}


def _make_features(track_id: int, run_id: int, **overrides) -> TrackAudioFeaturesComputed:
    """Build a TrackAudioFeaturesComputed with sensible defaults for all NOT NULL fields."""
    defaults = {
        "track_id": track_id,
        "run_id": run_id,
        "bpm": 140.0,
        "tempo_confidence": 0.9,
        "bpm_stability": 0.95,
        "is_variable_tempo": False,
        "lufs_i": -8.0,
        "rms_dbfs": -10.0,
        "energy_mean": 0.5,
        "energy_max": 0.8,
        "energy_std": 0.1,
        "key_code": 0,
        "key_confidence": 0.85,
        "is_atonal": False,
    }
    defaults.update(overrides)
    return TrackAudioFeaturesComputed(**defaults)


async def _seed_features(session, track_ids: dict[str, int]) -> None:
    """Seed audio features for tracks."""
    await _seed_keys(session)

    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0", status="completed")
    session.add(run)
    await session.flush()

    # t1: Gravity — 140 BPM, Em (key_code=8), energy_mean=0.5
    f1 = _make_features(
        track_ids["t1"],
        run.run_id,
        bpm=140.0,
        key_code=8,
        lufs_i=-8.3,
        energy_mean=0.5,
    )
    # t2: Space Motion — 138 BPM, Am (key_code=18), energy_mean=0.7
    f2 = _make_features(
        track_ids["t2"],
        run.run_id,
        bpm=138.0,
        key_code=18,
        lufs_i=-6.0,
        energy_mean=0.7,
    )
    # t3: Dark Gravity — 145 BPM, Cm (key_code=0), energy_mean=0.2
    f3 = _make_features(
        track_ids["t3"],
        run.run_id,
        bpm=145.0,
        key_code=0,
        lufs_i=-10.5,
        energy_mean=0.2,
    )
    session.add_all([f1, f2, f3])
    await session.flush()


def _parse_response(result) -> dict:
    """Parse JSON text content from MCP tool result."""
    return json.loads(result.content[0].text)


async def test_search_finds_tracks_by_title(workflow_mcp_with_db, session):
    """search tool finds tracks matching the query text."""
    await _seed_tracks(session)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "Gravity"})
        assert not result.is_error
        data = _parse_response(result)

        # Should have tracks category with at least 2 matches
        assert "tracks" in data["results"]
        track_titles = [t["title"] for t in data["results"]["tracks"]]
        assert "Gravity" in track_titles
        assert "Dark Gravity" in track_titles

        # Library stats should be present (>= because session-scoped engine may have data)
        assert data["library"]["total_tracks"] >= 3

        # Pagination should be present
        assert "limit" in data["pagination"]
        assert data["pagination"]["has_more"] is False


async def test_search_scoped_to_tracks(workflow_mcp_with_db, session):
    """search with scope=tracks returns only tracks category."""
    await _seed_tracks(session)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "Gravity", "scope": "tracks"})
        data = _parse_response(result)
        assert "tracks" in data["results"]
        assert "playlists" not in data["results"]
        assert "sets" not in data["results"]


async def test_search_finds_playlists(workflow_mcp_with_db, session):
    """search finds playlists matching the query."""
    await _seed_tracks(session)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "Gravity", "scope": "playlists"})
        data = _parse_response(result)
        assert "playlists" in data["results"]
        assert len(data["results"]["playlists"]) >= 1
        assert data["results"]["playlists"][0]["name"] == "My Gravity playlist"


async def test_search_finds_sets(workflow_mcp_with_db, session):
    """search finds DJ sets matching the query."""
    await _seed_tracks(session)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "Gravity", "scope": "sets"})
        data = _parse_response(result)
        assert "sets" in data["results"]
        assert len(data["results"]["sets"]) >= 1
        assert data["results"]["sets"][0]["name"] == "Gravity Live Set"


async def test_search_no_results(workflow_mcp_with_db, session):
    """search returns empty results for non-matching query."""
    await _seed_tracks(session)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "zzz_nonexistent_zzz"})
        data = _parse_response(result)
        assert data["stats"]["total_matches"]["tracks"] == 0


async def test_filter_tracks_by_bpm(workflow_mcp_with_db, session):
    """filter_tracks returns tracks within BPM range."""
    track_ids = await _seed_tracks(session)
    await _seed_features(session, track_ids)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool(
            "filter_tracks",
            {"bpm_min": 139.0, "bpm_max": 141.0},
        )
        assert not result.is_error
        data = _parse_response(result)

        # Phase 2 filter_tracks returns EntityListResponse (flat results list)
        tracks = data["results"]
        assert len(tracks) == 1
        assert tracks[0]["bpm"] == 140.0
        assert tracks[0]["title"] == "Gravity"


async def test_filter_tracks_by_key_code(workflow_mcp_with_db, session):
    """filter_tracks returns tracks matching key code range."""
    track_ids = await _seed_tracks(session)
    await _seed_features(session, track_ids)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        # key_code 8 = Em, key_code 18 = Am
        result = await client.call_tool(
            "filter_tracks",
            {"key_code_min": 8, "key_code_max": 18},
        )
        data = _parse_response(result)
        tracks = data["results"]
        # Should include t1 (key_code=8) and t2 (key_code=18)
        assert len(tracks) == 2


async def test_filter_tracks_by_energy(workflow_mcp_with_db, session):
    """filter_tracks returns tracks within energy_mean range (0.0-1.0)."""
    track_ids = await _seed_tracks(session)
    await _seed_features(session, track_ids)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool(
            "filter_tracks",
            {"energy_min": 0.4, "energy_max": 0.8},
        )
        data = _parse_response(result)
        tracks = data["results"]
        # t1: energy_mean=0.5 (within), t2: 0.7 (within), t3: 0.2 (below)
        assert len(tracks) == 2


async def test_filter_tracks_no_criteria_returns_all(workflow_mcp_with_db, session):
    """filter_tracks with no criteria returns all analyzed tracks."""
    track_ids = await _seed_tracks(session)
    await _seed_features(session, track_ids)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool("filter_tracks", {})
        data = _parse_response(result)
        tracks = data["results"]
        assert len(tracks) == 3


async def test_filter_tracks_library_stats(workflow_mcp_with_db, session):
    """filter_tracks includes accurate library stats."""
    track_ids = await _seed_tracks(session)
    await _seed_features(session, track_ids)
    await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool("filter_tracks", {})
        data = _parse_response(result)
        assert data["library"]["total_tracks"] >= 3
        assert data["library"]["analyzed_tracks"] >= 3
        assert data["library"]["total_playlists"] >= 1
        assert data["library"]["total_sets"] >= 1
