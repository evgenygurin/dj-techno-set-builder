# DJ Workflow MCP Server — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a high-level MCP workflow server with 12 "smart" tools that use ctx.sample(), ctx.elicit(), Background Tasks, and DI to orchestrate complex DJ scenarios via Claude Desktop.

**Architecture:** Gateway MCP server mounts Yandex Music (existing) + DJ Workflows (new) with namespaces. Workflow tools call existing services directly through FastMCP Depends(). MCP Prompts provide workflow recipes, Resources expose system state.

**Tech Stack:** FastMCP 3.0rc1, FastAPI, SQLAlchemy async, Pydantic v2, existing service layer

---

### Task 1: Foundation — Types and Dependencies

**Files:**
- Create: `app/mcp/types.py`
- Create: `app/mcp/dependencies.py`
- Test: `tests/mcp/test_dependencies.py`

**Step 1: Write types.py — Pydantic models for structured output**

```python
"""Pydantic models for MCP tool structured output."""

from __future__ import annotations

from pydantic import BaseModel

class PlaylistStatus(BaseModel):
    """Status of a DJ playlist including analysis progress."""

    playlist_id: int
    name: str
    total_tracks: int
    analyzed_tracks: int
    bpm_range: tuple[float, float] | None = None
    keys: list[str] = []
    avg_energy: float | None = None
    duration_minutes: float = 0.0

class TrackDetails(BaseModel):
    """Full track details with audio features."""

    track_id: int
    title: str
    artists: str
    duration_ms: int | None = None
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None
    has_features: bool = False

class ImportResult(BaseModel):
    """Result of a playlist/track import operation."""

    playlist_id: int
    imported_count: int
    skipped_count: int
    enriched_count: int

class AnalysisResult(BaseModel):
    """Result of audio analysis on a playlist."""

    playlist_id: int
    analyzed_count: int
    failed_count: int
    bpm_range: tuple[float, float] | None = None
    keys: list[str] = []

class SimilarTracksResult(BaseModel):
    """Result of finding similar tracks."""

    playlist_id: int
    candidates_found: int
    candidates_selected: int
    added_count: int

class SearchStrategy(BaseModel):
    """LLM-generated search strategy for finding similar tracks."""

    queries: list[str]
    target_bpm_range: tuple[float, float]
    target_keys: list[str]
    target_energy_range: tuple[float, float]
    reasoning: str

class SetBuildResult(BaseModel):
    """Result of building/optimizing a DJ set."""

    set_id: int
    version_id: int
    track_count: int
    total_score: float
    avg_transition_score: float
    energy_curve: list[float] = []

class TransitionScoreResult(BaseModel):
    """Transition score between two tracks."""

    from_track_id: int
    to_track_id: int
    from_title: str
    to_title: str
    total: float
    bpm: float
    harmonic: float
    energy: float
    spectral: float
    groove: float

class ExportResult(BaseModel):
    """Result of exporting a set."""

    set_id: int
    format: str
    track_count: int
    content: str
```

**Step 2: Write dependencies.py — DI providers for MCP tools**

