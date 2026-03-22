# MCP Tools Redesign — Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement CRUD tool paradigm for all entities, split compute from persist, unify export tools, and remove stubs — building on Phase 1's EntityFinder, response models, and pagination.

**Architecture:** New CRUD tools use shared converters (ORM → types_v2) and response wrappers (JSON envelope with library stats + pagination). Compute tools (analyze, build) return data without DB writes. Persist tools (save_features, create_set) explicitly save. All tools accept URN refs from Phase 1.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest

**Design doc:** `docs/plans/2026-02-19-mcp-tools-redesign-design.md`
**Phase 1 plan:** `docs/plans/2026-02-19-mcp-tools-redesign-plan.md` (prerequisite — must be implemented first)

**Phase 1 delivers (used by this plan):**
- `app/mcp/types_v2.py` — TrackSummary, TrackDetail, PlaylistSummary, SetSummary, ArtistSummary, LibraryStats, PaginationInfo, SearchResponse, FindResult
- `app/mcp/pagination.py` — encode_cursor, decode_cursor, paginate_params
- `app/mcp/refs.py` — parse_ref, ParsedRef, RefType
- `app/mcp/entity_finder.py` — TrackFinder, PlaylistFinder, SetFinder, ArtistFinder
- `app/mcp/library_stats.py` — get_library_stats(session)
- `app/mcp/workflows/search_tools.py` — search, filter_tracks tools

---

## Task 1: Response Envelope Models + Wrappers

**Files:**
- Modify: `app/mcp/types_v2.py` — add envelope models + Detail types
- Create: `app/mcp/response.py` — wrap_list, wrap_detail, wrap_action helpers
- Test: `tests/mcp/test_response.py`

Adds response envelope models and DRY wrapper functions. Every CRUD tool returns JSON with the same structure: `{results/result + library + pagination}`.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_response.py
"""Tests for response envelope helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types_v2 import (
    EntityDetailResponse,
    EntityListResponse,
    LibraryStats,
    PlaylistDetail,
    PlaylistSummary,
    SetDetail,
    TrackSummary,
)

@pytest.fixture
def mock_session():
    """Mock AsyncSession that returns library stats counts."""
    session = AsyncMock()
    # 4 COUNT queries: tracks, analyzed, playlists, sets
    session.execute = AsyncMock(
        side_effect=[_scalar(100), _scalar(80), _scalar(5), _scalar(3)]
    )
    return session

def _scalar(value: int) -> AsyncMock:
    mock = AsyncMock()
    mock.scalar_one = lambda: value
    return mock

class TestWrapList:
    async def test_basic(self, mock_session):
        entities = [
            TrackSummary(ref="local:1", title="A", artist="X"),
            TrackSummary(ref="local:2", title="B", artist="Y"),
        ]
        result = await wrap_list(entities, total=50, offset=0, limit=20, session=mock_session)

        import json

        data = json.loads(result)
        assert len(data["results"]) == 2
        assert data["total"] == 50
        assert data["library"]["total_tracks"] == 100
        assert data["pagination"]["has_more"] is True
        assert data["pagination"]["cursor"] is not None

    async def test_last_page(self, mock_session):
        entities = [TrackSummary(ref="local:1", title="A", artist="X")]
        result = await wrap_list(entities, total=1, offset=0, limit=20, session=mock_session)

        import json

        data = json.loads(result)
        assert data["pagination"]["has_more"] is False
        assert data["pagination"]["cursor"] is None

class TestWrapDetail:
    async def test_basic(self, mock_session):
        entity = TrackSummary(ref="local:42", title="Gravity", artist="Boris Brejcha")
        result = await wrap_detail(entity, mock_session)

        import json

        data = json.loads(result)
        assert data["result"]["ref"] == "local:42"
        assert data["library"]["total_tracks"] == 100

class TestWrapAction:
    async def test_success(self, mock_session):
        entity = TrackSummary(ref="local:42", title="New", artist="Me")
        result = await wrap_action(
            success=True,
            message="Track created",
            session=mock_session,
            result=entity,
        )

        import json

        data = json.loads(result)
        assert data["success"] is True
        assert data["message"] == "Track created"
        assert data["result"]["ref"] == "local:42"

    async def test_delete_no_result(self, mock_session):
        result = await wrap_action(
            success=True,
            message="Deleted local:42",
            session=mock_session,
        )

        import json

        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] is None

class TestDetailTypes:
    def test_playlist_detail(self):
        d = PlaylistDetail(
            ref="local:5",
            name="Techno develop",
            track_count=247,
            analyzed_count=200,
            bpm_range=(128.0, 145.0),
            keys=["5A", "6A"],
            avg_energy=-7.5,
            duration_minutes=120.5,
        )
        assert d.analyzed_count == 200
        assert d.bpm_range == (128.0, 145.0)

    def test_set_detail(self):
        d = SetDetail(
            ref="local:3",
            name="Friday night",
            version_count=2,
            track_count=15,
            description="Peak hour mix",
            template_name="classic_60",
            latest_version_id=42,
            latest_score=0.78,
        )
        assert d.template_name == "classic_60"
        assert d.latest_version_id == 42
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_response.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Add envelope models + Detail types to types_v2.py**

Add these classes to `app/mcp/types_v2.py` (after existing code):

```python
# --- Entity Details (Level 2: ~300 bytes each) --- (extend existing)

class PlaylistDetail(PlaylistSummary):
    """Extended playlist info — single entity view."""

    analyzed_count: int = 0
    bpm_range: tuple[float, float] | None = None
    keys: list[str] = Field(default_factory=list)
    avg_energy: float | None = None
    duration_minutes: float = 0.0

class SetDetail(SetSummary):
    """Extended set info — single entity view."""

    description: str | None = None
    template_name: str | None = None
    target_bpm_min: float | None = None
    target_bpm_max: float | None = None
    latest_version_id: int | None = None
    latest_score: float | None = None

# --- Response Envelopes ---

class EntityListResponse(BaseModel):
    """Standard response for list/search operations."""

    results: list[Any]
    total: int
    library: LibraryStats
    pagination: PaginationInfo

class EntityDetailResponse(BaseModel):
    """Standard response for single-entity operations."""

    result: dict[str, Any]
    library: LibraryStats

class ActionResponse(BaseModel):
    """Standard response for create/update/delete actions."""

    success: bool
    message: str
    result: dict[str, Any] | None = None
    library: LibraryStats
```

**Step 4: Implement response wrappers**

```python
# app/mcp/response.py
"""DRY response envelope wrappers for MCP tools.

