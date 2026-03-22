# MCP Redesign Phase 0 + Phase 1 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Построить фундаментальный слой agent-first MCP редизайна: test harness, PlatformKey, response models (schemas), URN ref parser, entity resolvers, cursor pagination, library stats, и два инструмента (search + filter_tracks).

**Architecture:** Новые модули (`app/mcp/schemas.py`, `app/mcp/refs.py`, `app/mcp/resolvers.py`, `app/mcp/pagination.py`, `app/mcp/stats.py`, `app/mcp/converters.py`, `app/mcp/platforms/keys.py`, `app/mcp/tools/search.py`) сидят рядом с существующим кодом. Никаких breaking changes — новые инструменты добавляются, старые не трогаются до Phase 2.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest + pytest-asyncio

**Design doc:** `docs/plans/2026-02-19-mcp-redesign-analysis.md`

**Key patterns in this codebase:**
- **MCP DI:** `from fastmcp.dependencies import Depends` (НЕ FastAPI)
- **Tool results:** Pydantic models → `result.data` в тестах (НЕ `result[0].text`)
- **Tool errors:** `raise ToolError(msg)` → `pytest.raises(ToolError)` в тестах
- **Repos:** `BaseRepository[ModelT: Base]` → `list(offset, limit, filters) → tuple[list[T], int]`
- **Tests:** Server fixture + `async with Client(server)` в теле теста
- **Asyncio:** `asyncio_mode = "auto"` — НЕ нужен `@pytest.mark.asyncio`

---

## Phase 0: Prerequisites

---

### Task 1: MCP Test Harness — session override

**Files:**
- Modify: `tests/mcp/conftest.py`
- Test: `tests/mcp/test_harness.py`

MCP tools используют `app.mcp.dependencies.get_session()`, который создаёт сессию из `app.database.session_factory` (production). Тесты пишут в in-memory SQLite. Без override MCP tools не видят тестовые данные.

**Step 1: Write the failing test**

```python
# tests/mcp/test_harness.py
"""Tests for MCP test harness — verify tools can read test DB data."""

from __future__ import annotations

from fastmcp import Client

from app.models.tracks import Track

async def test_mcp_tool_reads_test_db(workflow_mcp_with_db, session):
    """Tool should see data written to test session."""
    # Seed a track into the test DB
    track = Track(title="Test Track", title_sort="test track", duration_ms=180000, status=0)
    session.add(track)
    await session.flush()

    async with Client(workflow_mcp_with_db) as client:
        result = await client.call_tool(
            "get_track_details",
            {"track_id": track.track_id},
        )
        assert not result.is_error
        assert result.data.track_id == track.track_id
        assert result.data.title == "Test Track"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_harness.py::test_mcp_tool_reads_test_db -v
```

Expected: FAIL — `workflow_mcp_with_db` fixture not found.

**Step 3: Implement the fixture**

```python
# tests/mcp/conftest.py — add to existing fixtures
import contextlib
from collections.abc import AsyncIterator
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp.workflows import create_workflow_mcp

@pytest.fixture
async def workflow_mcp_with_db(engine) -> FastMCP:
    """DJ Workflows MCP server wired to test DB.

    Override ``app.mcp.dependencies.get_session`` so that every MCP tool
    call uses the same in-memory SQLite engine as the test ``session`` fixture.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _test_session() -> AsyncIterator[AsyncSession]:
        async with factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    with patch("app.mcp.dependencies.get_session", _test_session):
        yield create_workflow_mcp()
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/mcp/test_harness.py::test_mcp_tool_reads_test_db -v
```

Expected: PASS

**Step 5: Add gateway variant**

```python
# tests/mcp/conftest.py — add gateway_mcp_with_db fixture
from app.mcp import create_dj_mcp

@pytest.fixture
async def gateway_mcp_with_db(engine) -> FastMCP:
    """Full gateway MCP server wired to test DB."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _test_session() -> AsyncIterator[AsyncSession]:
        async with factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    with patch("app.mcp.dependencies.get_session", _test_session):
        yield create_dj_mcp()
```

**Step 6: Commit**

```bash
git add tests/mcp/conftest.py tests/mcp/test_harness.py
git commit -m "feat(mcp): add test harness — DB-wired MCP fixtures

workflow_mcp_with_db and gateway_mcp_with_db override get_session
so MCP tools can read/write the test in-memory SQLite engine."
```

---

### Task 2: PlatformKey enum

**Files:**
- Create: `app/mcp/platforms/__init__.py`
- Create: `app/mcp/platforms/keys.py`
- Test: `tests/mcp/platforms/__init__.py`
- Test: `tests/mcp/platforms/test_keys.py`

Решает проблему `ym` vs `yandex_music` vs `yandex` — единый источник истины для platform key → provider_code mapping.

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/__init__.py
```

```python
# tests/mcp/platforms/test_keys.py
"""Tests for PlatformKey — canonical key ↔ provider_code mapping."""

from __future__ import annotations

import pytest

from app.mcp.platforms.keys import PlatformKey

class TestPlatformKey:
    def test_ym_key(self):
        assert PlatformKey.YM.value == "ym"

    def test_ym_provider_code(self):
        assert PlatformKey.YM.provider_code == "yandex_music"

    def test_ym_display_name(self):
        assert PlatformKey.YM.display_name == "Yandex Music"

    def test_from_provider_code(self):
        key = PlatformKey.from_provider_code("yandex_music")
        assert key is PlatformKey.YM

    def test_from_provider_code_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider_code"):
            PlatformKey.from_provider_code("tidal")

    def test_from_ref_prefix(self):
        key = PlatformKey.from_ref_prefix("ym")
        assert key is PlatformKey.YM

    def test_from_ref_prefix_unknown(self):
        with pytest.raises(ValueError, match="Unknown ref prefix"):
            PlatformKey.from_ref_prefix("tidal")

    def test_all_keys_have_provider_code(self):
        for key in PlatformKey:
            assert key.provider_code, f"{key} has no provider_code"

    def test_spotify_future(self):
        """Spotify is declared but not connected."""
        assert PlatformKey.SPOTIFY.value == "spotify"
        assert PlatformKey.SPOTIFY.provider_code == "spotify"
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/platforms/test_keys.py -v
```

Expected: FAIL — module not found.

**Step 3: Implement PlatformKey**

```python
# app/mcp/platforms/__init__.py
"""Multi-platform abstractions."""

from app.mcp.platforms.keys import PlatformKey

__all__ = ["PlatformKey"]
```

```python
# app/mcp/platforms/keys.py
"""Canonical platform key ↔ DB provider_code mapping.

Resolves the ym / yandex_music / yandex inconsistency across the codebase.
Platform keys are short strings used in URN refs (``ym:12345``).
Provider codes match ``providers.provider_code`` in the DB.
"""

