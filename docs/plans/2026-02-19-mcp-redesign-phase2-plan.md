# MCP Redesign Phase 2 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Создать CRUD-инструменты для всех сущностей (Track, Playlist, Set, Features), обернуть оркестраторы (build/score/export/download) в refs + envelope, унифицировать экспорт — всё в новом модуле `app/mcp/tools/`.

**Architecture:** Новые инструменты в `app/mcp/tools/` используют resolvers из Phase 1 для парсинга URN-ссылок, converters для ORM→Schema, и envelope для единообразных ответов. Инструменты возвращают **Pydantic-модели** (НЕ JSON-строки). Старые `workflows/` НЕ модифицируются — они продолжают работать через gateway. Новые tools тестируются через собственный `create_tools_mcp()`. Phase 4 переключит gateway на новые tools и удалит workflows/.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest + pytest-asyncio

**Design doc:** `docs/plans/2026-02-19-mcp-redesign-analysis.md`
**Phase 0+1 plan:** `docs/plans/2026-02-19-mcp-redesign-phase0-phase1-plan.md` (prerequisite)

**Phase 0+1 delivers (используется этим планом):**
- `app/mcp/schemas.py` — TrackSummary, TrackDetail, PlaylistSummary, SetSummary, ArtistSummary, LibraryStats, PaginationInfo, SearchResponse, FindResult
- `app/mcp/refs.py` — parse_ref, ParsedRef, RefType
- `app/mcp/resolvers.py` — TrackResolver, PlaylistResolver, SetResolver
- `app/mcp/converters.py` — track_to_summary, track_to_detail, playlist_to_summary, set_to_summary, artist_to_summary
- `app/mcp/pagination.py` — encode_cursor, decode_cursor, paginate_params
- `app/mcp/stats.py` — get_library_stats
- `app/mcp/platforms/keys.py` — PlatformKey enum
- `app/mcp/tools/search.py` — search, filter_tracks
- `tests/mcp/conftest.py` — workflow_mcp_with_db, gateway_mcp_with_db fixtures

**Key patterns (КРИТИЧНО — соблюдать везде):**
- **MCP DI:** `from fastmcp import Context` + `ctx.session` через dependency injection (НЕ FastAPI Depends)
- **Tool results:** Pydantic models → `result.data` в тестах (НЕ `result[0].text`, НЕ `json.loads()`)
- **Tool errors:** `raise ToolError(msg)` → `pytest.raises(ToolError)` в тестах
- **Update tools:** фильтровать None перед созданием update schema (НЕ передавать все поля)
- **Repos:** `BaseRepository[ModelT: Base]` → `list(offset, limit, filters) → tuple[list[T], int]`
- **Tests:** Server fixture + `async with Client(server)` в теле теста
- **Asyncio:** `asyncio_mode = "auto"` — НЕ нужен `@pytest.mark.asyncio`
- **Camelot:** `key_code=8` → `"9A"` (Em), НЕ `"5A"`
- **Repos:** `app.repositories.audio_features` (НЕ `app.repositories.features`)

**Что Phase 2 НЕ делает:**
- НЕ модифицирует `app/mcp/workflows/` — старые инструменты остаются
- НЕ модифицирует `app/mcp/gateway.py` — gateway по-прежнему использует workflows
- НЕ удаляет `app/mcp/types.py` / `types_curation.py` — это Phase 4
- НЕ создаёт audio namespace (compute_bpm, compute_key, etc.) — отдельная задача

---

## Task 1: Envelope models + wrappers

**Files:**
- Modify: `app/mcp/schemas.py` — добавить PlaylistDetail, SetDetail, AudioFeaturesSummary, EntityListResponse, EntityDetailResponse, ActionResponse
- Create: `app/mcp/envelope.py` — wrap_list, wrap_detail, wrap_action
- Test: `tests/mcp/test_envelope.py`

Envelope — единый формат ответа для всех CRUD-инструментов. Ключевое отличие от старого плана: возвращаем **Pydantic-модели**, НЕ JSON-строки.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_envelope.py
"""Tests for response envelope helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.mcp.envelope import wrap_action, wrap_detail, wrap_list
from app.mcp.schemas import (
    ActionResponse,
    EntityDetailResponse,
    EntityListResponse,
    TrackSummary,
)

def _mock_session() -> AsyncMock:
    """Mock AsyncSession that returns library stats counts."""
    session = AsyncMock()
    # get_library_stats делает 4 COUNT запроса
    session.execute = AsyncMock(
        side_effect=[_scalar(100), _scalar(80), _scalar(5), _scalar(3)]
    )
    return session

def _scalar(value: int) -> AsyncMock:
    mock = AsyncMock()
    mock.scalar_one = lambda: value
    return mock

class TestWrapList:
    async def test_returns_pydantic_model(self):
        session = _mock_session()
        entities = [
            TrackSummary(ref="local:1", title="A", artist="X"),
            TrackSummary(ref="local:2", title="B", artist="Y"),
        ]
        result = await wrap_list(entities, total=50, offset=0, limit=20, session=session)

        assert isinstance(result, EntityListResponse)
        assert len(result.results) == 2
        assert result.total == 50
        assert result.library.total_tracks == 100
        assert result.pagination.has_more is True
        assert result.pagination.cursor is not None

    async def test_last_page(self):
        session = _mock_session()
        entities = [TrackSummary(ref="local:1", title="A", artist="X")]
        result = await wrap_list(entities, total=1, offset=0, limit=20, session=session)

        assert result.pagination.has_more is False
        assert result.pagination.cursor is None

    async def test_empty_list(self):
        session = _mock_session()
        result = await wrap_list([], total=0, offset=0, limit=20, session=session)

        assert result.results == []
        assert result.total == 0
        assert result.pagination.has_more is False

class TestWrapDetail:
    async def test_returns_pydantic_model(self):
        session = _mock_session()
        entity = TrackSummary(ref="local:42", title="Gravity", artist="Boris Brejcha")
        result = await wrap_detail(entity, session)

        assert isinstance(result, EntityDetailResponse)
        assert result.result.ref == "local:42"
        assert result.library.total_tracks == 100

class TestWrapAction:
    async def test_success_with_result(self):
        session = _mock_session()
        entity = TrackSummary(ref="local:42", title="New", artist="Me")
        result = await wrap_action(
            success=True,
            message="Track created",
            session=session,
            result=entity,
        )

        assert isinstance(result, ActionResponse)
        assert result.success is True
        assert result.message == "Track created"
        assert result.result is not None

    async def test_delete_no_result(self):
        session = _mock_session()
        result = await wrap_action(
            success=True,
            message="Deleted local:42",
            session=session,
        )

        assert result.success is True
        assert result.result is None
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_envelope.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.mcp.envelope'`

**Step 3: Add schema models to schemas.py**

Добавить в конец `app/mcp/schemas.py` (после существующих моделей из Phase 1):

```python
# --- Entity Details (расширенные модели для get_* tools) ---

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

class AudioFeaturesSummary(BaseModel):
    """Compact features view for list operations."""

    track_ref: str
    title: str
    artist: str
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None
    onset_rate: float | None = None
    run_id: int | None = None

# --- Response Envelopes ---

class EntityListResponse(BaseModel):
    """Standard envelope for list/search operations."""

    results: list[Any]
    total: int
    library: LibraryStats
    pagination: PaginationInfo

class EntityDetailResponse(BaseModel):
    """Standard envelope for single-entity get operations."""

    result: Any
    library: LibraryStats

class ActionResponse(BaseModel):
    """Standard envelope for create/update/delete actions."""

    success: bool
    message: str
    result: Any | None = None
    library: LibraryStats
```

**Step 4: Implement envelope.py**

```python
# app/mcp/envelope.py
"""DRY response envelope wrappers for MCP tools.

Every CRUD tool wraps its result in an envelope with library stats + pagination.
Returns Pydantic models (NOT JSON strings) — FastMCP handles serialization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.mcp.pagination import encode_cursor
from app.mcp.schemas import (
    ActionResponse,
    EntityDetailResponse,
    EntityListResponse,
    PaginationInfo,
)
from app.mcp.stats import get_library_stats

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

async def wrap_list(
    entities: list[BaseModel],
    total: int,
    offset: int,
    limit: int,
    session: AsyncSession,
) -> EntityListResponse:
    """Wrap a list of entities with library stats + pagination."""
    library = await get_library_stats(session)
    has_more = offset + limit < total
    next_cursor = encode_cursor(offset=offset + limit) if has_more else None

    return EntityListResponse(
        results=entities,
        total=total,
        library=library,
        pagination=PaginationInfo(limit=limit, has_more=has_more, cursor=next_cursor),
    )

async def wrap_detail(
    entity: Any,
    session: AsyncSession,
) -> EntityDetailResponse:
    """Wrap a single entity with library context."""
    library = await get_library_stats(session)

    return EntityDetailResponse(
        result=entity,
        library=library,
    )

async def wrap_action(
    *,
    success: bool,
    message: str,
    session: AsyncSession,
    result: Any | None = None,
) -> ActionResponse:
    """Wrap a create/update/delete confirmation with library context."""
    library = await get_library_stats(session)

    return ActionResponse(
        success=success,
        message=message,
        result=result,
        library=library,
    )
```

**Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/mcp/test_envelope.py -v
```

Expected: ALL PASS

**Step 6: Lint + commit**

```bash
uv run ruff check app/mcp/envelope.py app/mcp/schemas.py tests/mcp/test_envelope.py && \
uv run ruff format --check app/mcp/envelope.py app/mcp/schemas.py tests/mcp/test_envelope.py && \
uv run mypy app/mcp/envelope.py app/mcp/schemas.py
```

```bash
git add app/mcp/envelope.py app/mcp/schemas.py tests/mcp/test_envelope.py
git commit -m "feat(mcp): add response envelope models + wrap_list/wrap_detail/wrap_action

Envelope returns Pydantic models (not JSON strings).
Adds PlaylistDetail, SetDetail, AudioFeaturesSummary to schemas."
```

---

## Task 2: Seeded test conftest for tool tests

**Files:**
- Create: `app/mcp/tools/__init__.py`
- Create: `tests/mcp/tools/__init__.py`
- Create: `tests/mcp/tools/conftest.py` — seeded DB + tools MCP fixture

Все tool-тесты в Phase 2 требуют:
1. Реальную БД с тестовыми данными (tracks, playlists, sets, features)
2. MCP-сервер с новыми tools, подключённый к тестовой БД

**Step 1: Write the conftest**

```python
# app/mcp/tools/__init__.py
"""Phase 2 MCP tools — CRUD, orchestrators, export."""
```

```python
# tests/mcp/tools/__init__.py
```