```python
"""Dependency injection providers for MCP tools."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fastmcp.dependencies import Depends

from app.config import settings
from app.database import session_factory
from app.clients.yandex_music import YandexMusicClient
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.dj_playlists import DjPlaylistRepository
from app.repositories.dj_playlist_items import DjPlaylistItemRepository
from app.repositories.dj_sets import DjSetRepository
from app.repositories.dj_set_items import DjSetItemRepository
from app.repositories.dj_set_versions import DjSetVersionRepository
from app.repositories.feature_runs import FeatureRunRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.repositories.transitions import TransitionRepository
from app.services.audio_features import AudioFeaturesService
from app.services.dj_sets import DjSetService
from app.services.playlists import DjPlaylistService
from app.services.set_generation import SetGenerationService
from app.services.track_analysis import TrackAnalysisService
from app.services.tracks import TrackService
from app.services.transitions import TransitionService

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session

def get_track_service(session: AsyncSession = Depends(get_session)) -> TrackService:
    return TrackService(TrackRepository(session))

def get_playlist_service(
    session: AsyncSession = Depends(get_session),
) -> DjPlaylistService:
    return DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )

def get_features_service(
    session: AsyncSession = Depends(get_session),
) -> AudioFeaturesService:
    return AudioFeaturesService(
        AudioFeaturesRepository(session),
        TrackRepository(session),
    )

def get_analysis_service(
    session: AsyncSession = Depends(get_session),
) -> TrackAnalysisService:
    return TrackAnalysisService(
        TrackRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
    )

def get_set_service(
    session: AsyncSession = Depends(get_session),
) -> DjSetService:
    return DjSetService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
    )

def get_set_generation_service(
    session: AsyncSession = Depends(get_session),
) -> SetGenerationService:
    return SetGenerationService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
        AudioFeaturesRepository(session),
    )

def get_transition_service(
    session: AsyncSession = Depends(get_session),
) -> TransitionService:
    return TransitionService(TransitionRepository(session))

def get_ym_client() -> YandexMusicClient:
    return YandexMusicClient(
        token=settings.yandex_music_token,
        user_id=settings.yandex_music_user_id,
    )
```

**Step 3: Write failing test for dependencies**

```python
"""Tests for MCP dependency injection providers."""

from __future__ import annotations

from app.mcp.dependencies import (
    get_analysis_service,
    get_features_service,
    get_playlist_service,
    get_session,
    get_set_generation_service,
    get_set_service,
    get_track_service,
    get_transition_service,
    get_ym_client,
)
from app.mcp.types import (
    AnalysisResult,
    ExportResult,
    ImportResult,
    PlaylistStatus,
    SearchStrategy,
    SetBuildResult,
    SimilarTracksResult,
    TrackDetails,
    TransitionScoreResult,
)

def test_types_are_importable():
    """All Pydantic types should be importable."""
    assert PlaylistStatus is not None
    assert TrackDetails is not None
    assert ImportResult is not None
    assert AnalysisResult is not None
    assert SimilarTracksResult is not None
    assert SearchStrategy is not None
    assert SetBuildResult is not None
    assert TransitionScoreResult is not None
    assert ExportResult is not None

def test_dependency_functions_are_importable():
    """All DI functions should be importable."""
    assert get_session is not None
    assert get_track_service is not None
    assert get_playlist_service is not None
    assert get_features_service is not None
    assert get_analysis_service is not None
    assert get_set_service is not None
    assert get_set_generation_service is not None
    assert get_transition_service is not None
    assert get_ym_client is not None

def test_playlist_status_model():
    """PlaylistStatus should serialize correctly."""
    status = PlaylistStatus(
        playlist_id=1,
        name="Test",
        total_tracks=10,
        analyzed_tracks=5,
        bpm_range=(126.0, 134.0),
        keys=["Am", "Cm"],
        avg_energy=-8.5,
        duration_minutes=45.0,
    )
    assert status.playlist_id == 1
    assert status.bpm_range == (126.0, 134.0)
    data = status.model_dump()
    assert data["keys"] == ["Am", "Cm"]
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_dependencies.py -v`
Expected: PASS

**Step 5: Run linting**

Run: `uv run ruff check app/mcp/types.py app/mcp/dependencies.py`
Run: `uv run mypy app/mcp/types.py app/mcp/dependencies.py`
Fix any issues.

**Step 6: Commit**

```bash
git add app/mcp/types.py app/mcp/dependencies.py tests/mcp/test_dependencies.py
git commit -m "feat: add MCP types and dependency injection providers"
```

---

### Task 2: Workflow Server Scaffold + Gateway

**Files:**
- Create: `app/mcp/workflows/__init__.py`
- Create: `app/mcp/workflows/server.py`
- Create: `app/mcp/gateway.py`
- Modify: `app/mcp/__init__.py`
- Modify: `app/main.py`
- Test: `tests/mcp/test_gateway.py`

**Step 1: Create workflow server scaffold**

`app/mcp/workflows/__init__.py`:
```python
"""DJ workflow MCP tools."""

from app.mcp.workflows.server import create_workflow_mcp

__all__ = ["create_workflow_mcp"]
```