from __future__ import annotations

from enum import Enum

class PlatformKey(Enum):
    """Canonical platform identifiers."""

    YM = "ym"
    SPOTIFY = "spotify"
    BEATPORT = "beatport"
    SOUNDCLOUD = "soundcloud"

    def __init__(self, value: str) -> None:
        self._value_ = value
        self._provider_code = _PROVIDER_CODES.get(value, value)
        self._display_name = _DISPLAY_NAMES.get(value, value)

    @property
    def provider_code(self) -> str:
        """DB ``providers.provider_code`` for this platform."""
        return self._provider_code

    @property
    def display_name(self) -> str:
        """Human-readable platform name."""
        return self._display_name

    @classmethod
    def from_provider_code(cls, code: str) -> PlatformKey:
        """Resolve DB provider_code → PlatformKey."""
        for key in cls:
            if key.provider_code == code:
                return key
        msg = f"Unknown provider_code: {code!r}"
        raise ValueError(msg)

    @classmethod
    def from_ref_prefix(cls, prefix: str) -> PlatformKey:
        """Resolve URN prefix → PlatformKey."""
        try:
            return cls(prefix)
        except ValueError:
            msg = f"Unknown ref prefix: {prefix!r}"
            raise ValueError(msg) from None

# Internal mappings — platform key → provider_code (DB column)
_PROVIDER_CODES: dict[str, str] = {
    "ym": "yandex_music",
    "spotify": "spotify",
    "beatport": "beatport",
    "soundcloud": "soundcloud",
}

_DISPLAY_NAMES: dict[str, str] = {
    "ym": "Yandex Music",
    "spotify": "Spotify",
    "beatport": "Beatport",
    "soundcloud": "SoundCloud",
}
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/platforms/test_keys.py -v
```

Expected: PASS

**Step 5: Lint**

```bash
uv run ruff check app/mcp/platforms/ tests/mcp/platforms/ && uv run mypy app/mcp/platforms/
```

**Step 6: Commit**

```bash
git add app/mcp/platforms/ tests/mcp/platforms/
git commit -m "feat(mcp): add PlatformKey enum — ym ↔ yandex_music mapping

Resolves platform key inconsistency (ym/yandex_music/yandex).
Single source of truth for ref prefix ↔ DB provider_code."
```

---

## Phase 1: Foundation

---

### Task 3: Response Models (`schemas.py`)

**Files:**
- Create: `app/mcp/schemas.py`
- Test: `tests/mcp/test_schemas.py`

Three response levels (Summary/Detail) + envelope models (LibraryStats, PaginationInfo, FindResult, SearchResponse).

**Step 1: Write the failing tests**

```python
# tests/mcp/test_schemas.py
"""Tests for MCP response models — summary, detail, envelope."""

from __future__ import annotations

from app.mcp.schemas import (
    ArtistSummary,
    FindResult,
    LibraryStats,
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
        assert t.key is None

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
        )
        assert t.bpm == 140.0
        assert t.mood == "peak_time"

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
        # Inherits from TrackSummary
        assert d.bpm == 140.0

class TestPlaylistSummary:
    def test_create(self):
        p = PlaylistSummary(ref="local:5", name="Techno develop", track_count=247)
        assert p.track_count == 247

class TestSetSummary:
    def test_create(self):
        s = SetSummary(ref="local:3", name="Friday night", version_count=2, track_count=15)
        assert s.version_count == 2

class TestArtistSummary:
    def test_create(self):
        a = ArtistSummary(ref="local:10", name="Boris Brejcha", tracks_in_db=5)
        assert a.tracks_in_db == 5

class TestLibraryStats:
    def test_create(self):
        s = LibraryStats(
            total_tracks=3247, analyzed_tracks=2890, total_playlists=15, total_sets=8
        )
        assert s.total_tracks == 3247

class TestPaginationInfo:
    def test_no_more(self):
        p = PaginationInfo(limit=20, offset=0, total=5, has_more=False)
        assert p.cursor is None

    def test_has_more(self):
        p = PaginationInfo(limit=20, offset=0, total=50, has_more=True, cursor="abc")
        assert p.cursor == "abc"

class TestFindResult:
    def test_exact_match(self):
        f = FindResult(
            exact=True,
            entities=[TrackSummary(ref="local:42", title="Gravity", artist="Boris Brejcha")],
            source="local",
        )
        assert len(f.entities) == 1
        assert f.exact is True

    def test_text_search(self):
        f = FindResult(
            exact=False,
            entities=[
                TrackSummary(ref="local:1", title="Gravity", artist="Boris Brejcha"),
                TrackSummary(ref="local:2", title="Gravity (Remix)", artist="Ann Clue"),
            ],
            source="local",
        )
        assert len(f.entities) == 2
        assert f.exact is False

class TestSearchResponse:
    def test_create(self):
        r = SearchResponse(
            results={"tracks": [], "playlists": []},
            stats={"tracks": 0, "playlists": 0},
            library=LibraryStats(
                total_tracks=100, analyzed_tracks=80, total_playlists=5, total_sets=3
            ),
            pagination=PaginationInfo(limit=20, offset=0, total=0, has_more=False),
        )
        assert r.library.total_tracks == 100
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/test_schemas.py -v
```

Expected: FAIL — module not found.

**Step 3: Implement schemas.py**

```python
# app/mcp/schemas.py
"""MCP response models — Summary / Detail levels + envelope.

Summary: ~150 bytes per entity (for lists, search results).
Detail: ~300 bytes per entity (for get_*, includes metadata).

These replace ``types.py`` and ``types_curation.py`` (Phase 4 cleanup).
"""

from __future__ import annotations

from pydantic import BaseModel

# ─── Entity Summary (for lists, search) ───

class TrackSummary(BaseModel):
    """Track at summary level — enough for agent to identify and compare."""

    ref: str
    title: str
    artist: str
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None
    duration_ms: int | None = None
    mood: str | None = None

class PlaylistSummary(BaseModel):
    """Playlist at summary level."""

    ref: str
    name: str
    track_count: int

class SetSummary(BaseModel):
    """DJ Set at summary level."""

    ref: str
    name: str
    version_count: int
    track_count: int

class ArtistSummary(BaseModel):
    """Artist at summary level."""

    ref: str
    name: str
    tracks_in_db: int

# ─── Entity Detail (for get_*, single entity) ───

class TrackDetail(TrackSummary):
    """Track with metadata — extends TrackSummary."""

    has_features: bool = False
    genres: list[str] = []
    labels: list[str] = []
    albums: list[str] = []
    sections_count: int | None = None
    platform_ids: dict[str, str] = {}

# ─── Envelope components ───

class LibraryStats(BaseModel):
    """Background stats included in every response."""

    total_tracks: int
    analyzed_tracks: int
    total_playlists: int
    total_sets: int