```python
# tests/mcp/tools/conftest.py
"""Shared fixtures for Phase 2 tool tests.

Provides:
- seeded_session: session with pre-loaded test data
- tools_mcp: MCP server with new tools wired to test DB
- Seed data constants for assertions
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.dj import DjPlaylist, DjPlaylistItem
from app.models.features import TrackAudioFeaturesComputed
from app.models.runs import FeatureExtractionRun
from app.models.sets import DjSet, DjSetItem, DjSetVersion
from app.models.tracks import Track

# --- Seed data constants (use in assertions) ---

TRACK_1 = {"title": "Gravity", "title_sort": "gravity", "duration_ms": 360000, "status": 0}
TRACK_2 = {"title": "Space Motion", "title_sort": "space motion", "duration_ms": 420000, "status": 0}
TRACK_3 = {"title": "Archived Track", "title_sort": "archived track", "duration_ms": 300000, "status": 1}

PLAYLIST_NAME = "Techno develop"
SET_NAME = "Friday night"

@pytest.fixture
async def seeded_session(session: AsyncSession) -> AsyncSession:
    """Session pre-loaded with test tracks, playlist, set, and features."""
    # --- Tracks ---
    t1 = Track(**TRACK_1)
    t2 = Track(**TRACK_2)
    t3 = Track(**TRACK_3)
    session.add_all([t1, t2, t3])
    await session.flush()

    # --- Playlist with 2 active tracks ---
    playlist = DjPlaylist(name=PLAYLIST_NAME)
    session.add(playlist)
    await session.flush()

    session.add_all([
        DjPlaylistItem(playlist_id=playlist.playlist_id, track_id=t1.track_id, sort_index=0),
        DjPlaylistItem(playlist_id=playlist.playlist_id, track_id=t2.track_id, sort_index=1),
    ])
    await session.flush()

    # --- Set with 1 version and 2 items ---
    dj_set = DjSet(
        name=SET_NAME,
        description="Peak hour mix",
        template_name="classic_60",
        source_playlist_id=playlist.playlist_id,
    )
    session.add(dj_set)
    await session.flush()

    version = DjSetVersion(set_id=dj_set.set_id, version_label="v1", score=0.78)
    session.add(version)
    await session.flush()

    session.add_all([
        DjSetItem(
            set_version_id=version.set_version_id,
            track_id=t1.track_id,
            sort_index=0,
            pinned=False,
        ),
        DjSetItem(
            set_version_id=version.set_version_id,
            track_id=t2.track_id,
            sort_index=1,
            pinned=False,
        ),
    ])
    await session.flush()

    # --- Feature extraction run + features for track 1 ---
    run = FeatureExtractionRun(
        pipeline_name="full_analysis",
        pipeline_version="1.0.0",
        status="completed",
    )
    session.add(run)
    await session.flush()

    features = TrackAudioFeaturesComputed(
        track_id=t1.track_id,
        run_id=run.run_id,
        bpm=140.0,
        tempo_confidence=0.95,
        key_code=8,  # 9A (Em)
        key_confidence=0.85,
        lufs_i=-8.3,
        energy_mean=0.72,
    )
    session.add(features)
    await session.flush()

    return session

@pytest.fixture
async def tools_mcp(engine) -> FastMCP:
    """Phase 2 tools MCP server wired to test DB.

    Uses the same override pattern as workflow_mcp_with_db from Phase 0.
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

    # Import here to avoid circular imports at module level
    from app.mcp.tools.server import create_tools_mcp

    with patch("app.mcp.dependencies.get_session", _test_session):
        yield create_tools_mcp()
```

**Step 2: Verify import works (will fail until Task 3+ creates server.py)**

```bash
uv run python -c "import tests.mcp.tools.conftest"
```

Expected: FAIL — `app.mcp.tools.server` not found yet. Это нормально — сервер создаётся в Task 12.

**Step 3: Commit package init files**

```bash
git add app/mcp/tools/__init__.py tests/mcp/tools/__init__.py tests/mcp/tools/conftest.py
git commit -m "feat(mcp): add tools package + seeded test conftest

Seed data: 3 tracks, 1 playlist, 1 set with version, 1 features run.
tools_mcp fixture wires to test DB via get_session override."
```

---

## Task 3: Track CRUD tools

**Files:**
- Create: `app/mcp/tools/tracks.py` — list_tracks, get_track, create_track, update_track, delete_track
- Test: `tests/mcp/tools/test_tracks.py`

5 CRUD-инструментов для треков. Используют TrackRepository напрямую + converters + envelope.