Every CRUD tool returns JSON with the same structure.
These helpers add LibraryStats + PaginationInfo automatically.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.mcp.library_stats import get_library_stats
from app.mcp.pagination import encode_cursor
from app.mcp.types_v2 import (
    ActionResponse,
    EntityDetailResponse,
    EntityListResponse,
    PaginationInfo,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

async def wrap_list(
    entities: list[BaseModel],
    total: int,
    offset: int,
    limit: int,
    session: AsyncSession,
) -> str:
    """Wrap a list of entities with library stats + pagination."""
    library = await get_library_stats(session)
    has_more = offset + limit < total
    next_cursor = encode_cursor(offset=offset + limit) if has_more else None

    resp = EntityListResponse(
        results=[e.model_dump(exclude_none=True) for e in entities],
        total=total,
        library=library,
        pagination=PaginationInfo(limit=limit, has_more=has_more, cursor=next_cursor),
    )
    return json.dumps(resp.model_dump(exclude_none=True), ensure_ascii=False)

async def wrap_detail(
    entity: BaseModel,
    session: AsyncSession,
) -> str:
    """Wrap a single entity with library context."""
    library = await get_library_stats(session)

    resp = EntityDetailResponse(
        result=entity.model_dump(exclude_none=True),
        library=library,
    )
    return json.dumps(resp.model_dump(exclude_none=True), ensure_ascii=False)

async def wrap_action(
    *,
    success: bool,
    message: str,
    session: AsyncSession,
    result: BaseModel | None = None,
) -> str:
    """Wrap a create/update/delete confirmation with library context."""
    library = await get_library_stats(session)

    resp = ActionResponse(
        success=success,
        message=message,
        result=result.model_dump(exclude_none=True) if result else None,
        library=library,
    )
    return json.dumps(resp.model_dump(exclude_none=True), ensure_ascii=False)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_response.py -v`
Expected: ALL PASS

**Step 6: Lint**

Run: `uv run ruff check app/mcp/response.py app/mcp/types_v2.py tests/mcp/test_response.py && uv run mypy app/mcp/response.py app/mcp/types_v2.py`

**Step 7: Commit**

```bash
git add app/mcp/response.py app/mcp/types_v2.py tests/mcp/test_response.py
git commit -m "feat(mcp): add response envelope models + wrap_list/wrap_detail/wrap_action helpers"
```

---

## Task 2: ORM-to-Response Converters

**Files:**
- Create: `app/mcp/converters.py`
- Test: `tests/mcp/test_converters.py`
- Modify: `app/mcp/entity_finder.py` — refactor to use converters

Pure mapping functions: ORM model → types_v2 Summary/Detail. No DB access — callers fetch data first, then convert.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_converters.py
"""Tests for ORM-to-Response converters."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.mcp.converters import (
    artist_to_summary,
    playlist_to_summary,
    set_to_summary,
    track_to_detail,
    track_to_summary,
)
from app.mcp.types_v2 import (
    ArtistSummary,
    PlaylistSummary,
    SetSummary,
    TrackDetail,
    TrackSummary,
)

def _make_track(track_id: int = 42, title: str = "Gravity", duration_ms: int = 360000):
    track = MagicMock()
    track.track_id = track_id
    track.title = title
    track.duration_ms = duration_ms
    return track

def _make_features(
    bpm: float = 140.0,
    key_code: int = 8,
    lufs_i: float = -8.3,
):
    f = MagicMock()
    f.bpm = bpm
    f.key_code = key_code
    f.lufs_i = lufs_i
    return f

class TestTrackToSummary:
    def test_minimal(self):
        track = _make_track()
        result = track_to_summary(track, artists_map={42: ["Boris Brejcha"]})

        assert isinstance(result, TrackSummary)
        assert result.ref == "local:42"
        assert result.title == "Gravity"
        assert result.artist == "Boris Brejcha"
        assert result.bpm is None  # no features

    def test_with_features(self):
        track = _make_track()
        features = _make_features()
        result = track_to_summary(
            track, artists_map={42: ["Boris Brejcha"]}, features=features
        )

        assert result.bpm == 140.0
        assert result.key == "5A"  # key_code 8 = 5A
        assert result.energy_lufs == -8.3

    def test_multiple_artists(self):
        track = _make_track()
        result = track_to_summary(
            track, artists_map={42: ["Boris Brejcha", "Ann Clue"]}
        )
        assert result.artist == "Boris Brejcha, Ann Clue"

    def test_unknown_artist(self):
        track = _make_track()
        result = track_to_summary(track, artists_map={})
        assert result.artist == "Unknown"

class TestTrackToDetail:
    def test_full(self):
        track = _make_track()
        features = _make_features()
        result = track_to_detail(
            track,
            artists_map={42: ["Boris Brejcha"]},
            features=features,
            genres=["Techno"],
            labels=["Fckng Serious"],
            albums=["Gravity EP"],
            platform_ids={"ym": "12345"},
        )

        assert isinstance(result, TrackDetail)
        assert result.has_features is True
        assert result.genres == ["Techno"]
        assert result.labels == ["Fckng Serious"]
        assert result.platform_ids == {"ym": "12345"}

    def test_no_features(self):
        track = _make_track()
        result = track_to_detail(track, artists_map={42: ["X"]})
        assert result.has_features is False
        assert result.bpm is None

class TestPlaylistToSummary:
    def test_basic(self):
        playlist = MagicMock()
        playlist.playlist_id = 5
        playlist.name = "Techno develop"

        result = playlist_to_summary(playlist, item_count=247)
        assert isinstance(result, PlaylistSummary)
        assert result.ref == "local:5"
        assert result.track_count == 247

class TestSetToSummary:
    def test_basic(self):
        s = MagicMock()
        s.set_id = 3
        s.name = "Friday night"

        result = set_to_summary(s, version_count=2, track_count=15)
        assert isinstance(result, SetSummary)
        assert result.ref == "local:3"
        assert result.version_count == 2

class TestArtistToSummary:
    def test_basic(self):
        artist = MagicMock()
        artist.artist_id = 10
        artist.name = "Boris Brejcha"

        result = artist_to_summary(artist, tracks_in_db=5)
        assert isinstance(result, ArtistSummary)
        assert result.ref == "local:10"
        assert result.tracks_in_db == 5
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_converters.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement converters**

```python
# app/mcp/converters.py
"""ORM-to-Response converters.

Pure mapping functions — no DB access, no side effects.
Callers fetch data from DB first, then call these to convert.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from app.mcp.types_v2 import (
    ArtistSummary,
    PlaylistSummary,
    SetSummary,
    TrackDetail,
    TrackSummary,
)
from app.utils.audio.camelot import key_code_to_camelot

if TYPE_CHECKING:
    from app.models.catalog import Artist, Track
    from app.models.dj import DjPlaylist
    from app.models.features import TrackAudioFeaturesComputed
    from app.models.sets import DjSet

def track_to_summary(
    track: Track,
    artists_map: dict[int, list[str]],
    features: TrackAudioFeaturesComputed | None = None,
) -> TrackSummary:
    """Convert Track ORM → TrackSummary (Level 1, ~150 bytes)."""
    artist_str = ", ".join(artists_map.get(track.track_id, [])) or "Unknown"

    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None

    if features is not None:
        bpm = features.bpm
        energy_lufs = features.lufs_i
        with contextlib.suppress(ValueError):
            key = key_code_to_camelot(features.key_code)

    return TrackSummary(
        ref=f"local:{track.track_id}",
        title=track.title,
        artist=artist_str,
        bpm=bpm,
        key=key,
        energy_lufs=energy_lufs,
        duration_ms=track.duration_ms,
    )

def track_to_detail(
    track: Track,
    artists_map: dict[int, list[str]],
    features: TrackAudioFeaturesComputed | None = None,
    genres: list[str] | None = None,
    labels: list[str] | None = None,
    albums: list[str] | None = None,
    platform_ids: dict[str, str] | None = None,
    sections_count: int = 0,
) -> TrackDetail:
    """Convert Track ORM → TrackDetail (Level 2, ~300 bytes)."""
    summary = track_to_summary(track, artists_map, features)

    return TrackDetail(
        **summary.model_dump(),
        has_features=features is not None,
        genres=genres or [],
        labels=labels or [],
        albums=albums or [],
        platform_ids=platform_ids or {},
        sections_count=sections_count,
    )

def playlist_to_summary(
    playlist: DjPlaylist,
    item_count: int = 0,
    analyzed_count: int | None = None,
) -> PlaylistSummary:
    """Convert DjPlaylist ORM → PlaylistSummary."""
    return PlaylistSummary(
        ref=f"local:{playlist.playlist_id}",
        name=playlist.name,
        track_count=item_count,
        analyzed_count=analyzed_count,
    )

def set_to_summary(
    set_: DjSet,
    version_count: int = 0,
    track_count: int = 0,
    avg_score: float | None = None,
) -> SetSummary:
    """Convert DjSet ORM → SetSummary."""
    return SetSummary(
        ref=f"local:{set_.set_id}",
        name=set_.name,
        version_count=version_count,
        track_count=track_count,
        avg_score=avg_score,
    )

def artist_to_summary(
    artist: Artist,
    tracks_in_db: int = 0,
) -> ArtistSummary:
    """Convert Artist ORM → ArtistSummary."""
    return ArtistSummary(
        ref=f"local:{artist.artist_id}",
        name=artist.name,
        tracks_in_db=tracks_in_db,
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_converters.py -v`
Expected: ALL PASS

**Step 5: Refactor EntityFinder to use converters**

In `app/mcp/entity_finder.py`, replace inline TrackSummary/PlaylistSummary construction with converter calls. For example, in `TrackFinder._find_by_id`:

```python
# Before (inline):
summary = TrackSummary(
    ref=f"local:{track.track_id}",
    title=track.title,
    artist=artist_str or "Unknown",
    duration_ms=track.duration_ms,
)

# After (converter):
from app.mcp.converters import track_to_summary
summary = track_to_summary(track, artists_map)
```

Apply the same pattern to `PlaylistFinder`, `SetFinder`, `ArtistFinder` — use the matching converter function.

**Step 6: Run all MCP tests to verify no regressions**

Run: `uv run pytest tests/mcp/ -v`
Expected: ALL PASS

**Step 7: Lint + commit**

```bash
uv run ruff check app/mcp/converters.py app/mcp/entity_finder.py tests/mcp/test_converters.py
uv run mypy app/mcp/converters.py
git add app/mcp/converters.py app/mcp/entity_finder.py tests/mcp/test_converters.py
git commit -m "feat(mcp): add ORM-to-Response converters + refactor EntityFinder to use them"
```

---

## Task 3: Track CRUD Tools

**Files:**
- Create: `app/mcp/workflows/track_tools.py`
- Test: `tests/mcp/test_track_tools.py`
- Modify: `app/mcp/workflows/server.py` — register

5 tools: `list_tracks`, `get_track`, `create_track`, `update_track`, `delete_track`. All use EntityFinder for ref resolution, converters for response, wrappers for envelope.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_track_tools.py
"""Tests for Track CRUD tools."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_track_crud_tools_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        for tool in ["list_tracks", "get_track", "create_track", "update_track", "delete_track"]:
            assert tool in names, f"{tool} not registered"

async def test_list_tracks_empty(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("list_tracks", {})
        data = json.loads(result[0].text)
        assert "results" in data
        assert "library" in data
        assert "pagination" in data
        assert data["total"] == 0

async def test_list_tracks_with_search(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("list_tracks", {"search": "nonexistent"})
        data = json.loads(result[0].text)
        assert data["total"] == 0

async def test_get_track_not_found(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("get_track", {"track_ref": "local:99999"})
        data = json.loads(result[0].text)
        assert "error" in data

async def test_get_track_text_ref(workflow_mcp):
    """Text ref returns list of matches (even if empty)."""
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("get_track", {"track_ref": "Boris Brejcha"})
        data = json.loads(result[0].text)
        # Text search returns list format
        assert "results" in data or "error" in data
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_track_tools.py -v`
Expected: FAIL — tools not registered

**Step 3: Implement Track CRUD tools**

```python
# app/mcp/workflows/track_tools.py
"""Track CRUD tools for DJ workflow MCP server.

list_tracks — paginated list with optional text search
get_track — single track by ref (ID returns detail, text returns match list)
create_track — create new track in local DB
update_track — update track fields by ref
delete_track — delete track by ref
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.converters import track_to_detail, track_to_summary
from app.mcp.dependencies import get_session
from app.mcp.entity_finder import TrackFinder
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.schemas.tracks import TrackCreate, TrackUpdate
from app.services.tracks import TrackService
from app.utils.audio.camelot import key_code_to_camelot

async def _build_track_detail(track_id: int, session: AsyncSession):
    """Fetch all related data and build TrackDetail."""
    repo = TrackRepository(session)
    features_repo = AudioFeaturesRepository(session)

    track = await repo.get_by_id(track_id)
    if track is None:
        return None

    artists_map = await repo.get_artists_for_tracks([track_id])
    genres_map = await repo.get_genres_for_tracks([track_id])
    labels_map = await repo.get_labels_for_tracks([track_id])
    albums_map = await repo.get_albums_for_tracks([track_id])
    features = await features_repo.get_by_track(track_id)

    return track_to_detail(
        track,
        artists_map=artists_map,
        features=features,
        genres=genres_map.get(track_id, []),
        labels=labels_map.get(track_id, []),
        albums=albums_map.get(track_id, []),
    )

def register_track_tools(mcp: FastMCP) -> None:
    """Register Track CRUD tools on the MCP server."""

    @mcp.tool(tags={"crud", "track"}, annotations={"readOnlyHint": True})
    async def list_tracks(
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """List tracks with optional text search.

        Returns paginated TrackSummary list + library stats.

        Args:
            limit: Max results per page (default 20, max 100).
            cursor: Pagination cursor from previous response.
            search: Optional text to filter by title (fuzzy match).
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        repo = TrackRepository(session)

        if search:
            tracks, total = await repo.search_by_title(
                search, offset=offset, limit=clamped
            )
        else:
            tracks, total = await repo.list(offset=offset, limit=clamped)

        track_ids = [t.track_id for t in tracks]
        artists_map = await repo.get_artists_for_tracks(track_ids) if track_ids else {}

        summaries = [track_to_summary(t, artists_map) for t in tracks]
        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "track"}, annotations={"readOnlyHint": True})
    async def get_track(
        track_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Get track details by ref.

        Exact refs (local:42, 42) return full TrackDetail.
        Text refs ("Boris Brejcha") return ranked list of TrackSummary matches.

        Args:
            track_ref: Track reference — local:42, 42, ym:12345, or text query.
        """
        ref = parse_ref(track_ref)

        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            detail = await _build_track_detail(ref.local_id, session)
            if detail is None:
                return json.dumps({"error": "Track not found", "ref": track_ref})
            return await wrap_detail(detail, session)

        if ref.ref_type == RefType.TEXT:
            repo = TrackRepository(session)
            finder = TrackFinder(repo, repo)
            found = await finder.find(ref, limit=20)
            return await wrap_list(
                found.entities, len(found.entities), 0, 20, session
            )

        return json.dumps({"error": "Platform refs not yet supported", "ref": track_ref})

    @mcp.tool(tags={"crud", "track"})
    async def create_track(
        title: str,
        duration_ms: int,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Create a new track in the local database.

        Args:
            title: Track title.
            duration_ms: Duration in milliseconds (must be > 0).
        """
        svc = TrackService(TrackRepository(session))
        track_read = await svc.create(TrackCreate(title=title, duration_ms=duration_ms))

        detail = await _build_track_detail(track_read.track_id, session)
        return await wrap_action(
            success=True,
            message=f"Created track local:{track_read.track_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "track"})
    async def update_track(
        track_ref: str,
        title: str | None = None,
        duration_ms: int | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Update track fields by ref.

        Args:
            track_ref: Track reference (must resolve to exact ID).
            title: New title (optional).
            duration_ms: New duration in ms (optional).
        """
        ref = parse_ref(track_ref)

        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "update requires exact ref (local:N or N)", "ref": track_ref})

        svc = TrackService(TrackRepository(session))
        update_data = TrackUpdate(title=title, duration_ms=duration_ms)
        await svc.update(ref.local_id, update_data)

        detail = await _build_track_detail(ref.local_id, session)
        return await wrap_action(
            success=True,
            message=f"Updated track local:{ref.local_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "track"})
    async def delete_track(
        track_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Delete a track by ref.

        Args:
            track_ref: Track reference (must resolve to exact ID).
        """
        ref = parse_ref(track_ref)

        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "delete requires exact ref (local:N or N)", "ref": track_ref})

        svc = TrackService(TrackRepository(session))
        await svc.delete(ref.local_id)

        return await wrap_action(
            success=True,
            message=f"Deleted track local:{ref.local_id}",
            session=session,
        )
```

**Step 4: Register in server.py**

In `app/mcp/workflows/server.py`, add:

```python
from app.mcp.workflows.track_tools import register_track_tools

# Inside create_workflow_mcp():
register_track_tools(mcp)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_track_tools.py -v`
Expected: ALL PASS

**Step 6: Lint + commit**

```bash
uv run ruff check app/mcp/workflows/track_tools.py tests/mcp/test_track_tools.py
uv run mypy app/mcp/workflows/track_tools.py
git add app/mcp/workflows/track_tools.py tests/mcp/test_track_tools.py app/mcp/workflows/server.py
git commit -m "feat(mcp): add Track CRUD tools — list/get/create/update/delete with refs + envelope"
```

---

## Task 4: Playlist CRUD Tools

**Files:**
- Create: `app/mcp/workflows/playlist_tools.py`
- Test: `tests/mcp/test_playlist_tools.py`
- Modify: `app/mcp/workflows/server.py` — register

Same pattern as Track CRUD (Task 3). 5 tools: `list_playlists`, `get_playlist`, `create_playlist`, `update_playlist`, `delete_playlist`.

**Key differences from Track CRUD:**
- `get_playlist` returns `PlaylistDetail` with track list, BPM range, key stats, energy stats
- `create_playlist` accepts `name` and optional `source_app`
- No artist join needed — playlists have items with track_ids

**Step 1: Write failing tests**

```python
# tests/mcp/test_playlist_tools.py
"""Tests for Playlist CRUD tools."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_playlist_crud_tools_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        for tool in [
            "list_playlists", "get_playlist", "create_playlist",
            "update_playlist", "delete_playlist",
        ]:
            assert tool in names, f"{tool} not registered"

async def test_list_playlists_empty(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("list_playlists", {})
        data = json.loads(result[0].text)
        assert "results" in data
        assert data["total"] == 0
```

**Step 2: Run, fail**

**Step 3: Implement playlist tools**

Follow the Track CRUD pattern (Task 3) with these specifics:

- `list_playlists` uses `DjPlaylistRepository.search_by_name()` for search, returns `PlaylistSummary`
- `get_playlist` builds `PlaylistDetail` by:
  1. Loading playlist items (`DjPlaylistItemRepository.list_by_playlist`)
  2. Loading features for each track to compute BPM range, keys, energy stats
  3. Computing duration from track metadata
- `create_playlist` uses `DjPlaylistService.create(DjPlaylistCreate(name=name))`
- `update_playlist` uses `DjPlaylistService.update(playlist_id, DjPlaylistUpdate(name=name))`
- `delete_playlist` uses `DjPlaylistService.delete(playlist_id)`

DI: use `get_playlist_service` from `app/mcp/dependencies.py` (already exists).

**Step 4: Register in server.py**

```python
from app.mcp.workflows.playlist_tools import register_playlist_tools
# Inside create_workflow_mcp():
register_playlist_tools(mcp)
```

**Step 5: Run tests, verify pass**

**Step 6: Lint + commit**

```bash
git add app/mcp/workflows/playlist_tools.py tests/mcp/test_playlist_tools.py app/mcp/workflows/server.py
git commit -m "feat(mcp): add Playlist CRUD tools — list/get/create/update/delete"
```

---

## Task 5: Set CRUD Tools

**Files:**
- Create: `app/mcp/workflows/set_tools.py`
- Test: `tests/mcp/test_set_tools.py`
- Modify: `app/mcp/workflows/server.py` — register

5 tools: `list_sets`, `get_set`, `create_set`, `update_set`, `delete_set`.

**Key difference:** `create_set` accepts optional `track_ids: list[int]` to populate the set with a version and items in one call (used after `build_set` compute).

**Step 1: Write failing tests**

```python
# tests/mcp/test_set_tools.py
"""Tests for Set CRUD tools."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_set_crud_tools_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        for tool in ["list_sets", "get_set", "create_set", "update_set", "delete_set"]:
            assert tool in names, f"{tool} not registered"

async def test_list_sets_empty(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("list_sets", {})
        data = json.loads(result[0].text)
        assert "results" in data
        assert data["total"] == 0
```

**Step 2: Run, fail**

**Step 3: Implement set tools**

```python
# app/mcp/workflows/set_tools.py
"""Set CRUD tools for DJ workflow MCP server."""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.converters import set_to_summary
from app.mcp.dependencies import get_session
from app.mcp.entity_finder import SetFinder
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types_v2 import SetDetail
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.schemas.sets import DjSetCreate, DjSetItemCreate, DjSetUpdate, DjSetVersionCreate
from app.services.sets import DjSetService

def register_set_tools(mcp: FastMCP) -> None:
    """Register Set CRUD tools on the MCP server."""

    def _make_svc(session: AsyncSession) -> DjSetService:
        return DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )

    async def _build_set_detail(set_id: int, session: AsyncSession) -> SetDetail | None:
        svc = _make_svc(session)
        try:
            set_read = await svc.get(set_id)
        except Exception:
            return None

        versions = await svc.list_versions(set_id)
        track_count = 0
        latest_version_id = None
        latest_score = None

        if versions.items:
            latest = versions.items[-1]
            latest_version_id = latest.set_version_id
            latest_score = latest.score
            items = await svc.list_items(latest.set_version_id)
            track_count = items.total

        return SetDetail(
            ref=f"local:{set_read.set_id}",
            name=set_read.name,
            version_count=versions.total,
            track_count=track_count,
            description=set_read.description,
            template_name=set_read.template_name,
            target_bpm_min=set_read.target_bpm_min,
            target_bpm_max=set_read.target_bpm_max,
            latest_version_id=latest_version_id,
            latest_score=latest_score,
        )

    @mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True})
    async def list_sets(
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """List DJ sets with optional text search.

        Args:
            limit: Max results per page (default 20, max 100).
            cursor: Pagination cursor from previous response.
            search: Optional text to filter by set name.
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        repo = DjSetRepository(session)

        if search:
            sets, total = await repo.search_by_name(search, offset=offset, limit=clamped)
        else:
            sets, total = await repo.list(offset=offset, limit=clamped)

        summaries = [set_to_summary(s) for s in sets]
        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True})
    async def get_set(
        set_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Get set details by ref. Text refs return match list.

        Args:
            set_ref: Set reference — local:3, 3, or text query.
        """
        ref = parse_ref(set_ref)

        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            detail = await _build_set_detail(ref.local_id, session)
            if detail is None:
                return json.dumps({"error": "Set not found", "ref": set_ref})
            return await wrap_detail(detail, session)

        if ref.ref_type == RefType.TEXT:
            repo = DjSetRepository(session)
            finder = SetFinder(repo)
            found = await finder.find(ref, limit=20)
            return await wrap_list(found.entities, len(found.entities), 0, 20, session)

        return json.dumps({"error": "Platform refs not yet supported", "ref": set_ref})

    @mcp.tool(tags={"crud", "set"})
    async def create_set(
        name: str,
        description: str | None = None,
        track_ids: list[int] | None = None,
        template_name: str | None = None,
        source_playlist_id: int | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Create a new DJ set, optionally populated with tracks.

        If track_ids provided, creates set + version + items in one call.
        Use after build_set() to persist the computed result.

        Args:
            name: Set name.
            description: Optional description.
            track_ids: Optional list of track IDs to populate (in order).
            template_name: Optional template name used for generation.
            source_playlist_id: Optional source playlist ID.
        """
        svc = _make_svc(session)

        set_data = DjSetCreate(
            name=name,
            description=description,
            template_name=template_name,
            source_playlist_id=source_playlist_id,
        )
        new_set = await svc.create(set_data)

        if track_ids:
            version = await svc.create_version(
                new_set.set_id,
                DjSetVersionCreate(version_label="v1"),
            )
            for idx, track_id in enumerate(track_ids):
                await svc.add_item(
                    version.set_version_id,
                    DjSetItemCreate(sort_index=idx, track_id=track_id),
                )

        detail = await _build_set_detail(new_set.set_id, session)
        return await wrap_action(
            success=True,
            message=f"Created set local:{new_set.set_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "set"})
    async def update_set(
        set_ref: str,
        name: str | None = None,
        description: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Update set fields by ref.

        Args:
            set_ref: Set reference (must resolve to exact ID).
            name: New name (optional).
            description: New description (optional).
        """
        ref = parse_ref(set_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "update requires exact ref", "ref": set_ref})

        svc = _make_svc(session)
        await svc.update(ref.local_id, DjSetUpdate(name=name, description=description))

        detail = await _build_set_detail(ref.local_id, session)
        return await wrap_action(
            success=True,
            message=f"Updated set local:{ref.local_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "set"})
    async def delete_set(
        set_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Delete a DJ set by ref.

        Args:
            set_ref: Set reference (must resolve to exact ID).
        """
        ref = parse_ref(set_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "delete requires exact ref", "ref": set_ref})

        svc = _make_svc(session)
        await svc.delete(ref.local_id)

        return await wrap_action(
            success=True,
            message=f"Deleted set local:{ref.local_id}",
            session=session,
        )
```

**Step 4: Register in server.py, run tests, lint, commit**

```bash
git commit -m "feat(mcp): add Set CRUD tools — create_set accepts track_ids for one-call set creation"
```

---

## Task 6: AudioFeatures CRUD

**Files:**
- Create: `app/mcp/workflows/features_tools.py`
- Test: `tests/mcp/test_features_tools.py`
- Modify: `app/mcp/workflows/server.py` — register

3 tools (partial CRUD — no update/delete for computed features):
- `list_features` — paginated list of tracks with features + BPM/key/energy stats
- `get_features` — full feature set for a single track
- `save_features` — persist computed features (used after `analyze_track`)

**Step 1: Write failing tests**

```python
# tests/mcp/test_features_tools.py
"""Tests for AudioFeatures CRUD tools."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_features_tools_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        for tool in ["list_features", "get_features", "save_features"]:
            assert tool in names, f"{tool} not registered"

async def test_list_features_empty(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("list_features", {})
        data = json.loads(result[0].text)
        assert "results" in data
        assert data["total"] == 0

async def test_get_features_not_found(workflow_mcp):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("get_features", {"track_ref": "local:99999"})
        data = json.loads(result[0].text)
        assert "error" in data
```

**Step 2: Run, fail**

**Step 3: Implement features tools**

```python
# app/mcp/workflows/features_tools.py
"""AudioFeatures CRUD tools for DJ workflow MCP server.

list_features — paginated list of tracks with computed features
get_features — full features for a single track (Level 3: Full, ~2 KB)
save_features — persist computed features from analyze_track
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.converters import track_to_summary
from app.mcp.dependencies import get_session
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.schemas.features import AudioFeaturesRead
from app.services.features import AudioFeaturesService

def register_features_tools(mcp: FastMCP) -> None:
    """Register AudioFeatures CRUD tools on the MCP server."""

    @mcp.tool(tags={"crud", "features"}, annotations={"readOnlyHint": True})
    async def list_features(
        limit: int = 20,
        cursor: str | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """List tracks that have computed audio features.

        Returns TrackSummary with BPM/key/energy populated from features.
        Optional BPM range filter.

        Args:
            limit: Max results per page.
            cursor: Pagination cursor.
            bpm_min: Minimum BPM filter.
            bpm_max: Maximum BPM filter.
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        features_repo = AudioFeaturesRepository(session)
        track_repo = TrackRepository(session)

        # Use filter_by_criteria if filters provided, else list_all
        if bpm_min is not None or bpm_max is not None:
            features_list, total = await features_repo.filter_by_criteria(
                bpm_min=bpm_min, bpm_max=bpm_max, offset=offset, limit=clamped,
            )
        else:
            # list_all returns all latest features — paginate manually
            all_features = await features_repo.list_all()
            total = len(all_features)
            features_list = all_features[offset : offset + clamped]

        track_ids = [f.track_id for f in features_list]
        tracks_by_id = {}
        artists_map = {}
        if track_ids:
            for tid in track_ids:
                t = await track_repo.get_by_id(tid)
                if t:
                    tracks_by_id[tid] = t
            artists_map = await track_repo.get_artists_for_tracks(track_ids)

        summaries = []
        for f in features_list:
            track = tracks_by_id.get(f.track_id)
            if track:
                summaries.append(track_to_summary(track, artists_map, features=f))

        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "features"}, annotations={"readOnlyHint": True})
    async def get_features(
        track_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Get full audio features for a track (Level 3: Full, ~2 KB).

        Returns all computed audio parameters: BPM, key, loudness, energy,
        spectral, rhythm, MFCC.

        Args:
            track_ref: Track reference (must resolve to exact ID).
        """
        ref = parse_ref(track_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "get_features requires exact ref", "ref": track_ref})

        svc = AudioFeaturesService(
            AudioFeaturesRepository(session), TrackRepository(session),
        )
        try:
            features = await svc.get_latest(ref.local_id)
        except Exception:
            return json.dumps({"error": "No features found", "ref": track_ref})

        return await wrap_detail(features, session)

    @mcp.tool(tags={"crud", "features"})
    async def save_features(
        track_ref: str,
        features_json: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Persist computed audio features for a track.

        Use after analyze_track() to save the computed result to DB.
        Creates a new feature extraction run.

        Args:
            track_ref: Track reference (must resolve to exact ID).
            features_json: JSON string with feature values from analyze_track output.
        """
        ref = parse_ref(track_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "save_features requires exact ref", "ref": track_ref})

        features_data = json.loads(features_json)

        # Create a feature extraction run and save
        from app.repositories.runs import FeatureExtractionRunRepository

        run_repo = FeatureExtractionRunRepository(session)
        run = await run_repo.create(status="completed")

        features_repo = AudioFeaturesRepository(session)
        from app.utils.audio.types import TrackFeatures

        track_features = TrackFeatures(**features_data)
        await features_repo.save_features(ref.local_id, run.run_id, track_features)

        return await wrap_action(
            success=True,
            message=f"Saved features for track local:{ref.local_id}",
            session=session,
        )
```

**Note:** The `save_features` implementation may need adjustment based on the exact `FeatureExtractionRunRepository` interface and `TrackFeatures` dataclass structure. Check `app/repositories/runs.py` and `app/utils/audio/types.py` before implementing.

**Step 4: Register, run tests, lint, commit**

```bash
git commit -m "feat(mcp): add AudioFeatures CRUD tools — list/get/save with BPM filter + full features view"
```

---

## Task 7: Compute-Only analyze_track Tool

**Files:**
- Create: `app/mcp/workflows/compute_tools.py`
- Test: `tests/mcp/test_compute_tools.py`
- Modify: `app/mcp/workflows/server.py` — register

NEW tool (not a refactor). `analyze_track` runs the full audio analysis pipeline and returns results WITHOUT saving to DB. Agent calls `save_features` (Task 6) separately to persist.

**Step 1: Write failing tests**

```python
# tests/mcp/test_compute_tools.py
"""Tests for compute-only tools (no DB writes)."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_analyze_track_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "analyze_track" in names

async def test_analyze_track_no_file(workflow_mcp):
    """analyze_track with nonexistent track should return error."""
    async with Client(workflow_mcp) as client:
        result = await client.call_tool(
            "analyze_track", {"track_ref": "local:99999"}
        )
        data = json.loads(result[0].text)
        assert "error" in data
```

**Step 2: Run, fail**

**Step 3: Implement analyze_track**

```python
# app/mcp/workflows/compute_tools.py
"""Compute-only tools — return data without DB writes.

Agent decides when to persist results using save_features / create_set.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.dependencies import get_session
from app.mcp.refs import RefType, parse_ref
from app.repositories.dj_library_items import DjLibraryItemRepository
from app.repositories.tracks import TrackRepository

def register_compute_tools(mcp: FastMCP) -> None:
    """Register compute-only tools on the MCP server."""

    @mcp.tool(tags={"compute", "analysis"})
    async def analyze_track(
        track_ref: str | None = None,
        audio_path: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Run full audio analysis pipeline on a track. Returns features WITHOUT saving.

        Accepts either track_ref (resolves to local file) or direct audio_path.
        To persist results, call save_features() with the returned data.

        Requires audio dependencies (essentia, soundfile, scipy).

        Args:
            track_ref: Track reference to analyze (resolves to local file via DjLibraryItem).
            audio_path: Direct path to audio file (alternative to track_ref).
        """
        # Resolve audio file path
        file_path: str | None = audio_path

        if track_ref and not file_path:
            ref = parse_ref(track_ref)
            if ref.ref_type != RefType.LOCAL or ref.local_id is None:
                return json.dumps({"error": "analyze requires local track ref or audio_path"})

            # Look up file path from DjLibraryItem
            lib_repo = DjLibraryItemRepository(session)
            lib_item = await lib_repo.get_by_track(ref.local_id)
            if lib_item is None:
                return json.dumps({
                    "error": "No local file found for track",
                    "ref": track_ref,
                    "hint": "Download the track first using download_tracks",
                })
            file_path = lib_item.file_path

        if not file_path:
            return json.dumps({"error": "Provide track_ref or audio_path"})

        # Run analysis pipeline (imports are heavy — lazy load)
        try:
            from app.services.track_analysis import TrackAnalysisService
            from app.repositories.audio_features import AudioFeaturesRepository
            from app.repositories.sections import SectionsRepository

            analysis_svc = TrackAnalysisService(
                TrackRepository(session),
                AudioFeaturesRepository(session),
                SectionsRepository(session),
            )
            # Use the service's analysis logic but DON'T persist
            # The service.analyze_track() both computes AND saves.
            # We need to call the underlying audio utils directly.
            from app.utils.audio import load_audio
            from app.utils.audio.pipeline import run_full_analysis

            audio_data = load_audio(file_path)
            features = run_full_analysis(audio_data)

            # Return computed features as JSON (agent calls save_features to persist)
            return json.dumps({
                "track_ref": track_ref,
                "audio_path": file_path,
                "features": features.to_dict(),
                "hint": "Call save_features(track_ref, features_json) to persist these results",
            }, ensure_ascii=False)

        except ImportError as e:
            return json.dumps({
                "error": f"Audio dependencies not available: {e}",
                "hint": "Install with: uv sync --extra audio",
            })
        except Exception as e:
            return json.dumps({"error": f"Analysis failed: {e}"})
```

**Important implementation note:** The exact import paths for `load_audio` and `run_full_analysis` may differ. Check:
- `app/utils/audio/__init__.py` for the audio loading function
- `app/services/track_analysis.py` for how the analysis pipeline is currently called
- Adapt the implementation to call the same underlying functions without the DB persist step.

**Step 4: Register, run tests, lint, commit**

```bash
git commit -m "feat(mcp): add analyze_track compute tool — returns features without DB persist"
```

---

## Task 8: Compute-Only build_set

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py`
- Test: `tests/mcp/test_setbuilder_v2.py`

Refactor `build_set` to be compute-only: runs GA optimization, returns result, does NOT create DjSet/Version/Items. Agent calls `create_set(name, track_ids=[...])` (Task 5) to persist.

**Step 1: Write failing test**

```python
# tests/mcp/test_setbuilder_v2.py
"""Tests for refactored build_set (compute-only)."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_build_set_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "build_set" in names

async def test_build_set_uses_refs(workflow_mcp):
    """build_set should accept playlist_ref instead of playlist_id."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        build_set_tool = next(t for t in tools if t.name == "build_set")
        # Check parameter names
        param_names = [p.name for p in (build_set_tool.inputSchema.get("properties", {}).keys())]
        # Should have playlist_ref, not playlist_id
        # (exact check depends on FastMCP schema format)
```

**Step 2: Run, fail**

**Step 3: Refactor build_set**

In `app/mcp/workflows/setbuilder_tools.py`, change `build_set`:

**Before (current — creates DjSet in DB):**
```python
async def build_set(
    playlist_id: int,
    set_name: str,
    ...
) -> SetBuildResult:
    # Creates DjSet, runs GA, creates DjSetVersion + Items
```

**After (compute-only — returns result, no DB writes):**
```python
@mcp.tool(tags={"compute", "setbuilder"})
async def build_set(
    playlist_ref: str,
    template: str | None = None,
    energy_arc: str = "progressive",
    exclude_refs: list[str] | None = None,
    limit: int = 60,
    session: AsyncSession = Depends(get_session),
) -> str:
    """Run GA optimization to build optimal track order. Returns result WITHOUT saving.

    Reads features from DB, runs genetic algorithm, returns optimized track order
    with transition scores and energy curve. Does NOT create a DJ set.

    To persist: call create_set(name="...", track_ids=[...]) with the returned track_ids.

    Args:
        playlist_ref: Source playlist containing candidate tracks.
        template: Optional template name (e.g., "classic_60", "warm_up_30").
        energy_arc: Energy arc type — "progressive", "wave", "peak_valley".
        exclude_refs: Optional list of track refs to exclude from selection.
        limit: Target number of tracks in the set (default 60).
    """
    # Resolve playlist_ref
    ref = parse_ref(playlist_ref)
    if ref.ref_type != RefType.LOCAL or ref.local_id is None:
        return json.dumps({"error": "build_set requires local playlist ref"})

    playlist_id = ref.local_id

    # Resolve exclude refs to track IDs
    exclude_ids: list[int] = []
    if exclude_refs:
        for eref in exclude_refs:
            parsed = parse_ref(eref)
            if parsed.ref_type == RefType.LOCAL and parsed.local_id is not None:
                exclude_ids.append(parsed.local_id)

    # Run GA — read features, optimize order
    from app.services.set_generation import SetGenerationService, SetGenerationRequest

    gen_svc = SetGenerationService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
        DjPlaylistItemRepository(session),
    )

    # Use compute-only method (if exists) or adapt generate()
    # The key change: we don't pass a set_id and don't create version/items
    request = SetGenerationRequest(
        playlist_id=playlist_id,
        template_name=template,
        energy_arc_type=energy_arc,
        exclude_track_ids=exclude_ids,
        target_count=limit,
    )

    # NOTE: SetGenerationService.generate() currently requires set_id and creates
    # DjSetVersion + Items. We need to add a compute_only() method or refactor.
    # Option A: Add compute_only(request) -> SetComputeResult to the service
    # Option B: Create a temporary set, run GA, extract results, delete set
    # Recommended: Option A — cleaner, add the method to SetGenerationService

    result = await gen_svc.compute(request)  # NEW METHOD — returns data only

    return json.dumps({
        "track_ids": result.track_ids,
        "track_count": len(result.track_ids),
        "total_score": result.total_score,
        "avg_transition_score": result.avg_transition_score,
        "energy_curve": result.energy_curve,
        "hint": "Call create_set(name='...', track_ids=[...]) to persist this result",
    }, ensure_ascii=False)
```

**Step 4: Add `compute()` method to SetGenerationService**

In `app/services/set_generation.py`, add a new method that runs GA without persisting:

```python
async def compute(self, request: SetGenerationRequest) -> SetComputeResult:
    """Run GA optimization and return result without persisting.

    Same logic as generate() but skips DjSetVersion/Item creation.
    """
    # ... (same feature loading and GA logic as generate())
    # Return computed result instead of saving to DB
    return SetComputeResult(
        track_ids=optimized_track_ids,
        total_score=total_score,
        avg_transition_score=avg_transition_score,
        energy_curve=energy_curve,
    )
```

Add `SetComputeResult` dataclass/Pydantic model:

```python
class SetComputeResult(BaseModel):
    track_ids: list[int]
    total_score: float
    avg_transition_score: float
    energy_curve: list[float]
```

**Step 5: Run tests, lint, commit**

```bash
git commit -m "feat(mcp): refactor build_set to compute-only — returns result without DB writes"
```

---

## Task 9: Unified export_set

**Files:**
- Modify: `app/mcp/workflows/export_tools.py`
- Test: `tests/mcp/test_export_unified.py`
- Modify: `app/mcp/workflows/server.py` — update registration

Merge `export_set_m3u`, `export_set_json`, `export_set_rekordbox` into one `export_set(format=...)` tool. Uses refs for set identification.

**Step 1: Write failing test**

```python
# tests/mcp/test_export_unified.py
"""Tests for unified export_set tool."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_export_set_registered(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "export_set" in names
        # Old tools should be removed
        assert "export_set_m3u" not in names
        assert "export_set_json" not in names
        assert "export_set_rekordbox" not in names
```

**Step 2: Run, fail**

**Step 3: Implement unified export_set**

In `app/mcp/workflows/export_tools.py`, replace the three separate tools with one:

```python
def register_export_tools(mcp: FastMCP) -> None:
    """Register export tools on the MCP server."""

    @mcp.tool(tags={"export"}, annotations={"readOnlyHint": True})
    async def export_set(
        set_ref: str,
        format: str = "m3u",
        version_id: int | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Export a DJ set to file.

        Generates an export file in the specified format.
        Uses the latest version if version_id not specified.

        Args:
            set_ref: Set reference (local:3 or 3).
            format: Export format — "m3u", "json", or "rekordbox".
            version_id: Specific version to export (default: latest).
        """
        ref = parse_ref(set_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "export requires exact set ref"})

        set_id = ref.local_id

        # Resolve version_id if not provided
        if version_id is None:
            svc = DjSetService(...)
            versions = await svc.list_versions(set_id)
            if not versions.items:
                return json.dumps({"error": "Set has no versions"})
            version_id = versions.items[-1].set_version_id

        export_svc = SetExportService(...)

        if format == "m3u":
            result = await export_svc.export_m3u(set_id, version_id)
        elif format == "json":
            result = await export_svc.export_json(set_id, version_id)
        elif format == "rekordbox":
            result = await export_svc.export_rekordbox(set_id, version_id)
        else:
            return json.dumps({"error": f"Unknown format: {format}. Use m3u, json, or rekordbox"})

        return json.dumps({
            "format": result.format,
            "file_path": result.file_path,
            "track_count": result.track_count,
            "duration_ms": result.duration_ms,
        }, ensure_ascii=False)
```

**Note:** The DI and service construction should follow the existing patterns in `export_tools.py`. Adapt the constructor calls based on what the current `SetExportService` requires.

**Step 4: Update server.py — remove old individual export registrations**

The `register_export_tools` function now only registers `export_set`.

**Step 5: Run tests, lint, commit**

```bash
git commit -m "feat(mcp): unify 3 export tools into export_set(format=m3u|json|rekordbox)"
```

---

## Task 10: Refactor Remaining Orchestrators

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py` — score_transitions uses refs
- Modify: `app/mcp/workflows/curation_tools.py` — classify_tracks, review_set, analyze_library_gaps use refs + types_v2
- Modify: `app/mcp/workflows/discovery_tools.py` — find_similar_tracks uses refs
- Test: `tests/mcp/test_orchestrator_refs.py`

Update remaining orchestrator tools to accept refs instead of raw IDs and return types_v2 response envelope.

**Step 1: Write failing tests**

```python
# tests/mcp/test_orchestrator_refs.py
"""Tests for orchestrator tools with ref support."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_score_transitions_uses_refs(workflow_mcp):
    """score_transitions should accept set_ref instead of set_id."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "score_transitions")
        props = tool.inputSchema.get("properties", {})
        assert "set_ref" in props or "set_id" in props  # transitional

async def test_classify_tracks_returns_envelope(workflow_mcp):
    """classify_tracks should return types_v2 envelope with library stats."""
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("classify_tracks", {})
        data = json.loads(result[0].text)
        # Should have library context
        assert "library" in data or "total_classified" in data
```

**Step 2: Run, fail**

**Step 3: Refactor each tool**

For each tool, the changes are:
1. Replace `set_id: int` → `set_ref: str`, parse with `parse_ref()`
2. Replace `playlist_id: int` → `playlist_ref: str`, parse with `parse_ref()`
3. Wrap return value in response envelope (add library stats)
4. Replace old types (`PlaylistStatus`, `TrackDetails`) with types_v2 models

**score_transitions** in `setbuilder_tools.py`:
```python
# Before:
async def score_transitions(set_id: int, version_id: int, ...) -> list[TransitionScoreResult]:

# After:
async def score_transitions(set_ref: str, version_id: int | None = None, ...) -> str:
    ref = parse_ref(set_ref)
    # ... resolve set_id, resolve latest version if version_id is None
    # ... same scoring logic
    # Wrap result
    return json.dumps({
        "transitions": [t.model_dump() for t in scores],
        "summary": {"avg_score": avg, "weak_count": weak_count},
        "library": library.model_dump(),
    }, ensure_ascii=False)
```

**classify_tracks** in `curation_tools.py`:
```python
# Before:
async def classify_tracks(...) -> ClassifyResult:

# After:
async def classify_tracks(session=Depends(get_session), ...) -> str:
    # Same logic, wrap result
    return json.dumps({
        "result": classify_result.model_dump(),
        "library": library.model_dump(),
    }, ensure_ascii=False)
```

**review_set** — same pattern: `set_id` → `set_ref`, wrap with envelope.

**analyze_library_gaps** — no ref needed (analyzes whole library), just add envelope.

**find_similar_tracks** — `playlist_id` → `playlist_ref`.

**rebuild_set** — `set_id` → `set_ref`.

**Step 4: Run all tests, fix any regressions**

Run: `uv run pytest tests/mcp/ -v`

**Step 5: Lint + commit**

```bash
git commit -m "refactor(mcp): update orchestrator tools to accept refs + return types_v2 envelope"
```

---

## Task 11: Remove Stubs + Update Registration

**Files:**
- Modify: `app/mcp/workflows/server.py` — new registration order
- Modify: `app/mcp/workflows/import_tools.py` — remove import_playlist, import_tracks stubs
- Delete or gut: `app/mcp/workflows/sync_tools.py` — remove sync stubs (Phase 3)
- Modify: `app/mcp/workflows/analysis_tools.py` — remove `get_playlist_status`, `get_track_details` (replaced by CRUD)
- Modify: `app/mcp/workflows/discovery_tools.py` — remove `search_by_criteria` (replaced by `filter_tracks` from Phase 1)
- Test: `tests/mcp/test_tool_inventory.py`

**Step 1: Write the inventory test**

```python
# tests/mcp/test_tool_inventory.py
"""Verify the complete tool inventory after Phase 2."""

from __future__ import annotations

from fastmcp import Client

async def test_expected_tools_present(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}

        # CRUD tools (Phase 2)
        crud_expected = {
            "list_tracks", "get_track", "create_track", "update_track", "delete_track",
            "list_playlists", "get_playlist", "create_playlist", "update_playlist", "delete_playlist",
            "list_sets", "get_set", "create_set", "update_set", "delete_set",
            "list_features", "get_features", "save_features",
        }
        for tool in crud_expected:
            assert tool in names, f"Missing CRUD tool: {tool}"

        # Orchestrators (kept/refactored)
        orchestrators_expected = {
            "search", "filter_tracks",  # Phase 1
            "analyze_track",  # Phase 2 compute
            "build_set", "rebuild_set", "score_transitions",  # setbuilder
            "export_set",  # unified export
            "classify_tracks", "analyze_library_gaps", "review_set",  # curation
            "download_tracks",  # action
            "find_similar_tracks",  # discovery
        }
        for tool in orchestrators_expected:
            assert tool in names, f"Missing orchestrator: {tool}"

        # Admin
        assert "activate_heavy_mode" in names

async def test_removed_tools_absent(workflow_mcp):
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}

        removed = {
            # Stubs (removed)
            "import_playlist", "import_tracks",
            "sync_set_to_ym", "sync_set_from_ym", "sync_playlist",
            # Replaced by CRUD
            "get_playlist_status", "get_track_details",
            # Replaced by filter_tracks
            "search_by_criteria",
            # Replaced by unified export_set
            "export_set_m3u", "export_set_json", "export_set_rekordbox",
        }
        for tool in removed:
            assert tool not in names, f"Tool should be removed: {tool}"
```

**Step 2: Run, fail (stubs still present)**

**Step 3: Remove stubs and replaced tools**

**In `import_tools.py`:** Remove `import_playlist` and `import_tracks` tool registrations. Keep `download_tracks` (it's a real tool, not a stub). Update `register_import_tools` to only register `download_tracks`.

**In `sync_tools.py`:** Remove all 3 stub tools (`sync_set_to_ym`, `sync_set_from_ym`, `sync_playlist`). Either delete the file or leave `register_sync_tools` as empty function. They'll be properly implemented in Phase 3.

**In `analysis_tools.py`:** Remove `get_playlist_status` and `get_track_details` (replaced by `get_playlist` and `get_track` CRUD tools). If the file becomes empty, remove `register_analysis_tools` call from server.py.

**In `discovery_tools.py`:** Remove `search_by_criteria` (replaced by `filter_tracks` from Phase 1). Keep `find_similar_tracks`.

**Step 4: Update server.py registration**

```python
def create_workflow_mcp() -> FastMCP:
    mcp = FastMCP("DJ Workflows")

    # Phase 1: Search + Filter
    register_search_tools(mcp)

    # Phase 2: CRUD
    register_track_tools(mcp)
    register_playlist_tools(mcp)
    register_set_tools(mcp)
    register_features_tools(mcp)

    # Phase 2: Compute
    register_compute_tools(mcp)

    # Orchestrators (refactored)
    register_setbuilder_tools(mcp)
    register_export_tools(mcp)
    register_curation_tools(mcp)
    register_discovery_tools(mcp)

    # Remaining (download only)
    register_import_tools(mcp)

    # MCP prompts + resources
    register_prompts(mcp)
    register_resources(mcp)

    # Visibility
    _register_visibility_tools(mcp)
    mcp.disable(tags={"heavy"})

    return mcp
```

**Step 5: Run tests, verify inventory matches**

Run: `uv run pytest tests/mcp/test_tool_inventory.py -v`

**Step 6: Run full test suite to catch regressions**

Run: `uv run pytest tests/ -v`

**Step 7: Lint + commit**

```bash
git commit -m "refactor(mcp): remove 8 stubs/replaced tools, update registration for Phase 2 CRUD"
```

---

## Task 12: Integration Tests

**Files:**
- Create: `tests/mcp/test_crud_integration.py`
- Create: `tests/mcp/test_compute_persist_integration.py`

End-to-end tests verifying the full CRUD cycle and compute/persist split with real DB.

**Step 1: Write CRUD integration test**

```python
# tests/mcp/test_crud_integration.py
"""Integration tests — full CRUD cycle with DB."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_track_crud_cycle(workflow_mcp, session):
    """Create → Get → Update → List → Delete a track."""
    async with Client(workflow_mcp) as client:
        # Create
        result = await client.call_tool("create_track", {
            "title": "Test Track", "duration_ms": 300000,
        })
        data = json.loads(result[0].text)
        assert data["success"] is True
        track_ref = data["result"]["ref"]
        assert track_ref.startswith("local:")

        # Get
        result = await client.call_tool("get_track", {"track_ref": track_ref})
        data = json.loads(result[0].text)
        assert data["result"]["title"] == "Test Track"

        # Update
        result = await client.call_tool("update_track", {
            "track_ref": track_ref, "title": "Updated Track",
        })
        data = json.loads(result[0].text)
        assert data["result"]["title"] == "Updated Track"

        # List
        result = await client.call_tool("list_tracks", {"search": "Updated"})
        data = json.loads(result[0].text)
        assert data["total"] >= 1

        # Delete
        result = await client.call_tool("delete_track", {"track_ref": track_ref})
        data = json.loads(result[0].text)
        assert data["success"] is True

        # Verify deleted
        result = await client.call_tool("get_track", {"track_ref": track_ref})
        data = json.loads(result[0].text)
        assert "error" in data

async def test_set_crud_with_tracks(workflow_mcp, session):
    """Create set with track_ids populates version + items."""
    from app.models.catalog import Track

    # Setup: create tracks directly in DB
    t1 = Track(title="Track A", duration_ms=300000)
    t2 = Track(title="Track B", duration_ms=200000)
    session.add_all([t1, t2])
    await session.flush()

    async with Client(workflow_mcp) as client:
        result = await client.call_tool("create_set", {
            "name": "Test Set",
            "track_ids": [t1.track_id, t2.track_id],
        })
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["result"]["track_count"] == 2
        assert data["result"]["version_count"] == 1
```

**Step 2: Write compute/persist split integration test**

```python
# tests/mcp/test_compute_persist_integration.py
"""Integration tests — compute/persist split."""

from __future__ import annotations

import json

from fastmcp import Client

async def test_build_set_does_not_persist(workflow_mcp, session):
    """build_set returns result but does NOT create DjSet in DB."""
    from app.models.dj import DjPlaylist, DjPlaylistItem
    from app.models.catalog import Track
    from app.models.features import TrackAudioFeaturesComputed
    from sqlalchemy import select, func

    # Setup: playlist with tracks that have features
    playlist = DjPlaylist(name="Test Playlist", source_app=1)
    session.add(playlist)
    await session.flush()

    # Create tracks with features (minimal setup)
    # ... (add tracks + features + playlist items)

    # Count sets before
    count_before = (await session.execute(
        select(func.count()).select_from(DjSet)
    )).scalar_one()

    async with Client(workflow_mcp) as client:
        result = await client.call_tool("build_set", {
            "playlist_ref": f"local:{playlist.playlist_id}",
        })
        data = json.loads(result[0].text)

        # Should return computed result
        assert "track_ids" in data or "error" in data

    # Count sets after — should be same (nothing persisted)
    count_after = (await session.execute(
        select(func.count()).select_from(DjSet)
    )).scalar_one()
    assert count_after == count_before
```

**Step 3: Run integration tests**

Run: `uv run pytest tests/mcp/test_crud_integration.py tests/mcp/test_compute_persist_integration.py -v`

**Note:** Integration tests require the DB fixtures from `tests/conftest.py` and `tests/mcp/conftest.py`. The `session` fixture creates tables in-memory. The `workflow_mcp` fixture creates the MCP server. You may need to configure dependency overrides so MCP tools use the test session.

**Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 5: Lint + commit**

```bash
git commit -m "test(mcp): add CRUD integration tests + compute/persist split verification"
```

---

## Summary

| Task | Component | Files | Est. |
|------|-----------|-------|------|
| 1 | Response envelopes + wrappers | 2 new + 1 mod | 15 min |
| 2 | ORM-to-Response converters | 2 new + 1 mod | 20 min |
| 3 | Track CRUD tools (5 tools) | 2 new + 1 mod | 25 min |
| 4 | Playlist CRUD tools (5 tools) | 2 new + 1 mod | 25 min |
| 5 | Set CRUD tools (5 tools) | 2 new + 1 mod | 30 min |
| 6 | AudioFeatures CRUD (3 tools) | 2 new + 1 mod | 20 min |
| 7 | analyze_track compute tool | 2 new + 1 mod | 25 min |
| 8 | build_set compute-only | 2 mod + 1 test | 30 min |
| 9 | Unified export_set | 1 mod + 1 test | 20 min |
| 10 | Refactor orchestrators (refs + envelope) | 4 mod + 1 test | 30 min |
| 11 | Remove stubs + registration | 5 mod + 1 test | 20 min |
| 12 | Integration tests | 2 new | 20 min |

**Total: ~12 tasks, ~4.5 hours estimated**

**What changes:**
- 18 new CRUD tools (5 Track + 5 Playlist + 5 Set + 3 Features)
- 1 new compute tool (analyze_track)
- 3 refactored tools (build_set, score_transitions, export_set)
- 5 refactored tools (classify_tracks, review_set, analyze_library_gaps, find_similar_tracks, rebuild_set)
- 8 removed tools (2 import stubs, 3 sync stubs, 2 replaced analysis tools, 1 replaced discovery tool)
- 3 merged into 1 (3 export → export_set)

**What stays unchanged:**
- `download_tracks` — action tool, works as-is
- `activate_heavy_mode` — admin, works as-is
- Phase 1 tools (search, filter_tracks) — already using new patterns
- Audio namespace (Phase 1) — hidden compute tools
- YM namespace — raw API access, unchanged

**Prerequisite:** Phase 1 must be implemented first (types_v2, pagination, refs, entity_finder, library_stats, search/filter tools, audio namespace, YM visibility).

**Next:** Phase 3 (Multi-platform abstraction + SyncEngine) builds on CRUD tools with platform adapters.