class PaginationInfo(BaseModel):
    """Cursor-based pagination metadata."""

    limit: int
    offset: int
    total: int
    has_more: bool
    cursor: str | None = None

# ─── Compound responses ───

class FindResult(BaseModel):
    """Result of entity ref resolution."""

    exact: bool
    entities: list[TrackSummary | PlaylistSummary | SetSummary | ArtistSummary]
    source: str

class SearchResponse(BaseModel):
    """Universal search response with categorized results."""

    results: dict[str, list[TrackSummary | PlaylistSummary | SetSummary | ArtistSummary]]
    stats: dict[str, int]
    library: LibraryStats
    pagination: PaginationInfo
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_schemas.py -v
```

Expected: PASS

**Step 5: Lint**

```bash
uv run ruff check app/mcp/schemas.py tests/mcp/test_schemas.py && uv run mypy app/mcp/schemas.py
```

**Step 6: Commit**

```bash
git add app/mcp/schemas.py tests/mcp/test_schemas.py
git commit -m "feat(mcp): add response models — Summary/Detail + envelope

TrackSummary, TrackDetail, PlaylistSummary, SetSummary, ArtistSummary,
LibraryStats, PaginationInfo, FindResult, SearchResponse."
```

---

### Task 4: URN Ref Parser (`refs.py`)

**Files:**
- Create: `app/mcp/refs.py`
- Test: `tests/mcp/test_refs.py`

Parses `"local:42"`, `"ym:12345"`, `"42"`, `"Boris Brejcha"` into a structured `ParsedRef`.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_refs.py
"""Tests for URN ref parser — local:42, ym:12345, text queries."""

from __future__ import annotations

import pytest

from app.mcp.refs import ParsedRef, RefType, parse_ref

class TestParseRef:
    def test_local_explicit(self):
        r = parse_ref("local:42")
        assert r.type == RefType.LOCAL
        assert r.id == 42

    def test_local_bare_int(self):
        """Plain integer auto-resolves to local."""
        r = parse_ref("42")
        assert r.type == RefType.LOCAL
        assert r.id == 42

    def test_platform_ym(self):
        r = parse_ref("ym:12345")
        assert r.type == RefType.PLATFORM
        assert r.platform == "ym"
        assert r.platform_id == "12345"

    def test_platform_spotify(self):
        r = parse_ref("spotify:abc123")
        assert r.type == RefType.PLATFORM
        assert r.platform == "spotify"
        assert r.platform_id == "abc123"

    def test_text_query(self):
        r = parse_ref("Boris Brejcha")
        assert r.type == RefType.TEXT
        assert r.query == "Boris Brejcha"

    def test_text_single_word(self):
        r = parse_ref("Techno")
        assert r.type == RefType.TEXT
        assert r.query == "Techno"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_ref("")

    def test_whitespace_stripped(self):
        r = parse_ref("  local:42  ")
        assert r.type == RefType.LOCAL
        assert r.id == 42

    def test_local_invalid_id(self):
        with pytest.raises(ValueError, match="Invalid local ID"):
            parse_ref("local:abc")
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/test_refs.py -v
```

**Step 3: Implement refs.py**

```python
# app/mcp/refs.py
"""URN entity reference parser.

Formats:
    local:42          → LOCAL with id=42
    ym:12345          → PLATFORM with platform="ym", platform_id="12345"
    42                → LOCAL with id=42 (auto-detect bare int)
    "Boris Brejcha"   → TEXT with query="Boris Brejcha"
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

class RefType(StrEnum):
    """Type of entity reference."""

    LOCAL = "local"
    PLATFORM = "platform"
    TEXT = "text"

@dataclass(frozen=True)
class ParsedRef:
    """Parsed entity reference."""

    type: RefType
    id: int | None = None
    platform: str | None = None
    platform_id: str | None = None
    query: str | None = None

def parse_ref(ref: str) -> ParsedRef:
    """Parse a universal entity reference string.

    Args:
        ref: Reference string (``local:42``, ``ym:12345``, ``42``, ``"Boris Brejcha"``).

    Returns:
        ParsedRef with type, id/platform_id/query fields.

    Raises:
        ValueError: If ref is empty or has invalid local ID.
    """
    ref = ref.strip()
    if not ref:
        msg = "Ref string is empty"
        raise ValueError(msg)

    # Prefixed: "local:42", "ym:12345"
    if ":" in ref:
        prefix, value = ref.split(":", 1)
        if prefix == "local":
            try:
                return ParsedRef(type=RefType.LOCAL, id=int(value))
            except ValueError:
                msg = f"Invalid local ID: {value!r}"
                raise ValueError(msg) from None
        return ParsedRef(type=RefType.PLATFORM, platform=prefix, platform_id=value)

    # Bare integer → local
    try:
        return ParsedRef(type=RefType.LOCAL, id=int(ref))
    except ValueError:
        pass

    # Text query
    return ParsedRef(type=RefType.TEXT, query=ref)
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_refs.py -v
```

Expected: PASS

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/refs.py tests/mcp/test_refs.py && uv run mypy app/mcp/refs.py
git add app/mcp/refs.py tests/mcp/test_refs.py
git commit -m "feat(mcp): add URN ref parser — local:42, ym:12345, text

parse_ref() resolves refs to ParsedRef with LOCAL/PLATFORM/TEXT type."
```

---

### Task 5: Cursor Pagination (`pagination.py`)

**Files:**
- Create: `app/mcp/pagination.py`
- Test: `tests/mcp/test_pagination.py`

**Step 1: Write the failing tests**

```python
# tests/mcp/test_pagination.py
"""Tests for cursor-based pagination helpers."""

from __future__ import annotations

import pytest

from app.mcp.pagination import decode_cursor, encode_cursor, paginate_params

class TestCursorEncoding:
    def test_roundtrip(self):
        cursor = encode_cursor(offset=40)
        assert decode_cursor(cursor) == 40

    def test_zero_offset(self):
        cursor = encode_cursor(offset=0)
        assert decode_cursor(cursor) == 0

    def test_large_offset(self):
        cursor = encode_cursor(offset=99999)
        assert decode_cursor(cursor) == 99999

    def test_invalid_cursor(self):
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor("not-a-valid-cursor")

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

    def test_limit_capped(self):
        offset, limit = paginate_params(cursor=None, limit=500)
        assert limit == 100  # max cap
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/test_pagination.py -v
```

**Step 3: Implement pagination.py**

```python
# app/mcp/pagination.py
"""Cursor-based pagination helpers.

Cursors encode offset as opaque base64 strings. This decouples
the pagination contract from the underlying offset/limit implementation.
"""

from __future__ import annotations

import base64
import json

MAX_LIMIT = 100