`app/mcp/workflows/server.py`:
```python
"""DJ Workflow MCP server — high-level tools for DJ set building."""

from __future__ import annotations

from fastmcp import FastMCP

def create_workflow_mcp() -> FastMCP:
    """Create the DJ Workflows MCP server with all tools registered."""
    mcp = FastMCP("DJ Workflows")
    # Tools will be registered in subsequent tasks
    return mcp
```

**Step 2: Create gateway**

`app/mcp/gateway.py`:
```python
"""MCP Gateway — combines all MCP sub-servers into one."""

from __future__ import annotations

from fastmcp import FastMCP

from app.mcp.workflows import create_workflow_mcp
from app.mcp.yandex_music import create_yandex_music_mcp

def create_dj_mcp() -> FastMCP:
    """Create the gateway MCP server.

    Mounts Yandex Music (namespace "ym") and DJ Workflows (namespace "dj").
    """
    gateway = FastMCP("DJ Set Builder")

    ym = create_yandex_music_mcp()
    gateway.mount(ym, namespace="ym")

    wf = create_workflow_mcp()
    gateway.mount(wf, namespace="dj")

    return gateway
```

**Step 3: Update app/mcp/__init__.py**

```python
"""MCP server integrations."""

from app.mcp.gateway import create_dj_mcp

__all__ = ["create_dj_mcp"]
```

**Step 4: Update app/main.py to use gateway**

Replace `from app.mcp.yandex_music import create_yandex_music_mcp` with
`from app.mcp import create_dj_mcp`, and `create_yandex_music_mcp()` with
`create_dj_mcp()`.

```python
# app/main.py changes:
# Old: from app.mcp.yandex_music import create_yandex_music_mcp
# New: from app.mcp import create_dj_mcp
# Old: mcp = create_yandex_music_mcp()
# New: mcp = create_dj_mcp()
```

**Step 5: Write test**

`tests/mcp/test_gateway.py`:
```python
"""Tests for MCP Gateway composition."""

from __future__ import annotations

from fastmcp import FastMCP

async def test_gateway_creates_fastmcp():
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    assert isinstance(mcp, FastMCP)
    assert mcp.name == "DJ Set Builder"

async def test_gateway_has_yandex_music_tools():
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    # Yandex Music tools should be namespaced with "ym_"
    ym_tools = {n for n in tool_names if n.startswith("ym_")}
    assert len(ym_tools) > 0, f"No ym_ tools found. Available: {tool_names}"

async def test_existing_yandex_music_tests_still_pass():
    """Existing YM MCP tests should still work via direct import."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    tools = await mcp.list_tools()
    assert len(tools) > 0
```

**Step 6: Run all tests**

Run: `uv run pytest tests/mcp/ -v`
Expected: All PASS (existing + new).

**Step 7: Lint**

Run: `uv run ruff check app/mcp/gateway.py app/mcp/workflows/`
Run: `uv run mypy app/mcp/gateway.py app/mcp/workflows/`

**Step 8: Commit**

```bash
git add app/mcp/gateway.py app/mcp/workflows/ app/mcp/__init__.py app/main.py tests/mcp/test_gateway.py
git commit -m "feat: add MCP gateway with workflow server scaffold"
```

---

### Task 3: Read-Only Analysis Tools

**Files:**
- Create: `app/mcp/workflows/analysis_tools.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_workflow_analysis.py`

**Step 1: Write analysis_tools.py**