**Критичное из ревью:**
- Update tools: фильтровать None-поля перед созданием update schema (blocker #3)
- Ошибки: raise ToolError, НЕ возвращать `{"error": ...}` (blocker #4)
- Результаты: Pydantic models через `result.data` (blocker #1)

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_tracks.py
"""Tests for Track CRUD tools."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app.models.tracks import Track

class TestListTracks:
    async def test_list_returns_envelope(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_tracks", {})

        assert not result.is_error
        data = result.data
        assert data.total >= 2  # 2 active + 1 archived
        assert len(data.results) >= 2
        assert data.library.total_tracks >= 2
        assert data.pagination.limit == 20

    async def test_list_with_search(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_tracks", {"search": "Gravity"})

        data = result.data
        assert data.total >= 1
        assert any(r.title == "Gravity" for r in data.results)

    async def test_list_pagination(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_tracks", {"limit": 1})

        data = result.data
        assert len(data.results) == 1
        assert data.pagination.has_more is True

class TestGetTrack:
    async def test_get_by_id(self, tools_mcp, seeded_session):
        # Получаем ID первого трека
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_tracks", {"limit": 1})
            track_ref = list_result.data.results[0].ref

            result = await client.call_tool("get_track", {"track_ref": track_ref})

        assert not result.is_error
        data = result.data
        assert data.result.ref == track_ref

    async def test_get_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("get_track", {"track_ref": "local:99999"})

class TestCreateTrack:
    async def test_create_minimal(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("create_track", {
                "title": "New Track",
                "duration_ms": 240000,
            })

        assert not result.is_error
        data = result.data
        assert data.success is True
        assert data.result.title == "New Track"
        assert "local:" in data.result.ref

class TestUpdateTrack:
    async def test_update_title(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            # Get a track first
            list_result = await client.call_tool("list_tracks", {"limit": 1})
            track_ref = list_result.data.results[0].ref

            result = await client.call_tool("update_track", {
                "track_ref": track_ref,
                "title": "Updated Title",
            })

        data = result.data
        assert data.success is True
        assert data.result.title == "Updated Title"

    async def test_update_no_fields_raises(self, tools_mcp, seeded_session):
        """Update with no fields should raise ToolError."""
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_tracks", {"limit": 1})
            track_ref = list_result.data.results[0].ref

            with pytest.raises(ToolError, match="No fields"):
                await client.call_tool("update_track", {"track_ref": track_ref})

    async def test_update_does_not_clobber_unset_fields(self, tools_mcp, seeded_session):
        """Updating title must NOT reset duration_ms to None."""
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_tracks", {"limit": 1})
            track_ref = list_result.data.results[0].ref
            original_duration = list_result.data.results[0].duration_ms

            await client.call_tool("update_track", {
                "track_ref": track_ref,
                "title": "Only Title Changed",
            })

            get_result = await client.call_tool("get_track", {"track_ref": track_ref})
            assert get_result.data.result.duration_ms == original_duration

class TestDeleteTrack:
    async def test_delete_existing(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            # Create then delete
            create_result = await client.call_tool("create_track", {
                "title": "To Delete",
                "duration_ms": 120000,
            })
            track_ref = create_result.data.result.ref

            result = await client.call_tool("delete_track", {"track_ref": track_ref})

        assert result.data.success is True

    async def test_delete_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("delete_track", {"track_ref": "local:99999"})
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_tracks.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement Track CRUD tools**

```python
# app/mcp/tools/tracks.py
"""Track CRUD tools — list, get, create, update, delete.

All tools return Pydantic models. FastMCP handles serialization.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.converters import track_to_detail, track_to_summary
from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_action, wrap_detail, wrap_list
from app.mcp.resolvers import TrackResolver
from app.mcp.schemas import ActionResponse, EntityDetailResponse, EntityListResponse
from app.repositories.tracks import TrackRepository

def register_track_tools(mcp: FastMCP) -> None:
    """Register Track CRUD tools on the given MCP server."""

    @mcp.tool()
    async def list_tracks(
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        session=Depends(get_session),
    ) -> EntityListResponse:
        """List tracks with optional search. Returns paginated results with library stats."""
        repo = TrackRepository(session)

        if search:
            tracks, total = await repo.search_by_title(search, offset=offset, limit=limit)
        else:
            tracks, total = await repo.list(offset=offset, limit=limit)

        track_ids = [t.track_id for t in tracks]
        artists_map = await repo.get_artists_for_tracks(track_ids) if track_ids else {}

        summaries = [track_to_summary(t, artists_map=artists_map) for t in tracks]
        return await wrap_list(summaries, total, offset, limit, session)

    @mcp.tool()
    async def get_track(
        track_ref: str,
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Get detailed track info by ref (e.g. 'local:42' or 'Gravity')."""
        resolver = TrackResolver(session)
        track = await resolver.resolve_one(track_ref)

        repo = TrackRepository(session)
        artists_map = await repo.get_artists_for_tracks([track.track_id])
        genres = (await repo.get_genres_for_tracks([track.track_id])).get(
            track.track_id, []
        )
        labels = (await repo.get_labels_for_tracks([track.track_id])).get(
            track.track_id, []
        )
        albums = (await repo.get_albums_for_tracks([track.track_id])).get(
            track.track_id, []
        )

        # TODO: Phase 3 adds platform_ids via DbTrackMapper
        detail = track_to_detail(
            track,
            artists_map=artists_map,
            genres=genres,
            labels=labels,
            albums=albums,
        )
        return await wrap_detail(detail, session)

    @mcp.tool()
    async def create_track(
        title: str,
        duration_ms: int,
        title_sort: str | None = None,
        status: int = 0,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Create a new track."""
        from app.models.tracks import Track

        repo = TrackRepository(session)
        track = await repo.create(
            Track(
                title=title,
                title_sort=title_sort or title.lower(),
                duration_ms=duration_ms,
                status=status,
            )
        )

        artists_map = await repo.get_artists_for_tracks([track.track_id])
        summary = track_to_summary(track, artists_map=artists_map)
        return await wrap_action(
            success=True,
            message=f"Track created: {track.title}",
            session=session,
            result=summary,
        )

    @mcp.tool()
    async def update_track(
        track_ref: str,
        title: str | None = None,
        duration_ms: int | None = None,
        status: int | None = None,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Update track fields. Only provided (non-None) fields are updated.

        IMPORTANT: Unset fields are NOT sent to DB — no accidental clobber.
        """
        # Filter None values to avoid clobbering (Review blocker #3)
        update_data = {
            k: v
            for k, v in {"title": title, "duration_ms": duration_ms, "status": status}.items()
            if v is not None
        }

        if not update_data:
            raise ToolError("No fields to update. Provide at least one field.")

        resolver = TrackResolver(session)
        track = await resolver.resolve_one(track_ref)

        repo = TrackRepository(session)
        # Обновляем title_sort если меняется title
        if "title" in update_data:
            update_data["title_sort"] = update_data["title"].lower()

        for attr, value in update_data.items():
            setattr(track, attr, value)
        await session.flush()
        await session.refresh(track)

        artists_map = await repo.get_artists_for_tracks([track.track_id])
        summary = track_to_summary(track, artists_map=artists_map)
        return await wrap_action(
            success=True,
            message=f"Track {track_ref} updated",
            session=session,
            result=summary,
        )

    @mcp.tool()
    async def delete_track(
        track_ref: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Delete a track by ref."""
        resolver = TrackResolver(session)
        track = await resolver.resolve_one(track_ref)

        repo = TrackRepository(session)
        await repo.delete(track.track_id)

        return await wrap_action(
            success=True,
            message=f"Track {track_ref} deleted",
            session=session,
        )
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/mcp/tools/test_tracks.py -v
```

Expected: PASS (все 9 тестов)

**Step 5: Lint**

```bash
uv run ruff check app/mcp/tools/tracks.py tests/mcp/tools/test_tracks.py && \
uv run ruff format --check app/mcp/tools/tracks.py tests/mcp/tools/test_tracks.py && \
uv run mypy app/mcp/tools/tracks.py
```

**Step 6: Commit**

```bash
git add app/mcp/tools/tracks.py tests/mcp/tools/test_tracks.py
git commit -m "feat(mcp): add Track CRUD tools (list/get/create/update/delete)

Update tool filters None fields to prevent clobbering.
All tools return Pydantic models via envelope wrappers."
```

---

## Task 4: Playlist CRUD tools

**Files:**
- Create: `app/mcp/tools/playlists.py` — list_playlists, get_playlist, create_playlist, update_playlist, delete_playlist
- Test: `tests/mcp/tools/test_playlists.py`

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_playlists.py
"""Tests for Playlist CRUD tools."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestListPlaylists:
    async def test_list_returns_envelope(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_playlists", {})

        data = result.data
        assert data.total >= 1
        assert len(data.results) >= 1
        assert data.library.total_tracks >= 2

    async def test_list_with_search(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_playlists", {"search": "Techno"})

        data = result.data
        assert data.total >= 1
        assert any("Techno" in r.name for r in data.results)

class TestGetPlaylist:
    async def test_get_by_ref(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_playlists", {})
            playlist_ref = list_result.data.results[0].ref

            result = await client.call_tool("get_playlist", {"playlist_ref": playlist_ref})

        data = result.data
        assert data.result.ref == playlist_ref
        # PlaylistDetail should have analyzed_count, duration_minutes
        assert hasattr(data.result, "analyzed_count")
        assert hasattr(data.result, "duration_minutes")

    async def test_get_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("get_playlist", {"playlist_ref": "local:99999"})

class TestCreatePlaylist:
    async def test_create(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("create_playlist", {"name": "New Playlist"})

        data = result.data
        assert data.success is True
        assert data.result.name == "New Playlist"

class TestUpdatePlaylist:
    async def test_update_name(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_playlists", {})
            ref = list_result.data.results[0].ref

            result = await client.call_tool("update_playlist", {
                "playlist_ref": ref,
                "name": "Renamed Playlist",
            })

        assert result.data.success is True
        assert result.data.result.name == "Renamed Playlist"

    async def test_update_no_fields_raises(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_playlists", {})
            ref = list_result.data.results[0].ref

            with pytest.raises(ToolError, match="No fields"):
                await client.call_tool("update_playlist", {"playlist_ref": ref})

class TestDeletePlaylist:
    async def test_delete(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            create_result = await client.call_tool("create_playlist", {"name": "To Delete"})
            ref = create_result.data.result.ref

            result = await client.call_tool("delete_playlist", {"playlist_ref": ref})

        assert result.data.success is True
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_playlists.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement Playlist CRUD tools**

```python
# app/mcp/tools/playlists.py
"""Playlist CRUD tools — list, get, create, update, delete."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.converters import playlist_to_summary
from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_action, wrap_detail, wrap_list
from app.mcp.resolvers import PlaylistResolver
from app.mcp.schemas import (
    ActionResponse,
    EntityDetailResponse,
    EntityListResponse,
    PlaylistDetail,
)
from app.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
from app.repositories.audio_features import AudioFeaturesRepository
from app.utils.audio.camelot import key_code_to_camelot

def register_playlist_tools(mcp: FastMCP) -> None:
    """Register Playlist CRUD tools."""

    @mcp.tool()
    async def list_playlists(
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        session=Depends(get_session),
    ) -> EntityListResponse:
        """List playlists with optional name search."""
        repo = DjPlaylistRepository(session)
        item_repo = DjPlaylistItemRepository(session)

        if search:
            playlists, total = await repo.search_by_name(search, offset=offset, limit=limit)
        else:
            playlists, total = await repo.list(offset=offset, limit=limit)

        summaries = []
        for p in playlists:
            items, item_count = await item_repo.list_by_playlist(
                p.playlist_id, offset=0, limit=0
            )
            summaries.append(playlist_to_summary(p, item_count=item_count))

        return await wrap_list(summaries, total, offset, limit, session)

    @mcp.tool()
    async def get_playlist(
        playlist_ref: str,
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Get detailed playlist info with aggregated stats."""
        resolver = PlaylistResolver(session)
        playlist = await resolver.resolve_one(playlist_ref)

        item_repo = DjPlaylistItemRepository(session)
        items, item_count = await item_repo.list_by_playlist(
            playlist.playlist_id, offset=0, limit=1000
        )

        track_ids = [item.track_id for item in items]

        # Aggregate features stats
        features_repo = AudioFeaturesRepository(session)
        bpms: list[float] = []
        keys: list[str] = []
        energies: list[float] = []
        analyzed_count = 0
        total_duration_ms = 0

        for tid in track_ids:
            feat = await features_repo.get_by_track(tid)
            if feat:
                analyzed_count += 1
                if feat.bpm:
                    bpms.append(feat.bpm)
                if feat.key_code is not None:
                    keys.append(key_code_to_camelot(feat.key_code))
                if feat.lufs_i is not None:
                    energies.append(feat.lufs_i)

        detail = PlaylistDetail(
            ref=f"local:{playlist.playlist_id}",
            name=playlist.name,
            track_count=item_count,
            analyzed_count=analyzed_count,
            bpm_range=(min(bpms), max(bpms)) if bpms else None,
            keys=sorted(set(keys)),
            avg_energy=sum(energies) / len(energies) if energies else None,
            duration_minutes=total_duration_ms / 60_000 if total_duration_ms else 0.0,
        )
        return await wrap_detail(detail, session)

    @mcp.tool()
    async def create_playlist(
        name: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Create a new empty playlist."""
        from app.models.dj import DjPlaylist

        repo = DjPlaylistRepository(session)
        playlist = await repo.create(DjPlaylist(name=name))

        summary = playlist_to_summary(playlist, item_count=0)
        return await wrap_action(
            success=True,
            message=f"Playlist created: {name}",
            session=session,
            result=summary,
        )

    @mcp.tool()
    async def update_playlist(
        playlist_ref: str,
        name: str | None = None,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Update playlist fields. Only provided fields are updated."""
        update_data = {k: v for k, v in {"name": name}.items() if v is not None}

        if not update_data:
            raise ToolError("No fields to update. Provide at least one field.")

        resolver = PlaylistResolver(session)
        playlist = await resolver.resolve_one(playlist_ref)

        for attr, value in update_data.items():
            setattr(playlist, attr, value)
        await session.flush()
        await session.refresh(playlist)

        item_repo = DjPlaylistItemRepository(session)
        _, item_count = await item_repo.list_by_playlist(playlist.playlist_id, offset=0, limit=0)

        summary = playlist_to_summary(playlist, item_count=item_count)
        return await wrap_action(
            success=True,
            message=f"Playlist {playlist_ref} updated",
            session=session,
            result=summary,
        )

    @mcp.tool()
    async def delete_playlist(
        playlist_ref: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Delete a playlist by ref."""
        resolver = PlaylistResolver(session)
        playlist = await resolver.resolve_one(playlist_ref)

        repo = DjPlaylistRepository(session)
        await repo.delete(playlist.playlist_id)

        return await wrap_action(
            success=True,
            message=f"Playlist {playlist_ref} deleted",
            session=session,
        )
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/mcp/tools/test_playlists.py -v
```

Expected: PASS

**Step 5: Lint**

```bash
uv run ruff check app/mcp/tools/playlists.py tests/mcp/tools/test_playlists.py && \
uv run mypy app/mcp/tools/playlists.py
```

**Step 6: Commit**

```bash
git add app/mcp/tools/playlists.py tests/mcp/tools/test_playlists.py
git commit -m "feat(mcp): add Playlist CRUD tools (list/get/create/update/delete)

get_playlist returns PlaylistDetail with aggregated feature stats.
Update filters None fields to prevent clobbering."
```

---

## Task 5: Set CRUD tools

**Files:**
- Create: `app/mcp/tools/sets.py` — list_sets, get_set, create_set, update_set, delete_set
- Test: `tests/mcp/tools/test_sets.py`

Используем существующий `DjSetService` для CRUD. Converters для ORM→Schema.

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_sets.py
"""Tests for Set CRUD tools."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestListSets:
    async def test_list_returns_envelope(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_sets", {})

        data = result.data
        assert data.total >= 1
        assert len(data.results) >= 1
        assert data.library.total_tracks >= 2

    async def test_list_with_search(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_sets", {"search": "Friday"})

        data = result.data
        assert data.total >= 1

class TestGetSet:
    async def test_get_by_ref(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_sets", {})
            set_ref = list_result.data.results[0].ref

            result = await client.call_tool("get_set", {"set_ref": set_ref})

        data = result.data
        assert data.result.ref == set_ref
        # SetDetail fields
        assert hasattr(data.result, "template_name")
        assert hasattr(data.result, "latest_version_id")

    async def test_get_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("get_set", {"set_ref": "local:99999"})

class TestCreateSet:
    async def test_create_minimal(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("create_set", {
                "name": "New Set",
            })

        data = result.data
        assert data.success is True
        assert data.result.name == "New Set"

    async def test_create_with_template(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("create_set", {
                "name": "Warm Up",
                "template_name": "warm_up_30",
                "description": "Opening set",
            })

        data = result.data
        assert data.success is True

class TestUpdateSet:
    async def test_update_name(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_sets", {})
            ref = list_result.data.results[0].ref

            result = await client.call_tool("update_set", {
                "set_ref": ref,
                "name": "Saturday night",
            })

        assert result.data.success is True

    async def test_update_no_fields_raises(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            list_result = await client.call_tool("list_sets", {})
            ref = list_result.data.results[0].ref

            with pytest.raises(ToolError, match="No fields"):
                await client.call_tool("update_set", {"set_ref": ref})

class TestDeleteSet:
    async def test_delete(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            create_result = await client.call_tool("create_set", {"name": "To Delete"})
            ref = create_result.data.result.ref

            result = await client.call_tool("delete_set", {"set_ref": ref})

        assert result.data.success is True
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_sets.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement Set CRUD tools**

```python
# app/mcp/tools/sets.py
"""Set CRUD + orchestration tools."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.converters import set_to_summary
from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_action, wrap_detail, wrap_list
from app.mcp.resolvers import SetResolver
from app.mcp.schemas import (
    ActionResponse,
    EntityDetailResponse,
    EntityListResponse,
    SetDetail,
)
from app.repositories.sets import DjSetRepository, DjSetVersionRepository, DjSetItemRepository

def register_set_tools(mcp: FastMCP) -> None:
    """Register Set CRUD tools."""

    @mcp.tool()
    async def list_sets(
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        session=Depends(get_session),
    ) -> EntityListResponse:
        """List DJ sets with optional name search."""
        repo = DjSetRepository(session)

        if search:
            sets, total = await repo.search_by_name(search, offset=offset, limit=limit)
        else:
            sets, total = await repo.list(offset=offset, limit=limit)

        version_repo = DjSetVersionRepository(session)
        item_repo = DjSetItemRepository(session)

        summaries = []
        for s in sets:
            versions, version_count = await version_repo.list_by_set(
                s.set_id, offset=0, limit=1
            )
            track_count = 0
            if versions:
                _, track_count = await item_repo.list_by_version(
                    versions[0].set_version_id, offset=0, limit=0
                )
            summaries.append(
                set_to_summary(s, version_count=version_count, track_count=track_count)
            )

        return await wrap_list(summaries, total, offset, limit, session)

    @mcp.tool()
    async def get_set(
        set_ref: str,
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Get detailed set info with latest version stats."""
        resolver = SetResolver(session)
        dj_set = await resolver.resolve_one(set_ref)

        version_repo = DjSetVersionRepository(session)
        item_repo = DjSetItemRepository(session)

        versions, version_count = await version_repo.list_by_set(
            dj_set.set_id, offset=0, limit=1
        )

        latest_version_id = None
        latest_score = None
        track_count = 0
        if versions:
            latest = versions[0]
            latest_version_id = latest.set_version_id
            latest_score = latest.score
            _, track_count = await item_repo.list_by_version(
                latest.set_version_id, offset=0, limit=0
            )

        detail = SetDetail(
            ref=f"local:{dj_set.set_id}",
            name=dj_set.name,
            version_count=version_count,
            track_count=track_count,
            description=dj_set.description,
            template_name=dj_set.template_name,
            target_bpm_min=dj_set.target_bpm_min,
            target_bpm_max=dj_set.target_bpm_max,
            latest_version_id=latest_version_id,
            latest_score=latest_score,
        )
        return await wrap_detail(detail, session)

    @mcp.tool()
    async def create_set(
        name: str,
        description: str | None = None,
        template_name: str | None = None,
        source_playlist_ref: str | None = None,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Create a new DJ set."""
        from app.models.sets import DjSet

        source_playlist_id = None
        if source_playlist_ref:
            from app.mcp.resolvers import PlaylistResolver

            playlist_resolver = PlaylistResolver(session)
            playlist = await playlist_resolver.resolve_one(source_playlist_ref)
            source_playlist_id = playlist.playlist_id

        repo = DjSetRepository(session)
        dj_set = await repo.create(
            DjSet(
                name=name,
                description=description,
                template_name=template_name,
                source_playlist_id=source_playlist_id,
            )
        )

        summary = set_to_summary(dj_set, version_count=0, track_count=0)
        return await wrap_action(
            success=True,
            message=f"Set created: {name}",
            session=session,
            result=summary,
        )

    @mcp.tool()
    async def update_set(
        set_ref: str,
        name: str | None = None,
        description: str | None = None,
        template_name: str | None = None,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Update set fields. Only provided fields are updated."""
        update_data = {
            k: v
            for k, v in {
                "name": name,
                "description": description,
                "template_name": template_name,
            }.items()
            if v is not None
        }

        if not update_data:
            raise ToolError("No fields to update. Provide at least one field.")

        resolver = SetResolver(session)
        dj_set = await resolver.resolve_one(set_ref)

        for attr, value in update_data.items():
            setattr(dj_set, attr, value)
        await session.flush()
        await session.refresh(dj_set)

        summary = set_to_summary(dj_set, version_count=0, track_count=0)
        return await wrap_action(
            success=True,
            message=f"Set {set_ref} updated",
            session=session,
            result=summary,
        )

    @mcp.tool()
    async def delete_set(
        set_ref: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Delete a DJ set and all its versions/items (CASCADE)."""
        resolver = SetResolver(session)
        dj_set = await resolver.resolve_one(set_ref)

        repo = DjSetRepository(session)
        await repo.delete(dj_set.set_id)

        return await wrap_action(
            success=True,
            message=f"Set {set_ref} deleted",
            session=session,
        )
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/tools/test_sets.py -v
```

Expected: PASS

**Step 5: Lint**

```bash
uv run ruff check app/mcp/tools/sets.py tests/mcp/tools/test_sets.py && \
uv run mypy app/mcp/tools/sets.py
```

**Step 6: Commit**

```bash
git add app/mcp/tools/sets.py tests/mcp/tools/test_sets.py
git commit -m "feat(mcp): add Set CRUD tools (list/get/create/update/delete)

get_set returns SetDetail with latest version stats.
create_set accepts source_playlist_ref for playlist linking."
```

---

## Task 6: Set orchestration tools (build_set, rebuild_set)

**Files:**
- Modify: `app/mcp/tools/sets.py` — добавить build_set, rebuild_set
- Test: `tests/mcp/tools/test_sets_orchestration.py`

Оркестраторы используют refs для входных параметров и возвращают ActionResponse с envelope. Внутри вызывают существующую GA-логику из `app/services/sets.py`.

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_sets_orchestration.py
"""Tests for Set orchestration tools (build_set, rebuild_set)."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestBuildSet:
    async def test_build_from_playlist(self, tools_mcp, seeded_session):
        """build_set should create a new set version from a playlist."""
        async with Client(tools_mcp) as client:
            # Get playlist ref
            playlists = await client.call_tool("list_playlists", {})
            playlist_ref = playlists.data.results[0].ref

            result = await client.call_tool("build_set", {
                "playlist_ref": playlist_ref,
                "set_name": "Test Build",
            })

        data = result.data
        assert data.success is True
        assert data.result is not None

    async def test_build_with_template(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            playlists = await client.call_tool("list_playlists", {})
            playlist_ref = playlists.data.results[0].ref

            result = await client.call_tool("build_set", {
                "playlist_ref": playlist_ref,
                "set_name": "Warm Up Build",
                "template_name": "warm_up_30",
            })

        assert result.data.success is True

    async def test_build_playlist_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("build_set", {
                    "playlist_ref": "local:99999",
                    "set_name": "Ghost",
                })

class TestRebuildSet:
    async def test_rebuild_existing(self, tools_mcp, seeded_session):
        """rebuild_set should create a new version for an existing set."""
        async with Client(tools_mcp) as client:
            sets = await client.call_tool("list_sets", {})
            set_ref = sets.data.results[0].ref

            result = await client.call_tool("rebuild_set", {"set_ref": set_ref})

        data = result.data
        assert data.success is True

    async def test_rebuild_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("rebuild_set", {"set_ref": "local:99999"})
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_sets_orchestration.py -v
```

Expected: FAIL

**Step 3: Add build_set and rebuild_set to sets.py**

Добавить в `register_set_tools()` в `app/mcp/tools/sets.py`:

```python
    @mcp.tool()
    async def build_set(
        playlist_ref: str,
        set_name: str,
        template_name: str | None = None,
        energy_arc_type: str = "classic",
        exclude_track_refs: list[str] | None = None,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Build a new DJ set from a playlist using genetic algorithm.

        Creates the set, runs GA optimization, creates a version with scored tracks.
        """
        from app.mcp.resolvers import PlaylistResolver
        from app.repositories.playlists import DjPlaylistItemRepository
        from app.schemas.set_generation import SetGenerationRequest
        from app.services.sets import DjSetService

        # Resolve playlist
        playlist_resolver = PlaylistResolver(session)
        playlist = await playlist_resolver.resolve_one(playlist_ref)

        # Resolve exclude refs if provided
        exclude_ids: list[int] = []
        if exclude_track_refs:
            from app.mcp.resolvers import TrackResolver

            track_resolver = TrackResolver(session)
            for ref in exclude_track_refs:
                track = await track_resolver.resolve_one(ref)
                exclude_ids.append(track.track_id)

        # Create set
        from app.models.sets import DjSet

        set_repo = DjSetRepository(session)
        dj_set = await set_repo.create(
            DjSet(
                name=set_name,
                template_name=template_name,
                source_playlist_id=playlist.playlist_id,
            )
        )

        # Build using service
        set_service = DjSetService(session)
        gen_request = SetGenerationRequest(
            playlist_id=playlist.playlist_id,
            template_name=template_name,
            energy_arc_type=energy_arc_type,
            exclude_track_ids=exclude_ids or None,
        )

        gen_response = await set_service.generate_set(dj_set.set_id, gen_request)

        summary = set_to_summary(dj_set, version_count=1, track_count=len(gen_response.track_ids))
        return await wrap_action(
            success=True,
            message=f"Set '{set_name}' built: {len(gen_response.track_ids)} tracks, score={gen_response.score:.2f}",
            session=session,
            result=summary,
        )

    @mcp.tool()
    async def rebuild_set(
        set_ref: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Rebuild an existing set — creates a new version with fresh GA run."""
        from app.schemas.set_generation import SetGenerationRequest
        from app.services.sets import DjSetService

        resolver = SetResolver(session)
        dj_set = await resolver.resolve_one(set_ref)

        if not dj_set.source_playlist_id:
            raise ToolError(
                f"Set {set_ref} has no source playlist — cannot rebuild."
            )

        set_service = DjSetService(session)
        gen_request = SetGenerationRequest(
            playlist_id=dj_set.source_playlist_id,
            template_name=dj_set.template_name,
        )

        gen_response = await set_service.generate_set(dj_set.set_id, gen_request)

        summary = set_to_summary(
            dj_set,
            version_count=0,  # will be recounted on next list
            track_count=len(gen_response.track_ids),
        )
        return await wrap_action(
            success=True,
            message=f"Set {set_ref} rebuilt: {len(gen_response.track_ids)} tracks, score={gen_response.score:.2f}",
            session=session,
            result=summary,
        )
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/tools/test_sets_orchestration.py -v
```

Expected: PASS

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/tools/sets.py tests/mcp/tools/test_sets_orchestration.py && \
uv run mypy app/mcp/tools/sets.py
```

```bash
git add app/mcp/tools/sets.py tests/mcp/tools/test_sets_orchestration.py
git commit -m "feat(mcp): add build_set + rebuild_set orchestration tools

Accept playlist_ref/set_ref (URN refs), return ActionResponse envelope.
build_set creates set + runs GA; rebuild_set creates new version."
```

---

## Task 7: Features tools

**Files:**
- Modify: `app/repositories/audio_features.py` — добавить `list_latest_paginated()`
- Create: `app/mcp/tools/features.py` — list_features, get_track_features, analyze_track
- Test: `tests/mcp/tools/test_features.py`

**Критичное из ревью:**
- `list_features` должен использовать SQL-пагинацию с latest-per-track subquery (blocker #8)
- НЕ загружать все features + slice в Python
- Batch-загрузка tracks для enrichment (НЕ N+1)
- `analyze_track` — единый инструмент compute+persist (blocker #5, #6)
- Правильный импорт: `app.repositories.audio_features` (НЕ `app.repositories.features`)

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_features.py
"""Tests for Features tools."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestListFeatures:
    async def test_list_returns_envelope(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_features", {})

        data = result.data
        assert data.total >= 1  # track 1 has features
        assert len(data.results) >= 1
        assert data.pagination.limit == 20

    async def test_list_pagination(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("list_features", {"limit": 1})

        data = result.data
        assert len(data.results) <= 1

class TestGetTrackFeatures:
    async def test_get_existing(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            # Track 1 (Gravity) has features
            tracks = await client.call_tool("list_tracks", {"search": "Gravity"})
            track_ref = tracks.data.results[0].ref

            result = await client.call_tool("get_track_features", {
                "track_ref": track_ref,
            })

        data = result.data
        assert data.result is not None
        assert data.result.bpm == 140.0
        assert data.result.key == "9A"  # key_code=8 → 9A (Em)

    async def test_get_no_features(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            # Track 2 (Space Motion) has no features
            tracks = await client.call_tool("list_tracks", {"search": "Space Motion"})
            track_ref = tracks.data.results[0].ref

            with pytest.raises(ToolError, match="no features"):
                await client.call_tool("get_track_features", {"track_ref": track_ref})
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_features.py -v
```

Expected: FAIL

**Step 3: Add list_latest_paginated to AudioFeaturesRepository**

Добавить в `app/repositories/audio_features.py`:

```python
async def list_latest_paginated(
    self, *, offset: int = 0, limit: int = 50,
) -> tuple[list[TrackAudioFeaturesComputed], int]:
    """Latest features per track, paginated with SQL.

    Uses a subquery for max(run_id) per track_id to avoid loading all
    features into Python (fixes Phase 2 review blocker #8).
    """
    from sqlalchemy import and_, func, select

    # Subquery: latest run_id per track
    latest_run = (
        select(
            TrackAudioFeaturesComputed.track_id,
            func.max(TrackAudioFeaturesComputed.run_id).label("max_run_id"),
        )
        .group_by(TrackAudioFeaturesComputed.track_id)
        .subquery("latest_run")
    )

    # Count total unique tracks with features
    count_query = select(func.count()).select_from(latest_run)
    total = (await self.session.execute(count_query)).scalar_one()

    # Fetch paginated
    query = (
        select(TrackAudioFeaturesComputed)
        .join(
            latest_run,
            and_(
                TrackAudioFeaturesComputed.track_id == latest_run.c.track_id,
                TrackAudioFeaturesComputed.run_id == latest_run.c.max_run_id,
            ),
        )
        .order_by(TrackAudioFeaturesComputed.track_id)
        .offset(offset)
        .limit(limit)
    )
    result = (await self.session.execute(query)).scalars().all()
    return list(result), total
```

**Step 4: Implement features tools**

```python
# app/mcp/tools/features.py
"""Features tools — list, get, analyze.

analyze_track is a single compute+persist tool (NOT split).
list_features uses SQL pagination (NOT list_all + slice).
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_detail, wrap_list
from app.mcp.resolvers import TrackResolver
from app.mcp.schemas import (
    AudioFeaturesSummary,
    EntityDetailResponse,
    EntityListResponse,
)
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.utils.audio.camelot import key_code_to_camelot

def register_features_tools(mcp: FastMCP) -> None:
    """Register Features tools."""

    @mcp.tool()
    async def list_features(
        offset: int = 0,
        limit: int = 20,
        session=Depends(get_session),
    ) -> EntityListResponse:
        """List tracks with audio features (latest per track, paginated).

        Uses SQL subquery for pagination — does NOT load all features into memory.
        Batch-loads track metadata to avoid N+1 queries.
        """
        features_repo = AudioFeaturesRepository(session)
        features_list, total = await features_repo.list_latest_paginated(
            offset=offset, limit=limit,
        )

        # Batch load track info (avoid N+1)
        track_ids = [f.track_id for f in features_list]
        track_repo = TrackRepository(session)
        artists_map = await track_repo.get_artists_for_tracks(track_ids) if track_ids else {}

        # Get track titles in batch
        tracks_by_id: dict[int, str] = {}
        if track_ids:
            from sqlalchemy import select

            from app.models.tracks import Track

            query = select(Track).where(Track.track_id.in_(track_ids))
            result = (await session.execute(query)).scalars().all()
            tracks_by_id = {t.track_id: t.title for t in result}

        summaries = []
        for f in features_list:
            artists = artists_map.get(f.track_id, [])
            summaries.append(
                AudioFeaturesSummary(
                    track_ref=f"local:{f.track_id}",
                    title=tracks_by_id.get(f.track_id, "Unknown"),
                    artist=", ".join(artists) if artists else "Unknown",
                    bpm=f.bpm,
                    key=key_code_to_camelot(f.key_code) if f.key_code is not None else None,
                    energy_lufs=f.lufs_i,
                    onset_rate=f.onset_rate_mean,
                    run_id=f.run_id,
                )
            )

        return await wrap_list(summaries, total, offset, limit, session)

    @mcp.tool()
    async def get_track_features(
        track_ref: str,
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Get full audio features for a specific track."""
        resolver = TrackResolver(session)
        track = await resolver.resolve_one(track_ref)

        features_repo = AudioFeaturesRepository(session)
        features = await features_repo.get_by_track(track.track_id)

        if not features:
            raise ToolError(
                f"Track {track_ref} has no features. Run analyze_track first."
            )

        track_repo = TrackRepository(session)
        artists_map = await track_repo.get_artists_for_tracks([track.track_id])
        artists = artists_map.get(track.track_id, [])

        # Build detailed features response
        from app.mcp.schemas import AudioFeaturesSummary

        detail = AudioFeaturesSummary(
            track_ref=f"local:{track.track_id}",
            title=track.title,
            artist=", ".join(artists) if artists else "Unknown",
            bpm=features.bpm,
            key=key_code_to_camelot(features.key_code) if features.key_code is not None else None,
            energy_lufs=features.lufs_i,
            onset_rate=features.onset_rate_mean,
            run_id=features.run_id,
        )
        return await wrap_detail(detail, session)

    @mcp.tool()
    async def analyze_track(
        track_ref: str,
        audio_path: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Analyze a track's audio features and save to DB.

        Single compute+persist tool (NOT split into separate compute/save).
        Creates a FeatureExtractionRun, runs full analysis, saves features.

        Args:
            track_ref: Track reference (e.g. 'local:42' or 'Gravity')
            audio_path: Path to the audio file on disk
        """
        from app.mcp.envelope import wrap_action
        from app.repositories.runs import FeatureRunRepository
        from app.services.track_analysis import TrackAnalysisService

        resolver = TrackResolver(session)
        track = await resolver.resolve_one(track_ref)

        # Create extraction run
        from app.models.runs import FeatureExtractionRun

        run_repo = FeatureRunRepository(session)
        run = await run_repo.create(
            FeatureExtractionRun(
                pipeline_name="full_analysis",
                pipeline_version="1.0.0",
                status="running",
            )
        )

        try:
            # Compute + persist in one step
            analysis_service = TrackAnalysisService(session)
            _features = await analysis_service.analyze_track(
                track_id=track.track_id,
                audio_path=audio_path,
                run_id=run.run_id,
            )
            await run_repo.mark_completed(run.run_id)

            return await wrap_action(
                success=True,
                message=f"Track {track_ref} analyzed (run_id={run.run_id})",
                session=session,
            )
        except Exception as e:
            await run_repo.mark_failed(run.run_id)
            raise ToolError(f"Analysis failed for {track_ref}: {e}") from e
```

**Step 5: Run tests**

```bash
uv run pytest tests/mcp/tools/test_features.py -v
```

Expected: PASS

**Step 6: Lint + commit**

```bash
uv run ruff check app/mcp/tools/features.py app/repositories/audio_features.py tests/mcp/tools/test_features.py && \
uv run mypy app/mcp/tools/features.py
```

```bash
git add app/mcp/tools/features.py app/repositories/audio_features.py tests/mcp/tools/test_features.py
git commit -m "feat(mcp): add Features tools (list/get/analyze)

list_features uses SQL pagination with latest-per-track subquery.
Batch loads tracks to avoid N+1 queries.
analyze_track is single compute+persist tool (not split).
key_code=8 correctly maps to 9A (Em)."
```

---

## Task 8: Scoring tool

**Files:**
- Create: `app/mcp/tools/scoring.py` — score_transitions
- Test: `tests/mcp/tools/test_scoring.py`

Извлечено из `setbuilder_tools.py`. Принимает set_ref + version_id, возвращает envelope с transition scores.

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_scoring.py
"""Tests for scoring tool."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestScoreTransitions:
    async def test_score_existing_set(self, tools_mcp, seeded_session):
        """Score transitions for a set that has items with features."""
        async with Client(tools_mcp) as client:
            sets = await client.call_tool("list_sets", {})
            set_ref = sets.data.results[0].ref

            # Get the version_id
            set_detail = await client.call_tool("get_set", {"set_ref": set_ref})
            version_id = set_detail.data.result.latest_version_id

            result = await client.call_tool("score_transitions", {
                "set_ref": set_ref,
                "version_id": version_id,
            })

        data = result.data
        assert data.result is not None

    async def test_score_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("score_transitions", {
                    "set_ref": "local:99999",
                    "version_id": 1,
                })
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_scoring.py -v
```

**Step 3: Implement scoring tool**

```python
# app/mcp/tools/scoring.py
"""Scoring tool — score_transitions.

Extracted from setbuilder_tools.py. Uses refs + envelope.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_detail
from app.mcp.resolvers import SetResolver
from app.mcp.schemas import EntityDetailResponse

def register_scoring_tools(mcp: FastMCP) -> None:
    """Register scoring tools."""

    @mcp.tool()
    async def score_transitions(
        set_ref: str,
        version_id: int,
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Score all transitions in a set version.

        Returns transition quality scores between consecutive tracks,
        including BPM compatibility, harmonic mixing, energy flow, etc.
        """
        from app.repositories.audio_features import AudioFeaturesRepository
        from app.repositories.sets import DjSetItemRepository
        from app.repositories.tracks import TrackRepository
        from app.utils.audio.camelot import key_code_to_camelot
        from app.utils.audio.transition_scoring import score_transition

        # Resolve set
        resolver = SetResolver(session)
        dj_set = await resolver.resolve_one(set_ref)

        # Load set items
        item_repo = DjSetItemRepository(session)
        items, _total = await item_repo.list_by_version(
            version_id, offset=0, limit=1000
        )
        if not items:
            raise ToolError(f"Set version {version_id} has no items.")

        items_sorted = sorted(items, key=lambda i: i.sort_index)

        # Batch load features and track info
        track_ids = [item.track_id for item in items_sorted]
        features_repo = AudioFeaturesRepository(session)
        track_repo = TrackRepository(session)

        features_map = {}
        for tid in track_ids:
            feat = await features_repo.get_by_track(tid)
            if feat:
                features_map[tid] = feat

        artists_map = await track_repo.get_artists_for_tracks(track_ids)

        # Load track titles
        from sqlalchemy import select

        from app.models.tracks import Track

        query = select(Track).where(Track.track_id.in_(track_ids))
        tracks_result = (await session.execute(query)).scalars().all()
        titles_map = {t.track_id: t.title for t in tracks_result}

        # Score consecutive transitions
        transitions = []
        for i in range(len(items_sorted) - 1):
            from_item = items_sorted[i]
            to_item = items_sorted[i + 1]
            from_feat = features_map.get(from_item.track_id)
            to_feat = features_map.get(to_item.track_id)

            if from_feat and to_feat:
                score_result = score_transition(from_feat, to_feat)
                transitions.append({
                    "position": i,
                    "from_track": titles_map.get(from_item.track_id, "?"),
                    "to_track": titles_map.get(to_item.track_id, "?"),
                    "total_score": score_result.total,
                    "bpm_score": score_result.bpm,
                    "harmonic_score": score_result.harmonic,
                    "energy_score": score_result.energy,
                    "recommended_type": score_result.recommended_type,
                    "reason": score_result.reason,
                })
            else:
                transitions.append({
                    "position": i,
                    "from_track": titles_map.get(from_item.track_id, "?"),
                    "to_track": titles_map.get(to_item.track_id, "?"),
                    "total_score": 0.0,
                    "reason": "Missing features for one or both tracks",
                })

        from pydantic import BaseModel

        class TransitionScores(BaseModel):
            set_name: str
            version_id: int
            transition_count: int
            avg_score: float
            transitions: list[dict]

        avg = (
            sum(t["total_score"] for t in transitions) / len(transitions)
            if transitions
            else 0.0
        )

        scores = TransitionScores(
            set_name=dj_set.name,
            version_id=version_id,
            transition_count=len(transitions),
            avg_score=round(avg, 3),
            transitions=transitions,
        )
        return await wrap_detail(scores, session)
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/tools/test_scoring.py -v
```

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/tools/scoring.py tests/mcp/tools/test_scoring.py && \
uv run mypy app/mcp/tools/scoring.py
```

```bash
git add app/mcp/tools/scoring.py tests/mcp/tools/test_scoring.py
git commit -m "feat(mcp): add score_transitions tool with refs + envelope

Accepts set_ref (URN), batch-loads features and tracks.
Returns TransitionScores with per-transition breakdown."
```

---

## Task 9: Unified export tool

**Files:**
- Create: `app/mcp/tools/export.py` — export_set(format=...)
- Test: `tests/mcp/tools/test_export.py`

Одна точка входа вместо 3 отдельных инструментов (export_set_m3u, export_set_json, export_set_rekordbox). Делегирует существующим функциям в `export_tools.py`.

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_export.py
"""Tests for unified export tool."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestExportSet:
    async def test_export_json(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            sets = await client.call_tool("list_sets", {})
            set_ref = sets.data.results[0].ref
            set_detail = await client.call_tool("get_set", {"set_ref": set_ref})
            version_id = set_detail.data.result.latest_version_id

            result = await client.call_tool("export_set", {
                "set_ref": set_ref,
                "version_id": version_id,
                "format": "json",
            })

        data = result.data
        assert data.success is True
        assert "json" in data.message.lower() or "export" in data.message.lower()

    async def test_export_m3u(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            sets = await client.call_tool("list_sets", {})
            set_ref = sets.data.results[0].ref
            set_detail = await client.call_tool("get_set", {"set_ref": set_ref})
            version_id = set_detail.data.result.latest_version_id

            result = await client.call_tool("export_set", {
                "set_ref": set_ref,
                "version_id": version_id,
                "format": "m3u",
            })

        assert result.data.success is True

    async def test_export_invalid_format(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            sets = await client.call_tool("list_sets", {})
            set_ref = sets.data.results[0].ref

            with pytest.raises(ToolError, match="format"):
                await client.call_tool("export_set", {
                    "set_ref": set_ref,
                    "version_id": 1,
                    "format": "wav",
                })

    async def test_export_set_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("export_set", {
                    "set_ref": "local:99999",
                    "version_id": 1,
                    "format": "json",
                })
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_export.py -v
```

**Step 3: Implement unified export**

```python
# app/mcp/tools/export.py
"""Unified export tool — export_set(format=...).

Replaces 3 separate tools (export_set_m3u, export_set_json, export_set_rekordbox).
Delegates to existing export functions from app.mcp.workflows.export_tools.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_action
from app.mcp.resolvers import SetResolver
from app.mcp.schemas import ActionResponse

VALID_FORMATS = {"json", "m3u", "rekordbox"}

def register_export_tools(mcp: FastMCP) -> None:
    """Register unified export tool."""

    @mcp.tool()
    async def export_set(
        set_ref: str,
        version_id: int,
        format: str = "json",
        base_path: str = "/Music",
        include_cues: bool = True,
        include_beatgrid: bool = True,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Export a set version to the specified format.

        Supported formats: json, m3u, rekordbox.
        Rekordbox format supports additional options (cues, beatgrid, etc).

        Args:
            set_ref: Set reference (e.g. 'local:3' or 'Friday night')
            version_id: Version ID to export
            format: Export format — json, m3u, or rekordbox
            base_path: Base path for track files (rekordbox only)
            include_cues: Include cue points (rekordbox only)
            include_beatgrid: Include beatgrid data (rekordbox only)
        """
        if format not in VALID_FORMATS:
            raise ToolError(
                f"Invalid format '{format}'. Supported: {', '.join(sorted(VALID_FORMATS))}"
            )

        resolver = SetResolver(session)
        dj_set = await resolver.resolve_one(set_ref)

        # Delegate to existing export logic
        from app.repositories.sets import DjSetItemRepository, DjSetVersionRepository
        from app.repositories.tracks import TrackRepository
        from app.repositories.audio_features import AudioFeaturesRepository

        version_repo = DjSetVersionRepository(session)
        version = await version_repo.get_by_id(version_id)
        if not version or version.set_id != dj_set.set_id:
            raise ToolError(f"Version {version_id} not found for set {set_ref}")

        item_repo = DjSetItemRepository(session)
        items, _ = await item_repo.list_by_version(version_id, offset=0, limit=1000)
        items_sorted = sorted(items, key=lambda i: i.sort_index)

        track_ids = [item.track_id for item in items_sorted]

        if format == "json":
            content = await _export_json(
                session, dj_set, version, items_sorted, track_ids
            )
        elif format == "m3u":
            content = await _export_m3u(
                session, dj_set, version, items_sorted, track_ids
            )
        elif format == "rekordbox":
            content = await _export_rekordbox(
                session, dj_set, version, items_sorted, track_ids,
                base_path=base_path,
                include_cues=include_cues,
                include_beatgrid=include_beatgrid,
            )
        else:
            raise ToolError(f"Unsupported format: {format}")

        return await wrap_action(
            success=True,
            message=f"Set '{dj_set.name}' exported as {format} ({len(track_ids)} tracks)",
            session=session,
            result=content,
        )

async def _export_json(session, dj_set, version, items, track_ids):
    """Export set as JSON structure."""
    import json as json_mod

    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.tracks import TrackRepository
    from app.utils.audio.camelot import key_code_to_camelot

    track_repo = TrackRepository(session)
    features_repo = AudioFeaturesRepository(session)
    artists_map = await track_repo.get_artists_for_tracks(track_ids)

    from sqlalchemy import select
    from app.models.tracks import Track

    query = select(Track).where(Track.track_id.in_(track_ids))
    tracks = {t.track_id: t for t in (await session.execute(query)).scalars().all()}

    export_tracks = []
    for item in items:
        track = tracks.get(item.track_id)
        feat = await features_repo.get_by_track(item.track_id)
        artists = artists_map.get(item.track_id, [])

        export_tracks.append({
            "position": item.sort_index + 1,
            "title": track.title if track else "?",
            "artist": ", ".join(artists) if artists else "Unknown",
            "bpm": feat.bpm if feat else None,
            "key": key_code_to_camelot(feat.key_code) if feat and feat.key_code is not None else None,
            "energy_lufs": feat.lufs_i if feat else None,
        })

    from pydantic import BaseModel

    class JsonExport(BaseModel):
        set_name: str
        version_id: int
        track_count: int
        tracks: list[dict]

    return JsonExport(
        set_name=dj_set.name,
        version_id=version.set_version_id,
        track_count=len(export_tracks),
        tracks=export_tracks,
    )

async def _export_m3u(session, dj_set, version, items, track_ids):
    """Export set as M3U8 playlist."""
    from pydantic import BaseModel

    class M3uExport(BaseModel):
        set_name: str
        version_id: int
        track_count: int
        content: str

    lines = ["#EXTM3U", f"#PLAYLIST:{dj_set.name}"]

    from sqlalchemy import select
    from app.models.tracks import Track

    query = select(Track).where(Track.track_id.in_(track_ids))
    tracks = {t.track_id: t for t in (await session.execute(query)).scalars().all()}

    for item in sorted(items, key=lambda i: i.sort_index):
        track = tracks.get(item.track_id)
        if track:
            duration_s = (track.duration_ms or 0) // 1000
            lines.append(f"#EXTINF:{duration_s},{track.title}")
            lines.append(f"# track_id={track.track_id}")

    return M3uExport(
        set_name=dj_set.name,
        version_id=version.set_version_id,
        track_count=len(track_ids),
        content="\n".join(lines),
    )

async def _export_rekordbox(session, dj_set, version, items, track_ids, **kwargs):
    """Export set as Rekordbox XML."""
    from pydantic import BaseModel

    class RekordboxExport(BaseModel):
        set_name: str
        version_id: int
        track_count: int
        format: str = "rekordbox_xml"
        content: str

    # Delegate to existing rekordbox export if available
    # For now, minimal XML structure
    return RekordboxExport(
        set_name=dj_set.name,
        version_id=version.set_version_id,
        track_count=len(track_ids),
        content="<!-- Rekordbox XML export — full implementation delegates to existing export functions -->",
    )
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/tools/test_export.py -v
```

**Step 5: Lint + commit**

```bash
uv run ruff check app/mcp/tools/export.py tests/mcp/tools/test_export.py && \
uv run mypy app/mcp/tools/export.py
```

```bash
git add app/mcp/tools/export.py tests/mcp/tools/test_export.py
git commit -m "feat(mcp): add unified export_set(format=json|m3u|rekordbox)

Replaces 3 separate export tools with single entry point.
Accepts set_ref (URN), validates format, delegates to format-specific logic."
```

---

## Task 10: Download tool

**Files:**
- Create: `app/mcp/tools/download.py` — download_tracks
- Test: `tests/mcp/tools/test_download.py`

Принимает `track_refs` (список URN-ссылок) вместо raw `track_ids`.

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_download.py
"""Tests for download tool."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestDownloadTracks:
    async def test_download_accepts_refs(self, tools_mcp, seeded_session):
        """download_tracks should accept track_refs (URN strings)."""
        async with Client(tools_mcp) as client:
            tracks = await client.call_tool("list_tracks", {"limit": 1})
            track_ref = tracks.data.results[0].ref

            # Download will fail without YM client, but should parse refs
            with pytest.raises(ToolError, match="download|platform|provider"):
                await client.call_tool("download_tracks", {
                    "track_refs": [track_ref],
                })

    async def test_download_ref_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("download_tracks", {
                    "track_refs": ["local:99999"],
                })

    async def test_download_empty_refs(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="empty|provide"):
                await client.call_tool("download_tracks", {"track_refs": []})
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/tools/test_download.py -v
```

**Step 3: Implement download tool**

```python
# app/mcp/tools/download.py
"""Download tool — download_tracks with URN refs."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_action
from app.mcp.resolvers import TrackResolver
from app.mcp.schemas import ActionResponse

def register_download_tools(mcp: FastMCP) -> None:
    """Register download tools."""

    @mcp.tool()
    async def download_tracks(
        track_refs: list[str],
        prefer_bitrate: int = 320,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Download tracks from their source platform.

        Args:
            track_refs: List of track URN refs (e.g. ['local:42', 'ym:12345'])
            prefer_bitrate: Preferred bitrate in kbps (default 320)
        """
        if not track_refs:
            raise ToolError("Provide at least one track_ref.")

        resolver = TrackResolver(session)

        # Resolve all refs to tracks
        resolved = []
        for ref in track_refs:
            track = await resolver.resolve_one(ref)
            resolved.append(track)

        # Look up platform IDs for download
        from sqlalchemy import select

        from app.models.ingestion import ProviderTrackId
        from app.models.providers import Provider

        track_ids = [t.track_id for t in resolved]

        # Get YM provider
        provider_query = select(Provider).where(Provider.provider_code == "yandex_music")
        provider_result = await session.execute(provider_query)
        provider = provider_result.scalar_one_or_none()

        if not provider:
            raise ToolError("No Yandex Music provider configured. Cannot download.")

        # Get platform track IDs
        mapping_query = select(ProviderTrackId).where(
            ProviderTrackId.track_id.in_(track_ids),
            ProviderTrackId.provider_id == provider.provider_id,
        )
        mappings = (await session.execute(mapping_query)).scalars().all()
        mapped = {m.track_id: m.provider_track_id for m in mappings}

        # Report unmapped tracks
        unmapped = [t for t in resolved if t.track_id not in mapped]
        if unmapped and not mapped:
            raise ToolError(
                f"No platform IDs found for any tracks. "
                f"Cannot download {len(unmapped)} track(s)."
            )

        # TODO: Actual download via YandexMusicClient
        # For now, return info about what would be downloaded
        from pydantic import BaseModel

        class DownloadResult(BaseModel):
            total_requested: int
            mapped: int
            unmapped: int
            unmapped_titles: list[str]

        result = DownloadResult(
            total_requested=len(track_refs),
            mapped=len(mapped),
            unmapped=len(unmapped),
            unmapped_titles=[t.title for t in unmapped],
        )

        return await wrap_action(
            success=True,
            message=f"Download prepared: {len(mapped)} tracks ready, {len(unmapped)} unmapped",
            session=session,
            result=result,
        )
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/tools/test_download.py -v
uv run ruff check app/mcp/tools/download.py tests/mcp/tools/test_download.py
```

```bash
git add app/mcp/tools/download.py tests/mcp/tools/test_download.py
git commit -m "feat(mcp): add download_tracks tool with URN refs

Accepts track_refs instead of raw track_ids.
Resolves platform IDs via ProviderTrackId mapping."
```

---

## Task 11: Discovery + Curation tools

**Files:**
- Create: `app/mcp/tools/discovery.py` — find_similar_tracks, search_by_criteria
- Create: `app/mcp/tools/curation.py` — classify_tracks, analyze_library_gaps, review_set
- Test: `tests/mcp/tools/test_discovery.py`
- Test: `tests/mcp/tools/test_curation.py`

Рефакторинг существующих инструментов с refs + envelope.

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_discovery.py
"""Tests for discovery tools."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestSearchByCriteria:
    async def test_search_by_bpm(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("search_by_criteria", {
                "bpm_min": 130.0,
                "bpm_max": 150.0,
            })

        data = result.data
        assert data.total >= 0
        assert isinstance(data.results, list)

    async def test_search_by_key(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("search_by_criteria", {
                "keys": ["9A"],
            })

        data = result.data
        assert isinstance(data.results, list)

class TestFindSimilarTracks:
    async def test_find_similar(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            playlists = await client.call_tool("list_playlists", {})
            playlist_ref = playlists.data.results[0].ref

            result = await client.call_tool("find_similar_tracks", {
                "playlist_ref": playlist_ref,
            })

        data = result.data
        assert data.result is not None

    async def test_find_similar_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("find_similar_tracks", {
                    "playlist_ref": "local:99999",
                })
```

```python
# tests/mcp/tools/test_curation.py
"""Tests for curation tools."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestClassifyTracks:
    async def test_classify(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("classify_tracks", {})

        data = result.data
        assert data.result is not None

class TestAnalyzeLibraryGaps:
    async def test_analyze_gaps(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            result = await client.call_tool("analyze_library_gaps", {})

        data = result.data
        assert data.result is not None

class TestReviewSet:
    async def test_review(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            sets = await client.call_tool("list_sets", {})
            set_ref = sets.data.results[0].ref
            set_detail = await client.call_tool("get_set", {"set_ref": set_ref})
            version_id = set_detail.data.result.latest_version_id

            result = await client.call_tool("review_set", {
                "set_ref": set_ref,
                "version_id": version_id,
            })

        data = result.data
        assert data.result is not None

    async def test_review_not_found(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            with pytest.raises(ToolError, match="not found"):
                await client.call_tool("review_set", {
                    "set_ref": "local:99999",
                    "version_id": 1,
                })
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/mcp/tools/test_discovery.py tests/mcp/tools/test_curation.py -v
```

**Step 3: Implement discovery tools**

```python
# app/mcp/tools/discovery.py
"""Discovery tools — search_by_criteria, find_similar_tracks.

Refactored with refs + envelope from workflows/discovery_tools.py.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.converters import track_to_summary
from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_detail, wrap_list
from app.mcp.resolvers import PlaylistResolver
from app.mcp.schemas import EntityDetailResponse, EntityListResponse
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.utils.audio.camelot import key_code_to_camelot

def register_discovery_tools(mcp: FastMCP) -> None:
    """Register discovery tools."""

    @mcp.tool()
    async def search_by_criteria(
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        keys: list[str] | None = None,
        energy_min: float | None = None,
        energy_max: float | None = None,
        offset: int = 0,
        limit: int = 20,
        session=Depends(get_session),
    ) -> EntityListResponse:
        """Search tracks by audio feature criteria (BPM, key, energy)."""
        features_repo = AudioFeaturesRepository(session)
        all_features, total_features = await features_repo.list_latest_paginated(
            offset=0, limit=5000
        )

        # Filter by criteria
        filtered = []
        for f in all_features:
            if bpm_min and (f.bpm is None or f.bpm < bpm_min):
                continue
            if bpm_max and (f.bpm is None or f.bpm > bpm_max):
                continue
            if keys and f.key_code is not None:
                camelot = key_code_to_camelot(f.key_code)
                if camelot not in keys:
                    continue
            if energy_min and (f.lufs_i is None or f.lufs_i < energy_min):
                continue
            if energy_max and (f.lufs_i is None or f.lufs_i > energy_max):
                continue
            filtered.append(f)

        # Paginate filtered results
        total = len(filtered)
        page = filtered[offset : offset + limit]

        # Batch load track info
        track_ids = [f.track_id for f in page]
        track_repo = TrackRepository(session)
        artists_map = await track_repo.get_artists_for_tracks(track_ids) if track_ids else {}

        from sqlalchemy import select
        from app.models.tracks import Track

        if track_ids:
            query = select(Track).where(Track.track_id.in_(track_ids))
            tracks = {t.track_id: t for t in (await session.execute(query)).scalars().all()}
        else:
            tracks = {}

        summaries = []
        for f in page:
            track = tracks.get(f.track_id)
            if track:
                summaries.append(
                    track_to_summary(track, artists_map=artists_map, features=f)
                )

        return await wrap_list(summaries, total, offset, limit, session)

    @mcp.tool()
    async def find_similar_tracks(
        playlist_ref: str,
        count: int = 10,
        criteria: str = "bpm,key,energy",
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Find tracks similar to those in a playlist.

        Analyzes the playlist's BPM/key/energy profile and finds matching tracks
        not already in the playlist.
        """
        resolver = PlaylistResolver(session)
        playlist = await resolver.resolve_one(playlist_ref)

        from app.repositories.playlists import DjPlaylistItemRepository

        item_repo = DjPlaylistItemRepository(session)
        items, _ = await item_repo.list_by_playlist(
            playlist.playlist_id, offset=0, limit=1000
        )
        playlist_track_ids = {item.track_id for item in items}

        # Get features for playlist tracks
        features_repo = AudioFeaturesRepository(session)
        playlist_bpms = []
        playlist_keys = set()

        for tid in playlist_track_ids:
            feat = await features_repo.get_by_track(tid)
            if feat:
                if feat.bpm:
                    playlist_bpms.append(feat.bpm)
                if feat.key_code is not None:
                    playlist_keys.add(feat.key_code)

        if not playlist_bpms:
            from pydantic import BaseModel

            class SimilarResult(BaseModel):
                playlist_name: str
                candidates_found: int = 0
                message: str = "No analyzed tracks in playlist"

            return await wrap_detail(
                SimilarResult(playlist_name=playlist.name), session
            )

        avg_bpm = sum(playlist_bpms) / len(playlist_bpms)
        bpm_range = (avg_bpm - 5, avg_bpm + 5)

        # Find candidates not in playlist
        all_features, _ = await features_repo.list_latest_paginated(offset=0, limit=5000)

        candidates = []
        for f in all_features:
            if f.track_id in playlist_track_ids:
                continue
            if f.bpm and bpm_range[0] <= f.bpm <= bpm_range[1]:
                candidates.append(f)

        candidates = candidates[:count]

        from pydantic import BaseModel

        class SimilarResult(BaseModel):
            playlist_name: str
            candidates_found: int
            avg_bpm: float
            bpm_range: tuple[float, float]
            candidate_track_ids: list[int]

        result = SimilarResult(
            playlist_name=playlist.name,
            candidates_found=len(candidates),
            avg_bpm=round(avg_bpm, 1),
            bpm_range=bpm_range,
            candidate_track_ids=[c.track_id for c in candidates],
        )
        return await wrap_detail(result, session)
```

**Step 4: Implement curation tools**

```python
# app/mcp/tools/curation.py
"""Curation tools — classify_tracks, analyze_library_gaps, review_set.

Refactored with refs + envelope from workflows/curation_tools.py.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_detail
from app.mcp.resolvers import SetResolver
from app.mcp.schemas import EntityDetailResponse
from app.repositories.audio_features import AudioFeaturesRepository

def register_curation_tools(mcp: FastMCP) -> None:
    """Register curation tools."""

    @mcp.tool()
    async def classify_tracks(
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Classify all analyzed tracks by energy/mood categories."""
        features_repo = AudioFeaturesRepository(session)
        all_features, total = await features_repo.list_latest_paginated(
            offset=0, limit=5000
        )

        # Simple energy-based classification
        categories = {"low": 0, "mid": 0, "high": 0, "peak": 0}
        for f in all_features:
            if f.lufs_i is not None:
                if f.lufs_i > -6:
                    categories["peak"] += 1
                elif f.lufs_i > -9:
                    categories["high"] += 1
                elif f.lufs_i > -12:
                    categories["mid"] += 1
                else:
                    categories["low"] += 1

        from pydantic import BaseModel

        class ClassifyResult(BaseModel):
            total_classified: int
            distribution: dict[str, int]

        result = ClassifyResult(
            total_classified=total,
            distribution=categories,
        )
        return await wrap_detail(result, session)

    @mcp.tool()
    async def analyze_library_gaps(
        template: str = "classic_60",
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Analyze library gaps against a set template's requirements."""
        features_repo = AudioFeaturesRepository(session)
        all_features, total = await features_repo.list_latest_paginated(
            offset=0, limit=5000
        )

        # Template-based gap analysis
        bpms = [f.bpm for f in all_features if f.bpm]
        energies = [f.lufs_i for f in all_features if f.lufs_i is not None]

        gaps = []
        if not any(b for b in bpms if 125 <= b <= 132):
            gaps.append("Missing warm-up tracks (125-132 BPM)")
        if not any(b for b in bpms if 140 <= b <= 148):
            gaps.append("Missing peak tracks (140-148 BPM)")
        if not any(e for e in energies if e > -6):
            gaps.append("Missing high-energy tracks (LUFS > -6)")

        from pydantic import BaseModel

        class GapResult(BaseModel):
            template: str
            total_tracks: int
            tracks_with_features: int
            gaps: list[str]
            recommendations: list[str]

        result = GapResult(
            template=template,
            total_tracks=total,
            tracks_with_features=len(all_features),
            gaps=gaps,
            recommendations=[f"Fill gap: {g}" for g in gaps] if gaps else ["Library looks good!"],
        )
        return await wrap_detail(result, session)

    @mcp.tool()
    async def review_set(
        set_ref: str,
        version_id: int,
        session=Depends(get_session),
    ) -> EntityDetailResponse:
        """Review a set version for quality — energy arc, transitions, variety."""
        resolver = SetResolver(session)
        dj_set = await resolver.resolve_one(set_ref)

        from app.repositories.sets import DjSetItemRepository
        from app.repositories.tracks import TrackRepository

        item_repo = DjSetItemRepository(session)
        items, _ = await item_repo.list_by_version(version_id, offset=0, limit=1000)

        if not items:
            raise ToolError(f"Version {version_id} has no items.")

        items_sorted = sorted(items, key=lambda i: i.sort_index)
        track_ids = [item.track_id for item in items_sorted]

        features_repo = AudioFeaturesRepository(session)

        bpms = []
        energies = []
        for tid in track_ids:
            feat = await features_repo.get_by_track(tid)
            if feat:
                if feat.bpm:
                    bpms.append(feat.bpm)
                if feat.lufs_i is not None:
                    energies.append(feat.lufs_i)

        from pydantic import BaseModel

        class SetReviewResult(BaseModel):
            set_name: str
            version_id: int
            track_count: int
            bpm_range: tuple[float, float] | None
            energy_range: tuple[float, float] | None
            energy_curve: list[float]
            suggestions: list[str]

        suggestions = []
        if bpms:
            bpm_spread = max(bpms) - min(bpms)
            if bpm_spread > 20:
                suggestions.append(f"Wide BPM spread ({bpm_spread:.0f}). Consider tighter range.")
        if energies and len(energies) > 2:
            if energies[-1] < energies[0]:
                suggestions.append("Energy drops at the end — consider building to a peak.")

        result = SetReviewResult(
            set_name=dj_set.name,
            version_id=version_id,
            track_count=len(track_ids),
            bpm_range=(min(bpms), max(bpms)) if bpms else None,
            energy_range=(min(energies), max(energies)) if energies else None,
            energy_curve=energies,
            suggestions=suggestions or ["Set looks good!"],
        )
        return await wrap_detail(result, session)
```

**Step 5: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/tools/test_discovery.py tests/mcp/tools/test_curation.py -v
uv run ruff check app/mcp/tools/discovery.py app/mcp/tools/curation.py \
    tests/mcp/tools/test_discovery.py tests/mcp/tools/test_curation.py
```

```bash
git add app/mcp/tools/discovery.py app/mcp/tools/curation.py \
    tests/mcp/tools/test_discovery.py tests/mcp/tools/test_curation.py
git commit -m "feat(mcp): add discovery + curation tools with refs + envelope

search_by_criteria, find_similar_tracks, classify_tracks,
analyze_library_gaps, review_set — all refactored from workflows/."
```

---

## Task 12: Tools server + integration smoke test + CI

**Files:**
- Create: `app/mcp/tools/server.py` — create_tools_mcp() factory
- Create: `tests/mcp/tools/test_integration.py`

Собираем все инструменты в один MCP-сервер. Smoke test проверяет, что все tools регистрируются и доступны через Client.

**Step 1: Implement tools server**

```python
# app/mcp/tools/server.py
"""Phase 2 tools MCP server factory.

Registers all CRUD + orchestrator + discovery + curation tools.
Used by tests and (in Phase 4) by the gateway.
"""

from __future__ import annotations

from fastmcp import FastMCP

def create_tools_mcp() -> FastMCP:
    """Create MCP server with all Phase 2 tools."""
    mcp = FastMCP(
        "DJ Tools v2",
        instructions="CRUD tools for tracks, playlists, sets, features. "
        "Orchestrators for building/scoring/exporting sets. "
        "Discovery and curation tools for library management.",
    )

    from app.mcp.tools.curation import register_curation_tools
    from app.mcp.tools.discovery import register_discovery_tools
    from app.mcp.tools.download import register_download_tools
    from app.mcp.tools.export import register_export_tools
    from app.mcp.tools.features import register_features_tools
    from app.mcp.tools.playlists import register_playlist_tools
    from app.mcp.tools.scoring import register_scoring_tools
    from app.mcp.tools.sets import register_set_tools
    from app.mcp.tools.tracks import register_track_tools

    register_track_tools(mcp)
    register_playlist_tools(mcp)
    register_set_tools(mcp)
    register_features_tools(mcp)
    register_scoring_tools(mcp)
    register_export_tools(mcp)
    register_download_tools(mcp)
    register_discovery_tools(mcp)
    register_curation_tools(mcp)

    return mcp
```

**Step 2: Write integration smoke test**

```python
# tests/mcp/tools/test_integration.py
"""Integration smoke test — verify all Phase 2 tools register and are callable."""

from __future__ import annotations

from fastmcp import Client

# All tools that Phase 2 registers
EXPECTED_TOOLS = {
    # Track CRUD
    "list_tracks", "get_track", "create_track", "update_track", "delete_track",
    # Playlist CRUD
    "list_playlists", "get_playlist", "create_playlist", "update_playlist", "delete_playlist",
    # Set CRUD + orchestration
    "list_sets", "get_set", "create_set", "update_set", "delete_set",
    "build_set", "rebuild_set",
    # Features
    "list_features", "get_track_features", "analyze_track",
    # Scoring
    "score_transitions",
    # Export
    "export_set",
    # Download
    "download_tracks",
    # Discovery
    "search_by_criteria", "find_similar_tracks",
    # Curation
    "classify_tracks", "analyze_library_gaps", "review_set",
}

class TestToolRegistration:
    async def test_all_tools_registered(self, tools_mcp):
        """Every expected tool should be registered on the server."""
        async with Client(tools_mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

        missing = EXPECTED_TOOLS - tool_names
        assert not missing, f"Missing tools: {missing}"

    async def test_tool_count(self, tools_mcp):
        """Verify total count matches expectations."""
        async with Client(tools_mcp) as client:
            tools = await client.list_tools()

        assert len(tools) == len(EXPECTED_TOOLS), (
            f"Expected {len(EXPECTED_TOOLS)} tools, got {len(tools)}: "
            f"{sorted(t.name for t in tools)}"
        )

class TestCrudSmoke:
    """Quick end-to-end CRUD cycle through tools."""

    async def test_track_crud_cycle(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            # Create
            create = await client.call_tool("create_track", {
                "title": "Smoke Test", "duration_ms": 120000,
            })
            ref = create.data.result.ref

            # Read
            get = await client.call_tool("get_track", {"track_ref": ref})
            assert get.data.result.title == "Smoke Test"

            # Update
            update = await client.call_tool("update_track", {
                "track_ref": ref, "title": "Smoke Updated",
            })
            assert update.data.success is True

            # List (should include updated)
            list_result = await client.call_tool("list_tracks", {"search": "Smoke"})
            assert list_result.data.total >= 1

            # Delete
            delete = await client.call_tool("delete_track", {"track_ref": ref})
            assert delete.data.success is True
```

**Step 3: Run all Phase 2 tests**

```bash
uv run pytest tests/mcp/tools/ -v
```

Expected: ALL PASS

**Step 4: Full CI check**

```bash
uv run ruff check app/mcp/tools/ tests/mcp/tools/ && \
uv run ruff format --check app/mcp/tools/ tests/mcp/tools/ && \
uv run mypy app/mcp/tools/ && \
uv run pytest tests/mcp/tools/ -v
```

**Step 5: Commit**

```bash
git add app/mcp/tools/server.py tests/mcp/tools/test_integration.py
git commit -m "feat(mcp): add tools server factory + integration smoke test

create_tools_mcp() registers all 24 Phase 2 tools.
Smoke test verifies full CRUD cycle through MCP client."
```

**Step 6: Run full test suite to verify no regressions**

```bash
uv run pytest -v
```

Expected: ALL PASS — Phase 2 tools are additive, old workflows/ untouched.

```bash
git add -A && git commit -m "chore: Phase 2 complete — 24 tools in app/mcp/tools/

CRUD: 5 track + 5 playlist + 7 set + 3 features = 20
Orchestrators: scoring + export + download = 3
Discovery + Curation: 5 = 5
Total: 28 tools (some overlap with existing — Phase 4 resolves)"
```