def encode_cursor(*, offset: int) -> str:
    """Encode pagination state into an opaque cursor string."""
    payload = json.dumps({"o": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()

def decode_cursor(cursor: str) -> int:
    """Decode cursor string back to offset.

    Raises:
        ValueError: If cursor is invalid.
    """
    try:
        payload = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(payload)
        return int(data["o"])
    except Exception:
        msg = f"Invalid cursor: {cursor!r}"
        raise ValueError(msg) from None

def paginate_params(*, cursor: str | None, limit: int) -> tuple[int, int]:
    """Compute (offset, limit) from cursor and requested limit.

    Caps limit at MAX_LIMIT.
    """
    offset = decode_cursor(cursor) if cursor else 0
    capped_limit = min(limit, MAX_LIMIT)
    return offset, capped_limit
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/test_pagination.py -v
uv run ruff check app/mcp/pagination.py && uv run mypy app/mcp/pagination.py
git add app/mcp/pagination.py tests/mcp/test_pagination.py
git commit -m "feat(mcp): add cursor pagination — encode/decode + params

Opaque base64 cursors, limit capped at 100."
```

---

### Task 6: Library Stats (`stats.py`)

**Files:**
- Create: `app/mcp/stats.py`
- Test: `tests/mcp/test_stats.py`

4 COUNT queries → `LibraryStats`. Included in every response envelope.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_stats.py
"""Tests for library stats — background metadata for response envelopes."""

from __future__ import annotations

from app.mcp.schemas import LibraryStats
from app.mcp.stats import get_library_stats
from app.models.dj import DjPlaylist
from app.models.features import TrackAudioFeaturesComputed
from app.models.runs import FeatureExtractionRun
from app.models.sets import DjSet
from app.models.tracks import Track

async def test_empty_db(session):
    stats = await get_library_stats(session)
    assert isinstance(stats, LibraryStats)
    assert stats.total_tracks == 0
    assert stats.analyzed_tracks == 0
    assert stats.total_playlists == 0
    assert stats.total_sets == 0

async def test_with_data(session):
    # Seed tracks
    t1 = Track(title="A", title_sort="a", duration_ms=180000, status=0)
    t2 = Track(title="B", title_sort="b", duration_ms=200000, status=0)
    t3 = Track(title="C", title_sort="c", duration_ms=220000, status=0)
    session.add_all([t1, t2, t3])
    await session.flush()

    # Seed a feature run + features for t1 only
    run = FeatureExtractionRun(
        pipeline_name="test", pipeline_version="1.0", status="completed"
    )
    session.add(run)
    await session.flush()
    feat = TrackAudioFeaturesComputed(track_id=t1.track_id, run_id=run.run_id, bpm=140.0)
    session.add(feat)

    # Seed playlist + set
    pl = DjPlaylist(name="Test playlist")
    session.add(pl)
    s = DjSet(name="Test set")
    session.add(s)
    await session.flush()

    stats = await get_library_stats(session)
    assert stats.total_tracks == 3
    assert stats.analyzed_tracks == 1
    assert stats.total_playlists == 1
    assert stats.total_sets == 1
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/test_stats.py -v
```

**Step 3: Implement stats.py**

```python
# app/mcp/stats.py
"""Library stats — background metadata for response envelopes.

Executes 4 COUNT queries. Designed to be called once per tool invocation
and included in the response envelope so the agent always has context.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.schemas import LibraryStats
from app.models.dj import DjPlaylist
from app.models.features import TrackAudioFeaturesComputed
from app.models.sets import DjSet
from app.models.tracks import Track

async def get_library_stats(session: AsyncSession) -> LibraryStats:
    """Compute library-wide aggregate stats.

    Returns:
        LibraryStats with total counts for tracks, analyzed, playlists, sets.
    """
    total_tracks = (
        await session.execute(select(func.count(Track.track_id)))
    ).scalar_one()

    analyzed_tracks = (
        await session.execute(
            select(func.count(func.distinct(TrackAudioFeaturesComputed.track_id)))
        )
    ).scalar_one()

    total_playlists = (
        await session.execute(select(func.count(DjPlaylist.playlist_id)))
    ).scalar_one()

    total_sets = (
        await session.execute(select(func.count(DjSet.set_id)))
    ).scalar_one()

    return LibraryStats(
        total_tracks=total_tracks,
        analyzed_tracks=analyzed_tracks,
        total_playlists=total_playlists,
        total_sets=total_sets,
    )
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/test_stats.py -v
uv run ruff check app/mcp/stats.py && uv run mypy app/mcp/stats.py
git add app/mcp/stats.py tests/mcp/test_stats.py
git commit -m "feat(mcp): add library stats — 4 COUNT queries for envelope

get_library_stats(session) → LibraryStats with track/playlist/set counts."
```

---

### Task 7: ORM → Schema Converters (`converters.py`)

**Files:**
- Create: `app/mcp/converters.py`
- Test: `tests/mcp/test_converters.py`

Convert ORM models to Summary/Detail schemas. Key conversion: `key_code → Camelot notation`.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_converters.py
"""Tests for ORM → schema converters."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.mcp.converters import (
    playlist_to_summary,
    set_to_summary,
    track_to_detail,
    track_to_summary,
)
from app.mcp.schemas import PlaylistSummary, SetSummary, TrackDetail, TrackSummary

class TestTrackToSummary:
    def test_basic(self):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000

        s = track_to_summary(track, artist_name="Boris Brejcha")
        assert isinstance(s, TrackSummary)
        assert s.ref == "local:42"
        assert s.title == "Gravity"
        assert s.artist == "Boris Brejcha"
        assert s.duration_ms == 360000
        assert s.bpm is None

    def test_with_features(self):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000

        features = MagicMock()
        features.bpm = 140.0
        features.key_code = 8  # 8 = Em = 9A in Camelot
        features.lufs_i = -8.3

        s = track_to_summary(track, artist_name="Boris Brejcha", features=features)
        assert s.bpm == 140.0
        assert s.key == "9A"
        assert s.energy_lufs == -8.3

class TestTrackToDetail:
    def test_basic(self):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000

        d = track_to_detail(
            track,
            artist_name="Boris Brejcha",
            genres=["Techno"],
            labels=["Fckng Serious"],
            albums=["Gravity EP"],
            platform_ids={"ym": "12345"},
            has_features=True,
            sections_count=5,
        )
        assert isinstance(d, TrackDetail)
        assert d.ref == "local:42"
        assert d.genres == ["Techno"]
        assert d.has_features is True
        assert d.platform_ids == {"ym": "12345"}

class TestPlaylistToSummary:
    def test_basic(self):
        playlist = MagicMock()
        playlist.playlist_id = 5
        playlist.name = "Techno develop"

        s = playlist_to_summary(playlist, track_count=247)
        assert isinstance(s, PlaylistSummary)
        assert s.ref == "local:5"
        assert s.track_count == 247

class TestSetToSummary:
    def test_basic(self):
        dj_set = MagicMock()
        dj_set.set_id = 3
        dj_set.name = "Friday night"

        s = set_to_summary(dj_set, version_count=2, track_count=15)
        assert isinstance(s, SetSummary)
        assert s.ref == "local:3"
        assert s.version_count == 2
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/test_converters.py -v
```

**Step 3: Implement converters.py**

```python
# app/mcp/converters.py
"""ORM model → MCP schema converters.

These convert SQLAlchemy ORM instances into Pydantic Summary/Detail schemas.
Designed to be called from resolvers and tool implementations.
"""

from __future__ import annotations

from typing import Any

from app.mcp.schemas import (
    PlaylistSummary,
    SetSummary,
    TrackDetail,
    TrackSummary,
)
from app.utils.audio.constants import key_code_to_camelot

def track_to_summary(
    track: Any,
    *,
    artist_name: str = "",
    features: Any | None = None,
    mood: str | None = None,
) -> TrackSummary:
    """Convert Track ORM + optional features to TrackSummary."""
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None

    if features is not None:
        bpm = getattr(features, "bpm", None)
        key_code = getattr(features, "key_code", None)
        if key_code is not None:
            key = key_code_to_camelot(key_code)
        energy_lufs = getattr(features, "lufs_i", None)

    return TrackSummary(
        ref=f"local:{track.track_id}",
        title=track.title,
        artist=artist_name,
        bpm=bpm,
        key=key,
        energy_lufs=energy_lufs,
        duration_ms=track.duration_ms,
        mood=mood,
    )

def track_to_detail(
    track: Any,
    *,
    artist_name: str = "",
    features: Any | None = None,
    mood: str | None = None,
    genres: list[str] | None = None,
    labels: list[str] | None = None,
    albums: list[str] | None = None,
    platform_ids: dict[str, str] | None = None,
    has_features: bool = False,
    sections_count: int | None = None,
) -> TrackDetail:
    """Convert Track ORM + metadata to TrackDetail."""
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None

    if features is not None:
        bpm = getattr(features, "bpm", None)
        key_code = getattr(features, "key_code", None)
        if key_code is not None:
            key = key_code_to_camelot(key_code)
        energy_lufs = getattr(features, "lufs_i", None)

    return TrackDetail(
        ref=f"local:{track.track_id}",
        title=track.title,
        artist=artist_name,
        bpm=bpm,
        key=key,
        energy_lufs=energy_lufs,
        duration_ms=track.duration_ms,
        mood=mood,
        has_features=has_features,
        genres=genres or [],
        labels=labels or [],
        albums=albums or [],
        sections_count=sections_count,
        platform_ids=platform_ids or {},
    )

def playlist_to_summary(playlist: Any, *, track_count: int) -> PlaylistSummary:
    """Convert DjPlaylist ORM to PlaylistSummary."""
    return PlaylistSummary(
        ref=f"local:{playlist.playlist_id}",
        name=playlist.name,
        track_count=track_count,
    )

def set_to_summary(dj_set: Any, *, version_count: int, track_count: int) -> SetSummary:
    """Convert DjSet ORM to SetSummary."""
    return SetSummary(
        ref=f"local:{dj_set.set_id}",
        name=dj_set.name,
        version_count=version_count,
        track_count=track_count,
    )
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/test_converters.py -v
uv run ruff check app/mcp/converters.py && uv run mypy app/mcp/converters.py
git add app/mcp/converters.py tests/mcp/test_converters.py
git commit -m "feat(mcp): add ORM → schema converters

track_to_summary, track_to_detail, playlist_to_summary, set_to_summary.
Includes key_code → Camelot conversion."
```

---

### Task 8: Entity Resolvers (`resolvers.py`)

**Files:**
- Create: `app/mcp/resolvers.py`
- Test: `tests/mcp/test_resolvers.py`

Resolve `ParsedRef` → `FindResult` using repositories. Each entity type has its own resolver.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_resolvers.py
"""Tests for entity resolvers — ref → FindResult via DB."""

from __future__ import annotations

from app.mcp.refs import RefType, parse_ref
from app.mcp.resolvers import TrackResolver, PlaylistResolver, SetResolver
from app.mcp.schemas import FindResult
from app.models.dj import DjPlaylist
from app.models.sets import DjSet
from app.models.tracks import Track

class TestTrackResolver:
    async def test_local_found(self, session):
        track = Track(title="Gravity", title_sort="gravity", duration_ms=360000, status=0)
        session.add(track)
        await session.flush()

        resolver = TrackResolver(session)
        result = await resolver.resolve(parse_ref(f"local:{track.track_id}"))

        assert isinstance(result, FindResult)
        assert result.exact is True
        assert len(result.entities) == 1
        assert result.entities[0].title == "Gravity"
        assert result.source == "local"

    async def test_local_not_found(self, session):
        resolver = TrackResolver(session)
        result = await resolver.resolve(parse_ref("local:99999"))

        assert result.exact is True
        assert len(result.entities) == 0

    async def test_text_search(self, session):
        t1 = Track(title="Gravity", title_sort="gravity", duration_ms=360000, status=0)
        t2 = Track(title="Gravity Remix", title_sort="gravity remix", duration_ms=300000, status=0)
        t3 = Track(title="Unrelated", title_sort="unrelated", duration_ms=200000, status=0)
        session.add_all([t1, t2, t3])
        await session.flush()

        resolver = TrackResolver(session)
        result = await resolver.resolve(parse_ref("Gravity"))

        assert result.exact is False
        assert len(result.entities) >= 2  # "Gravity" and "Gravity Remix"
        assert result.source == "local"

    async def test_bare_int(self, session):
        track = Track(title="Test", title_sort="test", duration_ms=180000, status=0)
        session.add(track)
        await session.flush()

        resolver = TrackResolver(session)
        result = await resolver.resolve(parse_ref(str(track.track_id)))

        assert result.exact is True
        assert len(result.entities) == 1

class TestPlaylistResolver:
    async def test_local_found(self, session):
        pl = DjPlaylist(name="Techno develop")
        session.add(pl)
        await session.flush()

        resolver = PlaylistResolver(session)
        result = await resolver.resolve(parse_ref(f"local:{pl.playlist_id}"))

        assert result.exact is True
        assert len(result.entities) == 1
        assert result.entities[0].name == "Techno develop"

    async def test_text_search(self, session):
        pl = DjPlaylist(name="Techno develop")
        session.add(pl)
        await session.flush()

        resolver = PlaylistResolver(session)
        result = await resolver.resolve(parse_ref("Techno"))

        assert result.exact is False
        assert len(result.entities) >= 1

class TestSetResolver:
    async def test_local_found(self, session):
        s = DjSet(name="Friday night")
        session.add(s)
        await session.flush()

        resolver = SetResolver(session)
        result = await resolver.resolve(parse_ref(f"local:{s.set_id}"))

        assert result.exact is True
        assert len(result.entities) == 1
        assert result.entities[0].name == "Friday night"
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/test_resolvers.py -v
```

**Step 3: Implement resolvers.py**

```python
# app/mcp/resolvers.py
"""Entity resolvers — resolve ParsedRef → FindResult via DB.

Each entity type has a resolver that:
1. LOCAL ref → get_by_id → single entity or empty
2. TEXT ref → search_by_title/name → list of matches
3. PLATFORM ref → lookup via ProviderTrackId (future)
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.converters import playlist_to_summary, set_to_summary, track_to_summary
from app.mcp.refs import ParsedRef, RefType
from app.mcp.schemas import FindResult
from app.models.dj import DjPlaylist, DjPlaylistItem
from app.models.sets import DjSet, DjSetItem, DjSetVersion
from app.models.tracks import Track
from app.repositories.artists import ArtistRepository
from app.repositories.playlists import DjPlaylistRepository
from app.repositories.sets import DjSetRepository
from app.repositories.tracks import TrackRepository

class TrackResolver:
    """Resolve track refs to FindResult."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrackRepository(session)

    async def resolve(self, ref: ParsedRef) -> FindResult:
        if ref.type == RefType.LOCAL:
            return await self._resolve_local(ref.id)
        if ref.type == RefType.TEXT:
            return await self._resolve_text(ref.query or "")
        # PLATFORM — future
        return FindResult(exact=False, entities=[], source=ref.platform or "unknown")

    async def _resolve_local(self, track_id: int | None) -> FindResult:
        if track_id is None:
            return FindResult(exact=True, entities=[], source="local")
        track = await self._repo.get_by_id(track_id)
        if not track:
            return FindResult(exact=True, entities=[], source="local")
        artist_name = await self._get_artist_name(track.track_id)
        summary = track_to_summary(track, artist_name=artist_name)
        return FindResult(exact=True, entities=[summary], source="local")

    async def _resolve_text(self, query: str) -> FindResult:
        tracks, _ = await self._repo.search_by_title(query, limit=10)
        artist_map = await self._repo.get_artists_for_tracks(
            [t.track_id for t in tracks]
        )
        entities = [
            track_to_summary(
                t, artist_name=", ".join(artist_map.get(t.track_id, []))
            )
            for t in tracks
        ]
        return FindResult(exact=False, entities=entities, source="local")

    async def _get_artist_name(self, track_id: int) -> str:
        artist_map = await self._repo.get_artists_for_tracks([track_id])
        return ", ".join(artist_map.get(track_id, []))

class PlaylistResolver:
    """Resolve playlist refs to FindResult."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DjPlaylistRepository(session)

    async def resolve(self, ref: ParsedRef) -> FindResult:
        if ref.type == RefType.LOCAL:
            return await self._resolve_local(ref.id)
        if ref.type == RefType.TEXT:
            return await self._resolve_text(ref.query or "")
        return FindResult(exact=False, entities=[], source=ref.platform or "unknown")

    async def _resolve_local(self, playlist_id: int | None) -> FindResult:
        if playlist_id is None:
            return FindResult(exact=True, entities=[], source="local")
        playlist = await self._repo.get_by_id(playlist_id)
        if not playlist:
            return FindResult(exact=True, entities=[], source="local")
        count = await self._count_items(playlist.playlist_id)
        summary = playlist_to_summary(playlist, track_count=count)
        return FindResult(exact=True, entities=[summary], source="local")

    async def _resolve_text(self, query: str) -> FindResult:
        playlists, _ = await self._repo.search_by_name(query, limit=10)
        entities = []
        for pl in playlists:
            count = await self._count_items(pl.playlist_id)
            entities.append(playlist_to_summary(pl, track_count=count))
        return FindResult(exact=False, entities=entities, source="local")

    async def _count_items(self, playlist_id: int) -> int:
        result = await self._session.execute(
            select(func.count(DjPlaylistItem.playlist_item_id)).where(
                DjPlaylistItem.playlist_id == playlist_id
            )
        )
        return result.scalar_one()

class SetResolver:
    """Resolve set refs to FindResult."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DjSetRepository(session)

    async def resolve(self, ref: ParsedRef) -> FindResult:
        if ref.type == RefType.LOCAL:
            return await self._resolve_local(ref.id)
        if ref.type == RefType.TEXT:
            return await self._resolve_text(ref.query or "")
        return FindResult(exact=False, entities=[], source=ref.platform or "unknown")

    async def _resolve_local(self, set_id: int | None) -> FindResult:
        if set_id is None:
            return FindResult(exact=True, entities=[], source="local")
        dj_set = await self._repo.get_by_id(set_id)
        if not dj_set:
            return FindResult(exact=True, entities=[], source="local")
        ver_count, track_count = await self._count_versions_tracks(dj_set.set_id)
        summary = set_to_summary(dj_set, version_count=ver_count, track_count=track_count)
        return FindResult(exact=True, entities=[summary], source="local")

    async def _resolve_text(self, query: str) -> FindResult:
        sets, _ = await self._repo.search_by_name(query, limit=10)
        entities = []
        for s in sets:
            ver_count, track_count = await self._count_versions_tracks(s.set_id)
            entities.append(set_to_summary(s, version_count=ver_count, track_count=track_count))
        return FindResult(exact=False, entities=entities, source="local")

    async def _count_versions_tracks(self, set_id: int) -> tuple[int, int]:
        ver_count = (
            await self._session.execute(
                select(func.count(DjSetVersion.set_version_id)).where(
                    DjSetVersion.set_id == set_id
                )
            )
        ).scalar_one()
        # Count tracks in latest version
        latest_ver = (
            await self._session.execute(
                select(DjSetVersion.set_version_id)
                .where(DjSetVersion.set_id == set_id)
                .order_by(DjSetVersion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        track_count = 0
        if latest_ver:
            track_count = (
                await self._session.execute(
                    select(func.count(DjSetItem.set_item_id)).where(
                        DjSetItem.set_version_id == latest_ver
                    )
                )
            ).scalar_one()
        return ver_count, track_count
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/test_resolvers.py -v
uv run ruff check app/mcp/resolvers.py && uv run mypy app/mcp/resolvers.py
git add app/mcp/resolvers.py tests/mcp/test_resolvers.py
git commit -m "feat(mcp): add entity resolvers — ref → FindResult via DB

TrackResolver, PlaylistResolver, SetResolver. Handles LOCAL (get_by_id)
and TEXT (search_by_title/name) ref types. PLATFORM refs stubbed."
```

---

### Task 9: Universal Search Tool (`tools/search.py`)

**Files:**
- Create: `app/mcp/tools/__init__.py`
- Create: `app/mcp/tools/search.py`
- Test: `tests/mcp/tools/__init__.py`
- Test: `tests/mcp/tools/test_search.py`

The `search()` tool — fans out query to tracks, playlists, sets. Returns `SearchResponse` with categorized results + stats + library + pagination.

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/__init__.py
```

```python
# tests/mcp/tools/test_search.py
"""Tests for universal search tool."""

from __future__ import annotations

from fastmcp import Client, FastMCP

from app.mcp.schemas import SearchResponse
from app.models.dj import DjPlaylist
from app.models.sets import DjSet
from app.models.tracks import Track

async def _seed_data(session):
    """Seed test data for search tests."""
    t1 = Track(title="Gravity", title_sort="gravity", duration_ms=360000, status=0)
    t2 = Track(title="Space Motion", title_sort="space motion", duration_ms=300000, status=0)
    t3 = Track(title="Dark Gravity", title_sort="dark gravity", duration_ms=400000, status=0)
    session.add_all([t1, t2, t3])
    pl = DjPlaylist(name="My Gravity playlist")
    session.add(pl)
    s = DjSet(name="Gravity Set")
    session.add(s)
    await session.flush()

async def test_search_registered(search_mcp):
    """search tool is registered."""
    async with Client(search_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "search" in tool_names

async def test_search_by_query(search_mcp_with_db, session):
    """search returns categorized results."""
    await _seed_data(session)

    async with Client(search_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "Gravity"})
        assert not result.is_error
        data = result.data
        # Should find tracks and possibly playlists/sets matching "Gravity"
        assert "tracks" in data.results
        assert len(data.results["tracks"]) >= 2  # "Gravity" and "Dark Gravity"
        assert data.stats["tracks"] >= 2
        assert data.library.total_tracks == 3

async def test_search_scope_tracks(search_mcp_with_db, session):
    """search with scope=tracks returns only tracks."""
    await _seed_data(session)

    async with Client(search_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "Gravity", "scope": "tracks"})
        data = result.data
        assert "tracks" in data.results
        assert "playlists" not in data.results

async def test_search_empty_query(search_mcp_with_db, session):
    """search with empty results returns empty."""
    async with Client(search_mcp_with_db) as client:
        result = await client.call_tool("search", {"query": "zzz_nonexistent_zzz"})
        data = result.data
        assert data.stats.get("tracks", 0) == 0

async def test_filter_tracks_registered(search_mcp):
    """filter_tracks tool is registered."""
    async with Client(search_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "filter_tracks" in tool_names
```

**Step 2: Write conftest for search tool tests**

```python
# tests/mcp/tools/conftest.py
"""Fixtures for tool-level tests."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp.tools.search import create_search_tools

@pytest.fixture
def search_mcp() -> FastMCP:
    """Search tools MCP server (no DB)."""
    return create_search_tools()

@pytest.fixture
async def search_mcp_with_db(engine) -> FastMCP:
    """Search tools MCP server wired to test DB."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _test_session() -> AsyncIterator[AsyncSession]:
        async with factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    with patch("app.mcp.dependencies.get_session", _test_session):
        yield create_search_tools()
```

**Step 3: Run to verify failure**

```bash
uv run pytest tests/mcp/tools/test_search.py -v
```

**Step 4: Implement tools/search.py**

```python
# app/mcp/tools/__init__.py
"""MCP tools — DJ namespace."""
```

```python
# app/mcp/tools/search.py
"""Universal search + filter_tracks tools.

search() fans out query to tracks, playlists, sets.
filter_tracks() filters by BPM, key, energy criteria.
"""

from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.dependencies import get_session
from app.mcp.pagination import encode_cursor, paginate_params
from app.mcp.resolvers import PlaylistResolver, SetResolver, TrackResolver
from app.mcp.schemas import PaginationInfo, SearchResponse
from app.mcp.stats import get_library_stats

def create_search_tools() -> FastMCP:
    """Create a FastMCP server with search tools."""
    mcp = FastMCP("Search Tools")

    @mcp.tool(
        tags={"search"},
        annotations={"readOnlyHint": True},
    )
    async def search(
        query: str,
        scope: str = "all",
        limit: int = 20,
        cursor: str | None = None,
        ctx: Context = None,  # type: ignore[assignment]
        session: AsyncSession = Depends(get_session),
    ) -> SearchResponse:
        """Universal search across tracks, playlists, and sets.

        Args:
            query: Search text (title, artist name, etc.)
            scope: "all" | "tracks" | "playlists" | "sets"
            limit: Max results per category (default 20, max 100)
            cursor: Pagination cursor from previous response
        """
        offset, capped_limit = paginate_params(cursor=cursor, limit=limit)

        results: dict[str, list] = {}
        stats: dict[str, int] = {}

        scopes = (
            [scope] if scope != "all" else ["tracks", "playlists", "sets"]
        )

        if "tracks" in scopes:
            track_resolver = TrackResolver(session)
            from app.mcp.refs import ParsedRef, RefType

            ref = ParsedRef(type=RefType.TEXT, query=query)
            found = await track_resolver.resolve(ref)
            results["tracks"] = found.entities[:capped_limit]
            stats["tracks"] = len(found.entities)

        if "playlists" in scopes:
            playlist_resolver = PlaylistResolver(session)
            from app.mcp.refs import ParsedRef, RefType

            ref = ParsedRef(type=RefType.TEXT, query=query)
            found = await playlist_resolver.resolve(ref)
            results["playlists"] = found.entities[:capped_limit]
            stats["playlists"] = len(found.entities)

        if "sets" in scopes:
            set_resolver = SetResolver(session)
            from app.mcp.refs import ParsedRef, RefType

            ref = ParsedRef(type=RefType.TEXT, query=query)
            found = await set_resolver.resolve(ref)
            results["sets"] = found.entities[:capped_limit]
            stats["sets"] = len(found.entities)

        library = await get_library_stats(session)

        total_results = sum(stats.values())
        has_more = total_results > offset + capped_limit
        next_cursor = (
            encode_cursor(offset=offset + capped_limit) if has_more else None
        )
        pagination = PaginationInfo(
            limit=capped_limit,
            offset=offset,
            total=total_results,
            has_more=has_more,
            cursor=next_cursor,
        )

        return SearchResponse(
            results=results,
            stats=stats,
            library=library,
            pagination=pagination,
        )

    @mcp.tool(
        tags={"search"},
        annotations={"readOnlyHint": True},
    )
    async def filter_tracks(
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        keys: list[str] | None = None,
        energy_min: float | None = None,
        energy_max: float | None = None,
        mood: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        ctx: Context = None,  # type: ignore[assignment]
        session: AsyncSession = Depends(get_session),
    ) -> SearchResponse:
        """Filter tracks by audio features criteria.

        Args:
            bpm_min: Minimum BPM
            bpm_max: Maximum BPM
            keys: Camelot keys to include (e.g. ["5A", "7B"])
            energy_min: Minimum LUFS integrated loudness
            energy_max: Maximum LUFS integrated loudness
            mood: Track mood category
            limit: Max results (default 20, max 100)
            cursor: Pagination cursor
        """
        from sqlalchemy import select

        from app.mcp.converters import track_to_summary
        from app.mcp.pagination import paginate_params
        from app.models.features import TrackAudioFeaturesComputed
        from app.models.tracks import Track
        from app.repositories.tracks import TrackRepository
        from app.utils.audio.constants import camelot_to_key_code

        offset, capped_limit = paginate_params(cursor=cursor, limit=limit)

        # Build "latest features per track" subquery
        from sqlalchemy import func as sa_func

        latest = (
            select(
                TrackAudioFeaturesComputed.track_id,
                sa_func.max(TrackAudioFeaturesComputed.created_at).label("max_created"),
            )
            .group_by(TrackAudioFeaturesComputed.track_id)
            .subquery()
        )

        stmt = (
            select(TrackAudioFeaturesComputed)
            .join(
                latest,
                (TrackAudioFeaturesComputed.track_id == latest.c.track_id)
                & (TrackAudioFeaturesComputed.created_at == latest.c.max_created),
            )
        )

        # Apply filters
        if bpm_min is not None:
            stmt = stmt.where(TrackAudioFeaturesComputed.bpm >= bpm_min)
        if bpm_max is not None:
            stmt = stmt.where(TrackAudioFeaturesComputed.bpm <= bpm_max)
        if energy_min is not None:
            stmt = stmt.where(TrackAudioFeaturesComputed.lufs_i >= energy_min)
        if energy_max is not None:
            stmt = stmt.where(TrackAudioFeaturesComputed.lufs_i <= energy_max)
        if keys:
            key_codes = [camelot_to_key_code(k) for k in keys if camelot_to_key_code(k) is not None]
            if key_codes:
                stmt = stmt.where(TrackAudioFeaturesComputed.key_code.in_(key_codes))

        # Count total before pagination
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        # Apply pagination
        stmt = stmt.offset(offset).limit(capped_limit)
        result = await session.execute(stmt)
        features_list = list(result.scalars().all())

        # Load track data
        track_ids = [f.track_id for f in features_list]
        track_repo = TrackRepository(session)
        tracks_map: dict[int, Track] = {}
        artist_map: dict[int, list[str]] = {}
        if track_ids:
            for tid in track_ids:
                track = await track_repo.get_by_id(tid)
                if track:
                    tracks_map[tid] = track
            artist_map = await track_repo.get_artists_for_tracks(track_ids)

        # Build summaries
        entities = []
        for feat in features_list:
            track = tracks_map.get(feat.track_id)
            if track:
                entities.append(
                    track_to_summary(
                        track,
                        artist_name=", ".join(artist_map.get(feat.track_id, [])),
                        features=feat,
                    )
                )

        library = await get_library_stats(session)
        has_more = total > offset + capped_limit
        next_cursor = encode_cursor(offset=offset + capped_limit) if has_more else None

        return SearchResponse(
            results={"tracks": entities},
            stats={"tracks": total},
            library=library,
            pagination=PaginationInfo(
                limit=capped_limit,
                offset=offset,
                total=total,
                has_more=has_more,
                cursor=next_cursor,
            ),
        )

    return mcp
```

**Step 5: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/tools/test_search.py -v
uv run ruff check app/mcp/tools/ tests/mcp/tools/ && uv run mypy app/mcp/tools/
git add app/mcp/tools/ tests/mcp/tools/
git commit -m "feat(mcp): add universal search + filter_tracks tools

search() fans out to tracks/playlists/sets via resolvers.
filter_tracks() filters by BPM/key/energy/mood with latest-per-track
subquery. Both return SearchResponse with stats + pagination."
```

---

### Task 10: Integration — Register search tools in workflow server

**Files:**
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_client_integration.py`

Mount the new search tools into the existing DJ Workflows server so they appear alongside current tools.

**Step 1: Write the failing test**

```python
# Add to tests/mcp/test_client_integration.py

async def test_search_tools_in_workflow(workflow_mcp):
    """search and filter_tracks are registered in workflow server."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "search" in tool_names
        assert "filter_tracks" in tool_names
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/mcp/test_client_integration.py::test_search_tools_in_workflow -v
```

**Step 3: Register in server.py**

Add to `app/mcp/workflows/server.py`:

```python
# Inside create_workflow_mcp():
from app.mcp.tools.search import create_search_tools

# After existing tool registrations
search_server = create_search_tools()
for tool in search_server._tool_manager._tools.values():
    mcp.add_tool(tool)
```

> **Note:** Exact registration mechanism depends on FastMCP API. If `add_tool()` is not available, mount as sub-server or register tools manually.

**Step 4: Run full test suite**

```bash
uv run pytest tests/mcp/ -v
```

Expected: all existing tests pass + new search test passes.

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/ && uv run mypy app/mcp/
git add app/mcp/workflows/server.py tests/mcp/test_client_integration.py
git commit -m "feat(mcp): register search + filter_tracks in workflow server

New search tools available alongside existing DJ workflow tools."
```

---

### Task 11: Full CI check

**Step 1: Run all tests**

```bash
uv run pytest -v
```

**Step 2: Run linting**

```bash
make lint
```

**Step 3: Fix any issues**

If there are ruff/mypy issues, fix them in the affected files.

**Step 4: Final commit if fixes needed**

```bash
git add -u
git commit -m "fix: lint and type fixes for Phase 0 + Phase 1"
```

---

## Summary

| Task | Phase | New files | Tests | Purpose |
|------|-------|-----------|-------|---------|
| 1 | 0 | — (modify conftest) | test_harness.py | MCP test harness — DB-wired fixtures |
| 2 | 0 | platforms/keys.py | test_keys.py | PlatformKey enum — ym ↔ yandex_music |
| 3 | 1 | schemas.py | test_schemas.py | Response models (Summary/Detail + envelope) |
| 4 | 1 | refs.py | test_refs.py | URN ref parser |
| 5 | 1 | pagination.py | test_pagination.py | Cursor encode/decode |
| 6 | 1 | stats.py | test_stats.py | Library stats (4 COUNT queries) |
| 7 | 1 | converters.py | test_converters.py | ORM → schema converters |
| 8 | 1 | resolvers.py | test_resolvers.py | Entity resolvers (ref → FindResult) |
| 9 | 1 | tools/search.py | tools/test_search.py | search + filter_tracks tools |
| 10 | 1 | — (modify server.py) | test_client_integration.py | Register in workflow server |
| 11 | — | — | — | Full CI check |

**Estimated time:** ~3-4 hours (TDD with bite-sized commits)