```python
"""Analysis workflow tools — read-only status and detail queries."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.context import Context

from app.mcp.dependencies import (
    Depends,
    get_features_service,
    get_playlist_service,
    get_track_service,
)
from app.mcp.types import PlaylistStatus, TrackDetails
from app.services.audio_features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.services.tracks import TrackService

def register_analysis_tools(mcp: FastMCP) -> None:
    """Register read-only analysis tools on the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"analysis", "status"},
    )
    async def get_playlist_status(
        playlist_id: int,
        ctx: Context,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> PlaylistStatus:
        """Get full status of a playlist: tracks, analysis progress, BPM/key/energy stats.

        Call this first to understand what's in a playlist before
        running analysis or building sets.
        """
        playlist = await playlist_svc.get(playlist_id)
        items = await playlist_svc.list_items(playlist_id, limit=200)

        track_ids = [item.track_id for item in items.items]
        analyzed_count = 0
        bpms: list[float] = []
        keys: list[str] = []
        energies: list[float] = []
        total_duration_ms = 0

        for track_id in track_ids:
            try:
                feat = await features_svc.get_latest(track_id)
                analyzed_count += 1
                if feat.bpm is not None:
                    bpms.append(feat.bpm)
                if feat.musical_key is not None:
                    keys.append(feat.musical_key)
                if feat.energy_lufs is not None:
                    energies.append(feat.energy_lufs)
            except Exception:
                pass

        return PlaylistStatus(
            playlist_id=playlist_id,
            name=playlist.name,
            total_tracks=items.total,
            analyzed_tracks=analyzed_count,
            bpm_range=(min(bpms), max(bpms)) if bpms else None,
            keys=sorted(set(keys)),
            avg_energy=sum(energies) / len(energies) if energies else None,
            duration_minutes=total_duration_ms / 60000,
        )

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"analysis", "details"},
    )
    async def get_track_details(
        track_id: int,
        ctx: Context,
        track_svc: TrackService = Depends(get_track_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> TrackDetails:
        """Get full details of a track including audio features.

        Returns metadata and extracted audio features (BPM, key, energy).
        """
        track = await track_svc.get(track_id)

        bpm = None
        key = None
        energy = None
        has_features = False
        try:
            feat = await features_svc.get_latest(track_id)
            bpm = feat.bpm
            key = feat.musical_key
            energy = feat.energy_lufs
            has_features = True
        except Exception:
            pass

        return TrackDetails(
            track_id=track.track_id,
            title=track.title,
            artists=track.artists_display or "",
            duration_ms=track.duration_ms,
            bpm=bpm,
            key=key,
            energy_lufs=energy,
            has_features=has_features,
        )
```

**Important notes for implementer:**
- Check exact field names on `TrackRead`, `AudioFeaturesRead`, `DjPlaylistRead` schemas
- `playlist_svc.list_items()` returns a schema with `.items` list and `.total` count
- `features_svc.get_latest()` may raise `NotFoundError` if no features exist — catch it
- Adapt field names to match actual schema (e.g., `feat.bpm`, `feat.musical_key`, etc.)

**Step 2: Register in server.py**

Add to `create_workflow_mcp()`:
```python
from app.mcp.workflows.analysis_tools import register_analysis_tools

def create_workflow_mcp() -> FastMCP:
    mcp = FastMCP("DJ Workflows")
    register_analysis_tools(mcp)
    return mcp
```

**Step 3: Write tests**

`tests/mcp/test_workflow_analysis.py` — test that tools are registered:
```python
"""Tests for analysis workflow tools."""

from __future__ import annotations

async def test_analysis_tools_registered():
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "get_playlist_status" in tool_names
    assert "get_track_details" in tool_names

async def test_analysis_tools_have_readonly_annotation():
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        if tool.name in {"get_playlist_status", "get_track_details"}:
            assert tool.annotations is not None
```

**Step 4: Run tests + lint**

Run: `uv run pytest tests/mcp/ -v`
Run: `uv run ruff check app/mcp/workflows/`
Run: `uv run mypy app/mcp/workflows/`

**Step 5: Commit**

```bash
git add app/mcp/workflows/analysis_tools.py app/mcp/workflows/server.py tests/mcp/test_workflow_analysis.py
git commit -m "feat: add read-only analysis tools (get_playlist_status, get_track_details)"
```

---

### Task 4: Import Tools

**Files:**
- Create: `app/mcp/workflows/import_tools.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_workflow_import.py`

**Implementation:** Two tools — `import_playlist` and `import_tracks`.
These wrap `YandexMusicClient.fetch_playlist_tracks()` → create Track rows in DB → enrich metadata.

