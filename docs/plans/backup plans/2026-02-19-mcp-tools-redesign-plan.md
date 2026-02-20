# MCP Tools Redesign — Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the foundational layer for the agent-first MCP redesign: EntityFinder (URN refs), response shaping (summary/detail/full + stats), universal search, and cursor-based pagination.

**Architecture:** New modules (`app/mcp/refs.py`, `app/mcp/entity_finder.py`, `app/mcp/pagination.py`, `app/mcp/types_v2.py`) sit alongside existing code. No breaking changes — new tools added, old tools untouched until Phase 2.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest

**Design doc:** `docs/plans/2026-02-19-mcp-tools-redesign-design.md`

---

## Task 1: Response Models (`types_v2.py`)

**Files:**
- Create: `app/mcp/types_v2.py`
- Test: `tests/mcp/test_types_v2.py`

These Pydantic models define the three response levels (summary/detail/full) and the universal response envelope with stats + pagination.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_types_v2.py
from app.mcp.types_v2 import (
    TrackSummary,
    TrackDetail,
    PlaylistSummary,
    SetSummary,
    ArtistSummary,
    LibraryStats,
    MatchStats,
    PaginationInfo,
    SearchResponse,
    FindResult,
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
        p = PlaylistSummary(
            ref="local:5", name="Techno develop", track_count=247
        )
        assert p.track_count == 247

class TestSetSummary:
    def test_create(self):
        s = SetSummary(
            ref="local:3", name="Friday night", version_count=2, track_count=15
        )
        assert s.version_count == 2

class TestArtistSummary:
    def test_create(self):
        a = ArtistSummary(
            ref="local:10", name="Boris Brejcha", tracks_in_db=5
        )
        assert a.tracks_in_db == 5

class TestSearchResponse:
    def test_empty_search(self):
        r = SearchResponse(
            results={},
            stats=MatchStats(
                total_matches={}, match_profile={}
            ),
            library=LibraryStats(
                total_tracks=0, analyzed_tracks=0,
                total_playlists=0, total_sets=0,
            ),
            pagination=PaginationInfo(limit=20, has_more=False),
        )
        assert r.library.total_tracks == 0

    def test_search_with_results(self):
        r = SearchResponse(
            results={
                "tracks": [
                    TrackSummary(
                        ref="local:42", title="Gravity",
                        artist="Boris Brejcha", match_score=0.95,
                    )
                ]
            },
            stats=MatchStats(
                total_matches={"tracks": 23, "ym_tracks": 156},
                match_profile={"bpm_range": [128, 142]},
            ),
            library=LibraryStats(
                total_tracks=3247, analyzed_tracks=2890,
                total_playlists=15, total_sets=8,
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_types_v2.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.mcp.types_v2'`

**Step 3: Implement response models**

```python
# app/mcp/types_v2.py
"""Response models for MCP tools redesign (Phase 1).

Three response levels:
- Summary (~150 bytes/entity) — for lists, search results
- Detail (~300 bytes/entity) — for single entity views
- Full (~2 KB/entity) — for audio namespace, explicit requests

All tools return responses with: results + stats + pagination.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# --- Entity Summaries (Level 1: ~150 bytes each) ---

class TrackSummary(BaseModel):
    """Minimal track info for lists and search results."""

    ref: str
    title: str
    artist: str
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None
    duration_ms: int | None = None
    mood: str | None = None
    match_score: float | None = Field(None, ge=0, le=1)

class PlaylistSummary(BaseModel):
    """Minimal playlist info."""

    ref: str
    name: str
    track_count: int = 0
    analyzed_count: int | None = None
    match_score: float | None = Field(None, ge=0, le=1)

class SetSummary(BaseModel):
    """Minimal set info."""

    ref: str
    name: str
    version_count: int = 0
    track_count: int = 0
    avg_score: float | None = None
    match_score: float | None = Field(None, ge=0, le=1)

class ArtistSummary(BaseModel):
    """Minimal artist info."""

    ref: str
    name: str
    tracks_in_db: int = 0
    match_score: float | None = Field(None, ge=0, le=1)

# --- Entity Details (Level 2: ~300 bytes each) ---

class TrackDetail(TrackSummary):
    """Extended track info — single entity view."""

    has_features: bool = False
    genres: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    albums: list[str] = Field(default_factory=list)
    sections_count: int = 0
    platform_ids: dict[str, str] = Field(default_factory=dict)

# --- Response Envelope ---

class PaginationInfo(BaseModel):
    """Cursor-based pagination metadata."""

    limit: int
    has_more: bool
    cursor: str | None = None

class MatchStats(BaseModel):
    """Background statistics — total counts, not data."""

    total_matches: dict[str, int] = Field(default_factory=dict)
    match_profile: dict[str, Any] = Field(default_factory=dict)

class LibraryStats(BaseModel):
    """Library-wide context."""

    total_tracks: int
    analyzed_tracks: int
    total_playlists: int
    total_sets: int

class SearchResponse(BaseModel):
    """Universal search response with categorized results + stats."""

    results: dict[str, list[Any]]
    stats: MatchStats
    library: LibraryStats
    pagination: PaginationInfo

class FindResult(BaseModel):
    """Entity resolution result."""

    exact: bool
    entities: list[Any]
    source: str
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_types_v2.py -v`
Expected: ALL PASS

**Step 5: Lint**

Run: `uv run ruff check app/mcp/types_v2.py tests/mcp/test_types_v2.py && uv run mypy app/mcp/types_v2.py`

**Step 6: Commit**

```bash
git add app/mcp/types_v2.py tests/mcp/test_types_v2.py
git commit -m "feat(mcp): add v2 response models — summary/detail/full + stats + pagination"
```

---

## Task 2: Pagination Codec (`pagination.py`)

**Files:**
- Create: `app/mcp/pagination.py`
- Test: `tests/mcp/test_pagination_codec.py`

Cursor encoding/decoding for offset-based pagination. Cursor = base64-encoded JSON `{"offset": N}`.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_pagination_codec.py
import pytest

from app.mcp.pagination import encode_cursor, decode_cursor, paginate_params

class TestCursorCodec:
    def test_encode_decode_roundtrip(self):
        cursor = encode_cursor(offset=50)
        assert isinstance(cursor, str)
        params = decode_cursor(cursor)
        assert params["offset"] == 50

    def test_decode_none_returns_defaults(self):
        params = decode_cursor(None)
        assert params["offset"] == 0

    def test_decode_invalid_returns_defaults(self):
        params = decode_cursor("not-valid-base64!")
        assert params["offset"] == 0

    def test_decode_empty_string_returns_defaults(self):
        params = decode_cursor("")
        assert params["offset"] == 0

class TestPaginateParams:
    def test_no_cursor(self):
        offset, limit = paginate_params(cursor=None, limit=20)
        assert offset == 0
        assert limit == 20

    def test_with_cursor(self):
        cursor = encode_cursor(offset=40)
        offset, limit = paginate_params(cursor=cursor, limit=20)
        assert offset == 40
        assert limit == 20

    def test_limit_clamped(self):
        offset, limit = paginate_params(cursor=None, limit=500)
        assert limit == 100  # max limit

    def test_limit_minimum(self):
        offset, limit = paginate_params(cursor=None, limit=0)
        assert limit == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_pagination_codec.py -v`
Expected: FAIL

**Step 3: Implement pagination codec**

```python
# app/mcp/pagination.py
"""Cursor-based pagination utilities.

Cursor = base64(JSON{"offset": N}). Simple, stateless, no DB dependency.
"""

from __future__ import annotations

import base64
import json

MAX_LIMIT = 100
MIN_LIMIT = 1

def encode_cursor(*, offset: int) -> str:
    """Encode pagination state into an opaque cursor string."""
    payload = json.dumps({"offset": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()

def decode_cursor(cursor: str | None) -> dict[str, int]:
    """Decode cursor back to pagination state. Returns defaults on any error."""
    if not cursor:
        return {"offset": 0}
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(payload)
        return {"offset": max(0, int(data.get("offset", 0)))}
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return {"offset": 0}

def paginate_params(
    *, cursor: str | None = None, limit: int = 20
) -> tuple[int, int]:
    """Return (offset, clamped_limit) from cursor + limit."""
    params = decode_cursor(cursor)
    clamped = max(MIN_LIMIT, min(limit, MAX_LIMIT))
    return params["offset"], clamped
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_pagination_codec.py -v`
Expected: ALL PASS

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/pagination.py tests/mcp/test_pagination_codec.py
git add app/mcp/pagination.py tests/mcp/test_pagination_codec.py
git commit -m "feat(mcp): add cursor-based pagination codec"
```

---

## Task 3: Ref Parser (`refs.py`)

**Files:**
- Create: `app/mcp/refs.py`
- Test: `tests/mcp/test_refs.py`

Parses URN-style refs: `"local:42"`, `"ym:12345"`, `42`, `"Boris Brejcha"`.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_refs.py
import pytest

from app.mcp.refs import parse_ref, ParsedRef, RefType

class TestParseRef:
    def test_local_id_with_prefix(self):
        r = parse_ref("local:42")
        assert r.ref_type == RefType.LOCAL
        assert r.local_id == 42
        assert r.source == "local"

    def test_bare_integer(self):
        r = parse_ref("42")
        assert r.ref_type == RefType.LOCAL
        assert r.local_id == 42

    def test_integer_input(self):
        r = parse_ref(42)
        assert r.ref_type == RefType.LOCAL
        assert r.local_id == 42

    def test_platform_ym(self):
        r = parse_ref("ym:12345")
        assert r.ref_type == RefType.PLATFORM
        assert r.source == "ym"
        assert r.platform_id == "12345"

    def test_platform_spotify(self):
        r = parse_ref("spotify:abc123")
        assert r.ref_type == RefType.PLATFORM
        assert r.source == "spotify"
        assert r.platform_id == "abc123"

    def test_text_query(self):
        r = parse_ref("Boris Brejcha")
        assert r.ref_type == RefType.TEXT
        assert r.query == "Boris Brejcha"

    def test_text_with_dash(self):
        r = parse_ref("Boris Brejcha - Gravity")
        assert r.ref_type == RefType.TEXT
        assert r.query == "Boris Brejcha - Gravity"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_ref("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_ref("   ")

    def test_known_platforms(self):
        """Only known platform prefixes are treated as URN, not random words."""
        r = parse_ref("beatport:67890")
        assert r.ref_type == RefType.PLATFORM
        assert r.source == "beatport"

    def test_unknown_prefix_treated_as_text(self):
        """'genre:techno' is NOT a platform ref — treated as text query."""
        r = parse_ref("genre:techno")
        assert r.ref_type == RefType.TEXT
        assert r.query == "genre:techno"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_refs.py -v`
Expected: FAIL

**Step 3: Implement ref parser**

```python
# app/mcp/refs.py
"""Entity reference parser.

Parses URN-style refs into structured ParsedRef:
  "local:42"            → LOCAL, id=42
  "ym:12345"            → PLATFORM, source="ym", platform_id="12345"
  42                    → LOCAL, id=42
  "Boris Brejcha"       → TEXT, query="Boris Brejcha"
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

KNOWN_PLATFORMS = frozenset({"local", "ym", "spotify", "beatport", "soundcloud"})

class RefType(StrEnum):
    LOCAL = "local"
    PLATFORM = "platform"
    TEXT = "text"

@dataclass(frozen=True)
class ParsedRef:
    ref_type: RefType
    source: str = ""
    local_id: int | None = None
    platform_id: str | None = None
    query: str | None = None

def parse_ref(ref: str | int) -> ParsedRef:
    """Parse an entity reference string into a structured ParsedRef."""
    if isinstance(ref, int):
        return ParsedRef(ref_type=RefType.LOCAL, source="local", local_id=ref)

    ref = str(ref).strip()
    if not ref:
        msg = "Entity ref cannot be empty"
        raise ValueError(msg)

    # Bare integer: "42"
    try:
        return ParsedRef(ref_type=RefType.LOCAL, source="local", local_id=int(ref))
    except ValueError:
        pass

    # URN format: "source:id"
    if ":" in ref:
        prefix, _, suffix = ref.partition(":")
        if prefix.lower() in KNOWN_PLATFORMS and suffix:
            if prefix.lower() == "local":
                try:
                    return ParsedRef(
                        ref_type=RefType.LOCAL, source="local", local_id=int(suffix)
                    )
                except ValueError:
                    pass
            else:
                return ParsedRef(
                    ref_type=RefType.PLATFORM,
                    source=prefix.lower(),
                    platform_id=suffix,
                )

    # Everything else: text query for fuzzy search
    return ParsedRef(ref_type=RefType.TEXT, query=ref)
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_refs.py -v`
Expected: ALL PASS

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/refs.py tests/mcp/test_refs.py && uv run mypy app/mcp/refs.py
git add app/mcp/refs.py tests/mcp/test_refs.py
git commit -m "feat(mcp): add URN ref parser — local/platform/text resolution"
```

---

## Task 4: EntityFinder — Core + TrackFinder

**Files:**
- Create: `app/mcp/entity_finder.py`
- Test: `tests/mcp/test_entity_finder.py`

EntityFinder resolves `*_ref` parameters. Delegates to entity-specific finders.
TrackFinder = first concrete implementation (DB fuzzy + artist join).

**Step 1: Write the failing tests**

```python
# tests/mcp/test_entity_finder.py
"""Tests for EntityFinder — ref resolution to entity lookups."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.entity_finder import TrackFinder
from app.mcp.refs import RefType, parse_ref
from app.mcp.types_v2 import FindResult

@pytest.fixture
def mock_track_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.search_by_title = AsyncMock(return_value=([], 0))
    return repo

@pytest.fixture
def mock_artist_repo():
    repo = AsyncMock()
    repo.search_by_name = AsyncMock(return_value=([], 0))
    return repo

@pytest.fixture
def mock_track_svc():
    """Mock TrackRepository with get_artists_for_tracks."""
    repo = AsyncMock()
    repo.get_artists_for_tracks = AsyncMock(return_value={})
    return repo

class TestTrackFinder:
    async def test_find_by_local_id_found(self, mock_track_repo, mock_track_svc):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000
        mock_track_repo.get_by_id = AsyncMock(return_value=track)
        mock_track_svc.get_artists_for_tracks = AsyncMock(
            return_value={42: ["Boris Brejcha"]}
        )

        finder = TrackFinder(mock_track_repo, mock_track_svc)
        ref = parse_ref("local:42")
        result = await finder.find(ref)

        assert isinstance(result, FindResult)
        assert result.exact is True
        assert len(result.entities) == 1
        assert result.entities[0].ref == "local:42"
        assert result.entities[0].title == "Gravity"
        assert result.entities[0].artist == "Boris Brejcha"

    async def test_find_by_local_id_not_found(self, mock_track_repo, mock_track_svc):
        finder = TrackFinder(mock_track_repo, mock_track_svc)
        ref = parse_ref("local:999")
        result = await finder.find(ref)

        assert result.exact is True
        assert len(result.entities) == 0

    async def test_find_by_text_query(self, mock_track_repo, mock_track_svc):
        track1 = MagicMock()
        track1.track_id = 42
        track1.title = "Boris Brejcha - Gravity"
        track1.duration_ms = 360000
        track2 = MagicMock()
        track2.track_id = 43
        track2.title = "Boris Brejcha - Butterfly Effect"
        track2.duration_ms = 300000

        mock_track_repo.search_by_title = AsyncMock(
            return_value=([track1, track2], 2)
        )
        mock_track_svc.get_artists_for_tracks = AsyncMock(
            return_value={42: ["Boris Brejcha"], 43: ["Boris Brejcha"]}
        )

        finder = TrackFinder(mock_track_repo, mock_track_svc)
        ref = parse_ref("Boris Brejcha")
        result = await finder.find(ref, limit=10)

        assert result.exact is False
        assert len(result.entities) == 2
        assert result.source == "local"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_entity_finder.py -v`
Expected: FAIL

**Step 3: Implement EntityFinder + TrackFinder**

```python
# app/mcp/entity_finder.py
"""Entity resolution — find entities by ref (URN, text, ID).

Each entity type has its own Finder class. All return FindResult
with a list of matches (even for exact IDs — list of 0 or 1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.mcp.refs import ParsedRef, RefType
from app.mcp.types_v2 import FindResult, TrackSummary

if TYPE_CHECKING:
    from app.repositories.tracks import TrackRepository

class TrackFinder:
    """Resolve track refs to TrackSummary entities."""

    def __init__(
        self,
        track_repo: TrackRepository,
        track_repo_ext: TrackRepository,
    ) -> None:
        self._repo = track_repo
        self._repo_ext = track_repo_ext

    async def find(self, ref: ParsedRef, *, limit: int = 20) -> FindResult:
        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            return await self._find_by_id(ref.local_id)
        if ref.ref_type == RefType.TEXT and ref.query:
            return await self._find_by_text(ref.query, limit=limit)
        return FindResult(exact=False, entities=[], source="local")

    async def _find_by_id(self, track_id: int) -> FindResult:
        track = await self._repo.get_by_id(track_id)
        if track is None:
            return FindResult(exact=True, entities=[], source="local")

        artists = await self._repo_ext.get_artists_for_tracks([track.track_id])
        artist_str = ", ".join(artists.get(track.track_id, []))

        summary = TrackSummary(
            ref=f"local:{track.track_id}",
            title=track.title,
            artist=artist_str or "Unknown",
            duration_ms=track.duration_ms,
        )
        return FindResult(exact=True, entities=[summary], source="local")

    async def _find_by_text(self, query: str, *, limit: int = 20) -> FindResult:
        tracks, _total = await self._repo.search_by_title(
            query, offset=0, limit=limit
        )
        if not tracks:
            return FindResult(exact=False, entities=[], source="local")

        track_ids = [t.track_id for t in tracks]
        artists_map = await self._repo_ext.get_artists_for_tracks(track_ids)

        entities = [
            TrackSummary(
                ref=f"local:{t.track_id}",
                title=t.title,
                artist=", ".join(artists_map.get(t.track_id, [])) or "Unknown",
                duration_ms=t.duration_ms,
            )
            for t in tracks
        ]
        return FindResult(exact=False, entities=entities, source="local")
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_entity_finder.py -v`
Expected: ALL PASS

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/entity_finder.py tests/mcp/test_entity_finder.py
git add app/mcp/entity_finder.py tests/mcp/test_entity_finder.py
git commit -m "feat(mcp): add EntityFinder with TrackFinder — ref resolution to DB lookups"
```

---

## Task 5: PlaylistFinder + SetFinder + ArtistFinder

**Files:**
- Modify: `app/mcp/entity_finder.py`
- Test: `tests/mcp/test_entity_finder.py` (extend)

Same pattern as TrackFinder, for the other entity types.

**Step 1: Write failing tests for PlaylistFinder**

```python
# Add to tests/mcp/test_entity_finder.py
from app.mcp.entity_finder import PlaylistFinder, SetFinder, ArtistFinder

@pytest.fixture
def mock_playlist_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.search_by_name = AsyncMock(return_value=([], 0))
    return repo

class TestPlaylistFinder:
    async def test_find_by_id(self, mock_playlist_repo):
        playlist = MagicMock()
        playlist.playlist_id = 5
        playlist.name = "Techno develop"
        mock_playlist_repo.get_by_id = AsyncMock(return_value=playlist)

        finder = PlaylistFinder(mock_playlist_repo)
        ref = parse_ref("local:5")
        result = await finder.find(ref)

        assert result.exact is True
        assert result.entities[0].name == "Techno develop"

    async def test_find_by_text(self, mock_playlist_repo):
        p = MagicMock()
        p.playlist_id = 5
        p.name = "Techno develop"
        mock_playlist_repo.search_by_name = AsyncMock(return_value=([p], 1))

        finder = PlaylistFinder(mock_playlist_repo)
        ref = parse_ref("Techno")
        result = await finder.find(ref)

        assert result.exact is False
        assert len(result.entities) == 1
```

**Step 2: Run tests, verify fail**

**Step 3: Implement PlaylistFinder, SetFinder, ArtistFinder in `entity_finder.py`**

Follow the same pattern as TrackFinder:
- `PlaylistFinder(playlist_repo)` → returns `PlaylistSummary`
- `SetFinder(set_repo)` → returns `SetSummary`
- `ArtistFinder(artist_repo)` → returns `ArtistSummary`

Each has `find(ref, limit=20) -> FindResult` with `_find_by_id` + `_find_by_text`.

**Step 4: Run tests, verify pass**

**Step 5: Lint + commit**

```bash
git commit -m "feat(mcp): add PlaylistFinder, SetFinder, ArtistFinder"
```

---

## Task 6: LibraryStats Service

**Files:**
- Create: `app/mcp/library_stats.py`
- Test: `tests/mcp/test_library_stats.py`

Computes background stats for every response: total tracks/playlists/sets/analyzed count.
Uses COUNT queries — lightweight, cached per session.

**Step 1: Write failing tests**

```python
# tests/mcp/test_library_stats.py
from unittest.mock import AsyncMock
from app.mcp.library_stats import get_library_stats
from app.mcp.types_v2 import LibraryStats

async def test_get_library_stats():
    session = AsyncMock()
    # Mock execute to return scalars for 4 COUNT queries
    session.execute = AsyncMock()
    session.execute.side_effect = [
        _scalar(3247),  # tracks
        _scalar(2890),  # analyzed (features)
        _scalar(15),    # playlists
        _scalar(8),     # sets
    ]

    stats = await get_library_stats(session)
    assert isinstance(stats, LibraryStats)
    assert stats.total_tracks == 3247
    assert stats.analyzed_tracks == 2890
    assert stats.total_playlists == 15
    assert stats.total_sets == 8

def _scalar(value):
    """Create a mock result with scalar_one() returning value."""
    mock = AsyncMock()
    mock.scalar_one = lambda: value
    return mock
```

**Step 2: Run, fail**

**Step 3: Implement**

```python
# app/mcp/library_stats.py
"""Library-wide statistics for response envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.mcp.types_v2 import LibraryStats
from app.models.catalog import Track
from app.models.dj import DjPlaylist
from app.models.features import TrackAudioFeaturesComputed
from app.models.sets import DjSet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

async def get_library_stats(session: AsyncSession) -> LibraryStats:
    """Get library-wide counts (4 lightweight COUNT queries)."""
    tracks = (await session.execute(select(func.count(Track.track_id)))).scalar_one()
    analyzed = (
        await session.execute(
            select(func.count(func.distinct(TrackAudioFeaturesComputed.track_id)))
        )
    ).scalar_one()
    playlists = (
        await session.execute(select(func.count(DjPlaylist.playlist_id)))
    ).scalar_one()
    sets = (await session.execute(select(func.count(DjSet.set_id)))).scalar_one()

    return LibraryStats(
        total_tracks=tracks,
        analyzed_tracks=analyzed,
        total_playlists=playlists,
        total_sets=sets,
    )
```

**Step 4: Run, pass**

**Step 5: Lint + commit**

```bash
git commit -m "feat(mcp): add library_stats — lightweight COUNT queries for response envelope"
```

---

## Task 7: Audio Features SQL Filter

**Files:**
- Modify: `app/repositories/audio_features.py`
- Test: `tests/test_audio_features_repo.py` (extend)

Add SQL-level filtering by BPM, key, energy — replacing current in-memory Python loop.

**Step 1: Write failing test**

```python
# Add to existing tests/test_audio_features_repo.py or create tests/test_features_filter.py
async def test_filter_by_criteria(session):
    """filter_by_criteria returns tracks matching BPM + key + energy range."""
    repo = AudioFeaturesRepository(session)

    results, total = await repo.filter_by_criteria(
        bpm_min=138.0,
        bpm_max=145.0,
        key_codes=[8, 9],  # 5A, 6A in key_code
        energy_min=-10.0,
        energy_max=-5.0,
        offset=0,
        limit=50,
    )
    assert isinstance(results, list)
    assert isinstance(total, int)
```

**Step 2: Run, fail**

**Step 3: Implement `filter_by_criteria` in AudioFeaturesRepository**

```python
# Add to app/repositories/audio_features.py
async def filter_by_criteria(
    self,
    *,
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    key_codes: list[int] | None = None,
    energy_min: float | None = None,
    energy_max: float | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[TrackAudioFeaturesComputed], int]:
    """Filter features by audio parameters at SQL level."""
    filters: list[Any] = []
    if bpm_min is not None:
        filters.append(TrackAudioFeaturesComputed.bpm >= bpm_min)
    if bpm_max is not None:
        filters.append(TrackAudioFeaturesComputed.bpm <= bpm_max)
    if key_codes:
        filters.append(TrackAudioFeaturesComputed.key_code.in_(key_codes))
    if energy_min is not None:
        filters.append(TrackAudioFeaturesComputed.lufs_i >= energy_min)
    if energy_max is not None:
        filters.append(TrackAudioFeaturesComputed.lufs_i <= energy_max)

    return await self.list(offset=offset, limit=limit, filters=filters)
```

Note: uses existing `BaseRepository.list()` which already handles COUNT + pagination.

**Step 4: Run, pass**

**Step 5: Lint + commit**

```bash
git commit -m "feat(repo): add filter_by_criteria to AudioFeaturesRepository — SQL-level BPM/key/energy"
```

---

## Task 8: Universal Search Tool

**Files:**
- Create: `app/mcp/workflows/search_tools.py`
- Modify: `app/mcp/workflows/server.py` — register new tools
- Test: `tests/mcp/test_search_tools.py`

The `search` tool — fan-out to all entity finders + library stats.

**Step 1: Write failing test**

Test that the search tool is registered and returns SearchResponse structure.

```python
# tests/mcp/test_search_tools.py
from fastmcp import Client

async def test_search_tool_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "search" in names

async def test_search_returns_structure(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("search", {"query": "nonexistent_xyz"})
        # Should return valid JSON with results/stats/library/pagination
        import json
        data = json.loads(result[0].text)
        assert "results" in data
        assert "stats" in data
        assert "library" in data
        assert "pagination" in data
```

**Step 2: Run, fail**

**Step 3: Implement search tool**

```python
# app/mcp/workflows/search_tools.py
"""Universal search + filter tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.dependencies import Depends

from app.mcp.dependencies import get_session
from app.mcp.entity_finder import ArtistFinder, PlaylistFinder, SetFinder, TrackFinder
from app.mcp.library_stats import get_library_stats
from app.mcp.pagination import encode_cursor, paginate_params
from app.mcp.refs import parse_ref
from app.mcp.types_v2 import (
    LibraryStats,
    MatchStats,
    PaginationInfo,
    SearchResponse,
)
from app.repositories.artists import ArtistRepository
from app.repositories.playlists import DjPlaylistRepository
from app.repositories.sets import DjSetRepository
from app.repositories.tracks import TrackRepository

def register_search_tools(mcp: FastMCP) -> None:
    @mcp.tool(tags={"search"}, annotations={"readOnlyHint": True})
    async def search(
        query: str,
        scope: str = "all",
        limit: int = 20,
        cursor: str | None = None,
        session=Depends(get_session),
    ) -> str:
        """Universal search across all entities and platforms.

        Searches local DB (tracks, playlists, sets, artists) by fuzzy text match.
        Returns categorized results + background statistics + pagination.

        Args:
            query: Search text — name, title, artist, anything.
            scope: "all" | "tracks" | "playlists" | "sets" — limit search scope.
            limit: Max results per category (default 20, max 100).
            cursor: Pagination cursor from previous response.
        """
        import json

        offset, clamped_limit = paginate_params(cursor=cursor, limit=limit)
        ref = parse_ref(query)

        results: dict[str, list[dict]] = {}
        total_matches: dict[str, int] = {}

        track_repo = TrackRepository(session)
        playlist_repo = DjPlaylistRepository(session)
        set_repo = DjSetRepository(session)
        artist_repo = ArtistRepository(session)

        if scope in ("all", "tracks"):
            finder = TrackFinder(track_repo, track_repo)
            found = await finder.find(ref, limit=clamped_limit)
            results["tracks"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["tracks"] = len(found.entities)

        if scope in ("all", "playlists"):
            finder = PlaylistFinder(playlist_repo)
            found = await finder.find(ref, limit=clamped_limit)
            results["playlists"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["playlists"] = len(found.entities)

        if scope in ("all", "sets"):
            finder = SetFinder(set_repo)
            found = await finder.find(ref, limit=clamped_limit)
            results["sets"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["sets"] = len(found.entities)

        if scope in ("all", "artists"):
            finder = ArtistFinder(artist_repo)
            found = await finder.find(ref, limit=clamped_limit)
            results["artists"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["artists"] = len(found.entities)

        library = await get_library_stats(session)

        has_more = any(len(v) >= clamped_limit for v in results.values())
        next_cursor = encode_cursor(offset=offset + clamped_limit) if has_more else None

        response = SearchResponse(
            results=results,
            stats=MatchStats(total_matches=total_matches),
            library=library,
            pagination=PaginationInfo(
                limit=clamped_limit, has_more=has_more, cursor=next_cursor
            ),
        )
        return json.dumps(response.model_dump(exclude_none=True), ensure_ascii=False)
```

**Step 4: Register in server.py**

Add `register_search_tools(mcp)` to `create_workflow_mcp()` in `app/mcp/workflows/server.py`.

**Step 5: Run tests, verify pass**

Run: `uv run pytest tests/mcp/test_search_tools.py -v`

**Step 6: Lint + commit**

```bash
git commit -m "feat(mcp): add universal search tool — fan-out to all entity finders"
```

---

## Task 9: filter_tracks Tool

**Files:**
- Modify: `app/mcp/workflows/search_tools.py`
- Test: `tests/mcp/test_search_tools.py` (extend)

SQL-level filtering by BPM, key, energy, mood — replaces in-memory `search_by_criteria`.

**Step 1: Write failing test**

```python
async def test_filter_tracks_tool_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "filter_tracks" in names
```

**Step 2: Run, fail**

**Step 3: Implement filter_tracks**

Add to `search_tools.py`:

```python
@mcp.tool(tags={"search"}, annotations={"readOnlyHint": True})
async def filter_tracks(
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    keys: list[str] | None = None,
    energy_min: float | None = None,
    energy_max: float | None = None,
    mood: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    session=Depends(get_session),
) -> str:
    """Filter tracks by audio parameters (BPM, Camelot key, energy LUFS, mood).

    Uses SQL-level filtering — efficient for large libraries.
    Returns paginated track list + background statistics.

    Args:
        bpm_min/bpm_max: BPM range (e.g., 138.0 to 145.0).
        keys: Camelot keys (e.g., ["5A", "6A", "7B"]).
        energy_min/energy_max: LUFS range (e.g., -10.0 to -5.0).
        mood: Filter by mood classification.
        limit: Max results (default 50, max 100).
        cursor: Pagination cursor.
    """
    # Convert Camelot keys to key_codes, call repo.filter_by_criteria,
    # join with Track for title/artist, return paginated TrackSummary list.
    ...
```

**Step 4: Run, verify pass**

**Step 5: Lint + commit**

```bash
git commit -m "feat(mcp): add filter_tracks tool — SQL-level BPM/key/energy filtering"
```

---

## Task 10: Visibility Setup — Audio Namespace

**Files:**
- Create: `app/mcp/audio/server.py`
- Modify: `app/mcp/gateway.py` — mount audio namespace
- Modify: `app/mcp/workflows/server.py` — add `activate_audio_mode`
- Test: `tests/mcp/test_visibility.py` (extend)

Wire first 3 audio compute tools (compute_bpm, compute_key, compute_loudness) into MCP.
Rest of audio tools follow the same pattern.

**Step 1: Write failing test**

```python
# Add to tests/mcp/test_visibility.py
async def test_audio_tools_hidden_by_default(gateway_mcp):
    async with Client(gateway_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "audio_compute_bpm" not in names

async def test_activate_audio_mode(gateway_mcp):
    async with Client(gateway_mcp) as client:
        # activate
        await client.call_tool("dj_activate_audio_mode", {})
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "audio_compute_bpm" in names
```

**Step 2: Run, fail**

**Step 3: Implement audio server with 3 tools**

```python
# app/mcp/audio/server.py
"""Audio compute tools — pure functions exposed as MCP tools.

Hidden by default. Activate via activate_audio_mode().
Each tool accepts track_ref | audio_path and returns analysis results.
"""

from __future__ import annotations

from fastmcp import FastMCP

def create_audio_mcp() -> FastMCP:
    mcp = FastMCP("Audio Analysis")

    @mcp.tool(tags={"audio", "compute"})
    async def compute_bpm(
        track_ref: str | None = None,
        audio_path: str | None = None,
    ) -> str:
        """Estimate BPM of an audio track.

        Accepts track_ref (local:42, ym:123) or direct audio_path.
        Returns BpmResult: bpm, confidence, stability, is_variable.
        """
        from app.utils.audio import load_audio
        from app.utils.audio.bpm import estimate_bpm
        # resolve track_ref to path, or use audio_path directly
        # load audio, run estimate_bpm, return JSON
        ...

    # compute_key, compute_loudness follow same pattern
    ...

    return mcp
```

**Step 4: Mount in gateway.py**

```python
# In create_dj_mcp():
audio_server = create_audio_mcp()
gateway.mount(audio_server, namespace="audio")
gateway.disable(tags={"audio"})
```

**Step 5: Add activate_audio_mode to workflow server**

**Step 6: Run tests, verify pass**

**Step 7: Lint + commit**

```bash
git commit -m "feat(mcp): add audio namespace with compute_bpm/key/loudness — hidden by default"
```

---

## Task 11: YM Extended Visibility

**Files:**
- Modify: `app/mcp/yandex_music/server.py` — tag tools
- Modify: `app/mcp/workflows/server.py` — add `activate_ym_extended`
- Test: `tests/mcp/test_visibility.py` (extend)

Tag non-core YM tools with `ym_extended`, hide them. Add activation tool.

**Step 1: Define core YM tool list**

Core (12 tools): `search_yandex_music`, `get_tracks`, `get_play_lists`, `get_playlist_by_id`,
`create_playlist`, `rename_playlist`, `change_playlist_tracks`, `delete_playlist`,
`like_tracks`, `remove_liked_tracks`, `get_liked_tracks_ids`, `get_download_info`.

Everything else gets tag `ym_extended`.

**Step 2: Write failing test**

```python
async def test_ym_extended_hidden(gateway_mcp):
    async with Client(gateway_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "ym_get_artist_brief_info" not in names
        assert "ym_search_yandex_music" in names  # core stays visible
```

**Step 3: Implement tagging in YM server + activation tool**

**Step 4: Run, pass, lint, commit**

```bash
git commit -m "feat(mcp): add ym_extended visibility — 12 core YM tools visible, rest hidden"
```

---

## Task 12: Integration Test — Full Search Flow

**Files:**
- Test: `tests/mcp/test_search_integration.py`

End-to-end test: create tracks in DB → search by text → verify response format with stats.

**Step 1: Write integration test**

```python
# tests/mcp/test_search_integration.py
"""Integration test — full search flow with DB."""

from fastmcp import Client

async def test_search_finds_tracks_by_artist(workflow_mcp, session):
    """Create tracks, search by artist name, verify response."""
    from app.models.catalog import Track, Artist, TrackArtist

    # Setup: create artist + 2 tracks
    artist = Artist(name="Test Artist")
    session.add(artist)
    await session.flush()

    t1 = Track(title="Track Alpha", duration_ms=300000)
    t2 = Track(title="Track Beta", duration_ms=200000)
    session.add_all([t1, t2])
    await session.flush()

    ta1 = TrackArtist(track_id=t1.track_id, artist_id=artist.artist_id, role=0)
    ta2 = TrackArtist(track_id=t2.track_id, artist_id=artist.artist_id, role=0)
    session.add_all([ta1, ta2])
    await session.commit()

    # Search
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("search", {"query": "Test Artist"})
        import json
        data = json.loads(result[0].text)

        assert data["library"]["total_tracks"] >= 2
        assert data["stats"]["total_matches"]["tracks"] >= 0
        assert "pagination" in data
```

**Step 2: Run, verify pass (end-to-end)**

**Step 3: Commit**

```bash
git commit -m "test(mcp): add search integration test — full DB flow"
```

---

## Summary

| Task | Component | Files | Est. |
|------|-----------|-------|------|
| 1 | Response models (types_v2) | 2 new | 15 min |
| 2 | Pagination codec | 2 new | 10 min |
| 3 | Ref parser | 2 new | 15 min |
| 4 | EntityFinder + TrackFinder | 2 new | 20 min |
| 5 | Playlist/Set/Artist Finders | 2 modified | 15 min |
| 6 | LibraryStats service | 2 new | 10 min |
| 7 | Audio features SQL filter | 2 modified | 15 min |
| 8 | Universal search tool | 2 new + 1 mod | 25 min |
| 9 | filter_tracks tool | 1 mod + 1 test | 20 min |
| 10 | Audio namespace + visibility | 3 new + 2 mod | 25 min |
| 11 | YM extended visibility | 2 mod | 15 min |
| 12 | Integration test | 1 new | 15 min |

**Total: ~12 tasks, ~3.5 hours estimated**

No breaking changes — all new code sits alongside existing tools.
Phase 2 (CRUD paradigm + compute/persist split) builds on this foundation.