Use `ctx.report_progress()` for multi-track operations.
Consider using `task=True` if Background Tasks dependency (`fastmcp[tasks]`) is available; otherwise start without it and add later.

**Key logic in import_playlist:**
1. Call `ym_client.fetch_playlist_tracks(user_id, kind)` to get raw track data
2. For each track: check if exists in DB by yandex_track_id, create if not
3. `ctx.report_progress(i, total)` for each track
4. Return `ImportResult` with counts

**Key DI:** `get_ym_client()`, `get_track_service()`, `get_session()` (for raw repo access if needed)

Follow the same pattern as Task 3: `register_import_tools(mcp)`, add to `server.py`, write registration tests.

**Commit:** `git commit -m "feat: add import tools (import_playlist, import_tracks)"`

---

### Task 5: Discovery Tools

**Files:**
- Create: `app/mcp/workflows/discovery_tools.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_workflow_discovery.py`

**Implementation:** Two tools — `find_similar_tracks` and `search_by_criteria`.

**find_similar_tracks — the "smart" tool:**
1. Get playlist tracks + features
2. Build playlist profile (BPM range, keys, energy stats)
3. `ctx.sample()` → ask LLM for search strategy (`SearchStrategy` model)
4. Search YM with each query from strategy
5. Score candidates by BPM/key/energy distance
6. `ctx.elicit()` → show top candidates for user selection (multi-select)
7. Add selected tracks to playlist
8. Return `SimilarTracksResult`

**Important notes for implementer:**
- `ctx.sample()` with `result_type=SearchStrategy` — LLM returns structured output
- `ctx.elicit()` for multi-select uses `response_type=[["option1", "option2", ...]]`
- `ctx.sample()` and `ctx.elicit()` may not work in test environment — mock or skip
- Scoring logic: simple BPM distance + Camelot distance + energy distance
- If `ctx.sample()` fails (client doesn't support sampling), fall back to simple genre-based search

**search_by_criteria — simple manual tool:**
- Takes explicit BPM range, keys, energy range, genre
- Searches YM directly
- Returns list of candidates without LLM/elicitation

**Commit:** `git commit -m "feat: add discovery tools (find_similar_tracks, search_by_criteria)"`

---

### Task 6: Set Builder Tools

**Files:**
- Create: `app/mcp/workflows/setbuilder_tools.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_workflow_setbuilder.py`

**Implementation:** Three tools — `build_set`, `score_transitions`, `adjust_set`.

**build_set:**
1. Get playlist tracks + features
2. Create DjSet + DjSetVersion
3. Call `SetGenerationService.generate()` with GA config
4. Save ordered items to DjSetVersion
5. Return `SetBuildResult`

**score_transitions:**
1. Get set version items in order
2. For each adjacent pair: call `TransitionScoringService.score_transition()`
3. Return list of `TransitionScoreResult`

**adjust_set:**
1. Get current set order + transition scores
2. `ctx.sample()` → ask LLM to analyze and suggest reordering
3. `ctx.elicit()` → confirm changes with user
4. Apply changes, re-score
5. Return updated `SetBuildResult`

**Commit:** `git commit -m "feat: add set builder tools (build_set, score_transitions, adjust_set)"`

---

### Task 7: Export Tools

**Files:**
- Create: `app/mcp/workflows/export_tools.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_workflow_export.py`

**Implementation:** Two tools — `export_set_m3u`, `export_set_json`.

**export_set_m3u:**
1. Get set version items in order
2. For each track: get title, artists, duration
3. Build M3U content string
4. Return `ExportResult(format="m3u", content=m3u_string)`

**export_set_json:**
1. Get set version items + features + transition scores
2. Build JSON with: tracks[], transitions[], energy_curve[]
3. Return `ExportResult(format="json", content=json_string)`

**Commit:** `git commit -m "feat: add export tools (export_set_m3u, export_set_json)"`

---

### Task 8: MCP Prompts

**Files:**
- Create: `app/mcp/prompts/__init__.py`
- Create: `app/mcp/prompts/workflows.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_prompts.py`

**Implementation:** Three prompts — `expand_playlist`, `build_set_from_scratch`, `improve_set`.

Each prompt returns a `list[Message]` with step-by-step instructions referencing
namespaced tool names (`dj_get_playlist_status`, `dj_analyze_playlist`, etc.).

Register on the workflow MCP server via `register_prompts(mcp)`.

**Test:** Verify prompts are listed via `mcp.list_prompts()` and have correct argument names.

**Commit:** `git commit -m "feat: add MCP workflow prompts (expand, build, improve)"`

---

### Task 9: MCP Resources

**Files:**
- Create: `app/mcp/resources/__init__.py`
- Create: `app/mcp/resources/status.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_resources.py`

**Implementation:** Three resources:
- `playlist://{playlist_id}/status` — playlist stats (DI: playlist_svc, features_svc)
- `catalog://stats` — overall catalog counts (DI: track_svc)
- `set://{set_id}/summary` — set summary (DI: set_svc)

Register on the workflow MCP server via `register_resources(mcp)`.

**Test:** Verify resources/templates are listed via `mcp.list_resources()` / `mcp.list_resource_templates()`.

**Commit:** `git commit -m "feat: add MCP resources (playlist status, catalog stats, set summary)"`

---

### Task 10: Visibility + Transforms

**Files:**
- Modify: `app/mcp/workflows/server.py`
- Modify: `app/mcp/gateway.py`
- Test: `tests/mcp/test_visibility.py`

**Implementation:**

1. In `server.py`: add `activate_heavy_mode` tool that calls `ctx.enable_components(tags={"heavy"})`, then `mcp.disable(tags={"heavy"})` to hide heavy tools by default.

2. In `gateway.py`: add `PromptsAsTools` and `ResourcesAsTools` transforms if available in FastMCP 3.0rc1. Check imports exist first — if not available, skip (these are nice-to-have).

**Test:** Verify that heavy-tagged tools are hidden by default, and that calling `activate_heavy_mode` conceptually would reveal them.

**Commit:** `git commit -m "feat: add visibility control and transforms to gateway""`

---

### Task 11: Full CI Check

**Files:** None (verification only)

**Step 1:** Run all tests

Run: `uv run pytest -v`
Expected: All tests PASS (300+ existing + 15+ new MCP tests).

**Step 2:** Run linting

Run: `uv run ruff check`
Run: `uv run ruff format --check`
Run: `uv run mypy app/`
Expected: All clean.

**Step 3:** Manual smoke test

Run: `uv run uvicorn app.main:app --port 8000`
Test MCP endpoint: POST to `http://localhost:8000/mcp/mcp` with initialize.
Verify both `ym_*` and `dj_*` tools appear in `tools/list`.

**Step 4: Commit any fixes**

```bash
git commit -m "style: fix linting issues in MCP workflow tools"
```

---

## Notes for Implementer

### FastMCP DI Compatibility

FastMCP's `Depends()` is from `fastmcp.dependencies`, NOT `fastapi.Depends`.
They have similar API but are separate systems. Check the exact import path
in your installed version.

### Field Names on Schemas

The exact field names on `TrackRead`, `AudioFeaturesRead`, `DjPlaylistRead`
etc. may differ from what's shown here. Read the actual schema files before
implementing:
- `app/schemas/tracks.py`
- `app/schemas/audio_features.py`
- `app/schemas/playlists.py`
- `app/schemas/dj_sets.py`

### ctx.sample() / ctx.elicit() in Tests

These features require a real MCP client connection. In unit tests, tools
that use sampling/elicitation should be tested for registration only.
Integration tests with a real client can test the full flow later.

### Background Tasks (task=True)

Requires `fastmcp[tasks]` extra which depends on `docket`. If not installed,
omit `task=True` from decorators and add as a follow-up.
Check: `uv run python -c "import docket"` — if ImportError, skip task=True.

### Repository Import Paths

Some repo class names may differ from what's assumed here. Check:
```bash
grep -r "class.*Repository" app/repositories/ --include="*.py"
```
And adjust import paths in `dependencies.py` accordingly.
