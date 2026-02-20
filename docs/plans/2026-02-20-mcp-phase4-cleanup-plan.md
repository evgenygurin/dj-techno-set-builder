# Phase 4: Legacy MCP Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove legacy MCP tools, stubs, and dead types; migrate survivors to Phase 1-3 infrastructure.

**Architecture:** Phase 1-3 introduced CRUD tools (`track_tools.py`, etc.), `types_v2.py` response models,
`entity_finder.py`, `refs.py`, `response.py` envelope wrappers. Legacy tools in `analysis_tools.py`,
`import_tools.py`, `discovery_tools.py`, `export_tools.py` are now redundant or can be migrated to use
the new infrastructure. `sync_tools.py` was already rewritten in Phase 3 (uses SyncEngine) and stays.

**Tech Stack:** Python 3.12, FastMCP 3.0, Pydantic v2, pytest-asyncio

---

## Decision Log (resolving review blockers)

| Blocker | Decision |
|---------|----------|
| `sync_tools.py` — delete or keep? | **KEEP** — already Phase 3 SyncEngine rewrite |
| `export_set_m3u/json` vs unified | **DELETE** old, keep `unified_export_tools.py` + `export_set_rekordbox` |
| `download_tracks` location | **EXTRACT** to `download_tools.py` (new file), delete `import_tools.py` |
| "No new modules" vs renames | Phase 4 IS allowed to create `download_tools.py` (one file) |
| Types migration strategy | Move used types to `types_v2.py`, delete `types.py` + `types_curation.py` |
| Error handling | Use `ToolError` from fastmcp, not `ValueError` |

---

### Task 1: Delete `analysis_tools.py` and its tests

**Rationale:** `get_playlist_status` and `get_track_details` are fully replaced by Phase 2 CRUD
(`list_playlists` + `get_track` + `get_features`).

**Files:**
- Delete: `app/mcp/workflows/analysis_tools.py`
- Delete: `tests/mcp/test_workflow_analysis.py`
- Modify: `app/mcp/workflows/server.py` (remove import + registration)

**Step 1: Remove registration from server.py**

In `app/mcp/workflows/server.py`:
- Remove `from app.mcp.workflows.analysis_tools import register_analysis_tools`
- Remove `register_analysis_tools(mcp)` from `create_workflow_mcp()`

**Step 2: Delete files**

```bash
rm app/mcp/workflows/analysis_tools.py
rm tests/mcp/test_workflow_analysis.py
```

**Step 3: Run tests to verify nothing else breaks**

```bash
uv run pytest tests/mcp/ -v --tb=short 2>&1 | tail -20
```

Expected: Tests pass (except `test_client_integration.py` which we'll fix in Task 10).

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(mcp): remove analysis_tools — replaced by Phase 2 CRUD"
```

---

### Task 2: Delete import stubs, extract `download_tracks` to own module

**Rationale:** `import_playlist` and `import_tracks` are stubs (return zeros, print instructions).
`download_tracks` is real functionality — extract to `download_tools.py`.

**Files:**
- Delete: `app/mcp/workflows/import_tools.py`
- Delete: `tests/mcp/test_workflow_import.py`
- Create: `app/mcp/workflows/download_tools.py`
- Modify: `app/mcp/workflows/server.py`

**Step 1: Write test for download_tools registration**

Create `tests/mcp/test_workflow_download.py`:

```python
"""Tests for download_tools registration."""
from __future__ import annotations

import pytest
from fastmcp import FastMCP

from app.mcp.workflows.download_tools import register_download_tools

@pytest.fixture
def mcp() -> FastMCP:
    server = FastMCP("test")
    register_download_tools(server)
    return server

async def test_download_tracks_registered(mcp: FastMCP):
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "download_tracks" in names

async def test_download_tracks_has_correct_tags(mcp: FastMCP):
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "download_tracks")
    assert "download" in (tool.tags or set())
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_workflow_download.py -v
```

Expected: FAIL — `download_tools` module does not exist.

**Step 3: Create `download_tools.py`**

Move `download_tracks` function from `import_tools.py` into new file
`app/mcp/workflows/download_tools.py`:

```python
"""Download tools for DJ workflow MCP server."""
from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.mcp.dependencies import get_session, get_ym_client
from app.services.download import DownloadResult, DownloadService
from app.services.yandex_music_client import YandexMusicClient

def register_download_tools(mcp: FastMCP) -> None:
    """Register download tools on the MCP server."""

    @mcp.tool(
        name="download_tracks",
        description="Download MP3 files for tracks from Yandex Music to iCloud library",
        tags={"download", "yandex"},
        annotations={"readonly": False},
    )
    async def download_tracks(
        track_ids: list[int],
        prefer_bitrate: int = 320,
        ctx: Context | None = None,
        session: AsyncSession = Depends(get_session),  # noqa: B008
        ym_client: YandexMusicClient = Depends(get_ym_client),  # noqa: B008
    ) -> DownloadResult:
        """Download tracks from Yandex Music to local library.

        Downloads MP3 files and stores them in iCloud library directory.
        Skips tracks that already have files. Returns download statistics.

        Args:
            track_ids: List of track IDs to download
            prefer_bitrate: Preferred bitrate in kbps (default: 320)
        """
        library_path = Path(settings.dj_library_path).expanduser()
        download_svc = DownloadService(
            session=session,
            ym_client=ym_client,
            library_path=library_path,
        )
        return await download_svc.download_tracks_batch(
            track_ids=track_ids,
            prefer_bitrate=prefer_bitrate,
        )
```

**Step 4: Update server.py**

Replace:
```python
from app.mcp.workflows.import_tools import register_import_tools
```
With:
```python
from app.mcp.workflows.download_tools import register_download_tools
```

Replace `register_import_tools(mcp)` with `register_download_tools(mcp)`.

**Step 5: Delete old files**

```bash
rm app/mcp/workflows/import_tools.py
rm tests/mcp/test_workflow_import.py
```

**Step 6: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_download.py -v
```

Expected: PASS

**Step 7: Commit**

```bash
git add -A && git commit -m "refactor(mcp): extract download_tools, remove import stubs"
```

---

### Task 3: Remove `search_by_criteria` from `discovery_tools.py`

**Rationale:** `search_by_criteria` is replaced by Phase 1 `filter_tracks` (in `search_tools.py`).
`find_similar_tracks` stays — it has unique LLM-assisted functionality.

**Files:**
- Modify: `app/mcp/workflows/discovery_tools.py` (remove `search_by_criteria`)
- Modify: `tests/mcp/test_workflow_discovery.py` (remove `search_by_criteria` tests)

**Step 1: Remove `search_by_criteria` function from `discovery_tools.py`**

Delete the `search_by_criteria` tool function (lines ~190-264).
Also remove now-unused import: `TrackDetails` from `app.mcp.types`.

**Step 2: Update test file**

Remove any test for `search_by_criteria`. Keep `find_similar_tracks` tests.

**Step 3: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_discovery.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(mcp): remove search_by_criteria — replaced by filter_tracks"
```

---

### Task 4: Remove old export tools (`export_set_m3u`, `export_set_json`)

**Rationale:** Phase 2 `unified_export_tools.py` replaces M3U/JSON export.
`export_set_rekordbox` is unique and stays.

**Files:**
- Modify: `app/mcp/workflows/export_tools.py` (remove `export_set_m3u`, `export_set_json`; keep `export_set_rekordbox`)
- Modify: `tests/mcp/test_workflow_export.py` (remove old export tests)

**Step 1: Remove `export_set_m3u` and `export_set_json` from `export_tools.py`**

Keep only `export_set_rekordbox` and its helper functions (`_safe_filename`, `_build_display_name`, `_build_transitions`).

**Step 2: Update tests**

Remove tests for `export_set_m3u` and `export_set_json`. Keep `export_set_rekordbox` tests.

**Step 3: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_export.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(mcp): remove old export_set_m3u/json — unified_export_tools replaces"
```

---

### Task 5: Migrate types from `types.py` to `types_v2.py`

**Rationale:** After Tasks 1-4, only `setbuilder_tools.py`, `curation_tools.py`,
`discovery_tools.py`, and `export_tools.py` still use types from `types.py` / `types_curation.py`.

**Files:**
- Modify: `app/mcp/types_v2.py` (add surviving types)
- Modify: all files that import from `types.py` / `types_curation.py`
- Delete: `app/mcp/types.py`
- Delete: `app/mcp/types_curation.py`

**Step 1: Identify which types are still used after Tasks 1-4**

From `types.py`:
- `SetBuildResult` — used by `setbuilder_tools.py`
- `TransitionScoreResult` — used by `setbuilder_tools.py`
- `ExportResult` — used by `export_tools.py` (rekordbox)
- `SimilarTracksResult` — used by `discovery_tools.py`
- `SearchStrategy` — used by `discovery_tools.py`

From `types_curation.py`:
- `ClassifyResult`, `MoodDistribution` — used by `curation_tools.py`
- `SetReviewResult`, `WeakTransition` — used by `curation_tools.py`
- `LibraryGapResult`, `GapDescription` — used by `curation_tools.py`

**Step 2: Move surviving types to `types_v2.py`**

Append to `app/mcp/types_v2.py` (at the bottom, after existing Phase 1-2 types):

```python
# --- Legacy types (migrated from types.py / types_curation.py in Phase 4) ---

class SetBuildResult(BaseModel):
    """Result of building a DJ set."""
    set_id: int
    version_id: int
    name: str
    track_count: int
    quality_score: float

class TransitionScoreResult(BaseModel):
    """Result of scoring transitions in a set."""
    set_id: int
    version_id: int
    transitions: list[dict[str, Any]]
    overall_score: float

class ExportResult(BaseModel):
    """Result of exporting a set to a file format."""
    set_id: int
    format: str
    track_count: int
    content: str

class SimilarTracksResult(BaseModel):
    """Result of finding similar tracks."""
    playlist_id: int
    candidates_found: int
    candidates_selected: int
    added_count: int

class SearchStrategy(BaseModel):
    """LLM-generated search strategy."""
    queries: list[str] = Field(default_factory=list)
    target_bpm_range: tuple[float, float] = (0, 300)
    target_keys: list[str] = Field(default_factory=list)

class MoodDistribution(BaseModel):
    """Distribution of tracks across mood categories."""
    mood: str
    count: int
    percentage: float

class ClassifyResult(BaseModel):
    """Result of classifying tracks by mood."""
    total_classified: int
    distribution: list[MoodDistribution]

class WeakTransition(BaseModel):
    """A weak transition flagged for attention."""
    position: int
    from_track: str
    to_track: str
    score: float
    reason: str

class SetReviewResult(BaseModel):
    """Result of reviewing a DJ set quality."""
    set_id: int
    version_id: int
    overall_score: float
    weak_transitions: list[WeakTransition]
    variety_score: float

class GapDescription(BaseModel):
    """A gap in the library coverage."""
    category: str
    description: str
    severity: str

class LibraryGapResult(BaseModel):
    """Result of analyzing library gaps."""
    total_tracks: int
    gaps: list[GapDescription]
```

NOTE: Copy exact field definitions from the current `types.py` and `types_curation.py`.
The above is a template — verify each field matches the actual file.

**Step 3: Update all imports**

In `setbuilder_tools.py`:
```python
# OLD
from app.mcp.types import ExportResult, SetBuildResult, TransitionScoreResult
# NEW
from app.mcp.types_v2 import ExportResult, SetBuildResult, TransitionScoreResult
```

In `discovery_tools.py`:
```python
# OLD
from app.mcp.types import SimilarTracksResult, TrackDetails
from app.mcp.types import SearchStrategy
# NEW
from app.mcp.types_v2 import SimilarTracksResult, SearchStrategy
```

In `curation_tools.py`:
```python
# OLD
from app.mcp.types_curation import (ClassifyResult, ...)
# NEW
from app.mcp.types_v2 import (ClassifyResult, ...)
```

In `export_tools.py`:
```python
# OLD
from app.mcp.types import ExportResult
# NEW
from app.mcp.types_v2 import ExportResult
```

**Step 4: Delete old type files**

```bash
rm app/mcp/types.py
rm app/mcp/types_curation.py
```

**Step 5: Run full test suite**

```bash
uv run pytest tests/mcp/ -v --tb=short 2>&1 | tail -30
```

Expected: PASS (except `test_client_integration.py` tool list — fixed in Task 10).
Also delete `tests/mcp/test_sampling_types.py` if it imports from old `types.py`.

**Step 6: Commit**

```bash
git add -A && git commit -m "refactor(mcp): migrate types to types_v2, delete types.py + types_curation.py"
```

---

### Task 6: Refactor `discovery_tools.py` — use entity refs

**Rationale:** `find_similar_tracks` takes `playlist_id: int`. Migrate to accept
entity ref (consistent with Phase 1-3 tools).

**Files:**
- Modify: `app/mcp/workflows/discovery_tools.py`
- Modify: `tests/mcp/test_workflow_discovery.py`

**Step 1: Write test for ref-based parameter**

```python
async def test_find_similar_tracks_accepts_ref(workflow_mcp: FastMCP):
    """find_similar_tracks accepts playlist_ref parameter."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "find_similar_tracks")
    params = tool.inputSchema.get("properties", {})
    assert "playlist_ref" in params
```

**Step 2: Migrate `find_similar_tracks` to use refs**

```python
from app.mcp.entity_finder import PlaylistFinder
from app.mcp.refs import parse_ref

async def find_similar_tracks(
    playlist_ref: str | int,  # was: playlist_id: int
    ctx: Context,
    count: int = 10,
    criteria: str = "bpm,key,energy",
    playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    features_svc: AudioFeaturesService = Depends(get_features_service),
) -> SimilarTracksResult:
    # Resolve ref to playlist
    parsed = parse_ref(playlist_ref)
    finder = PlaylistFinder(playlist_svc)
    result = await finder.find(parsed)
    if result.error:
        raise ToolError(result.error)
    playlist_id = int(result.entity.ref.split(":")[-1])
    # ... rest of the function uses playlist_id as before
```

**Step 3: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_discovery.py -v
```

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(mcp): migrate find_similar_tracks to entity refs"
```

---

### Task 7: Refactor `setbuilder_tools.py` — use entity refs

**Rationale:** `build_set`, `rebuild_set`, `score_transitions` take integer IDs.
Migrate to accept refs for consistency.

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py`
- Modify: `tests/mcp/test_workflow_setbuilder.py`

**Step 1: Update tool parameters**

For each tool (`build_set`, `rebuild_set`, `score_transitions`):
- Replace `playlist_id: int` with `playlist_ref: str | int`
- Replace `set_id: int` with `set_ref: str | int`
- Add ref resolution at the start of each function

**Step 2: Update tests**

Tests should still pass with integer IDs (ref parser handles bare integers).

**Step 3: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_setbuilder.py -v
```

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(mcp): migrate setbuilder tools to entity refs"
```

---

### Task 8: Refactor `curation_tools.py` — use entity refs

**Files:**
- Modify: `app/mcp/workflows/curation_tools.py`
- Modify: `tests/mcp/test_workflow_curation.py`

Similar migration as Tasks 6-7. Replace integer ID parameters with `str | int` refs.

**Step 1: Update tool parameters + add ref resolution**

**Step 2: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_curation.py -v
```

**Step 3: Commit**

```bash
git add -A && git commit -m "refactor(mcp): migrate curation tools to entity refs"
```

---

### Task 9: Refactor `export_tools.py` (rekordbox) — use entity refs

**Files:**
- Modify: `app/mcp/workflows/export_tools.py`

Replace `set_id: int, version_id: int` with `set_ref: str | int, version_id: int`.

**Step 1: Update and test**

**Step 2: Commit**

```bash
git add -A && git commit -m "refactor(mcp): migrate rekordbox export to entity refs"
```

---

### Task 10: Update `test_client_integration.py` tool list

**Rationale:** After Tasks 1-4, the expected tool list has changed. Remove deleted tools,
verify the final tool inventory.

**Files:**
- Modify: `tests/mcp/test_client_integration.py`

**Step 1: Update expected tool set**

Remove from `expected`:
- `get_playlist_status`, `get_track_details` (Task 1)
- `import_playlist`, `import_tracks` (Task 2)
- `search_by_criteria` (Task 3)
- `export_set_m3u`, `export_set_json` (Task 4)

The final expected set should be:
```python
expected = {
    # Phase 1: Search
    "search", "filter_tracks",
    # Phase 2: CRUD
    "list_tracks", "get_track", "create_track", "update_track", "delete_track",
    "list_playlists", "get_playlist", "create_playlist", "update_playlist", "delete_playlist",
    "list_sets", "get_set", "create_set", "update_set", "delete_set",
    "list_features", "get_features", "save_features",
    # Phase 2: Compute + Export
    # (check actual names from compute_tools.py and unified_export_tools.py)
    # Phase 3: Sync
    "sync_set_to_ym", "sync_set_from_ym", "sync_playlist",
    # Survivors (migrated)
    "find_similar_tracks",
    "build_set", "rebuild_set", "score_transitions",
    "export_set_rekordbox",
    "classify_tracks", "review_set", "analyze_library_gaps",
    "download_tracks",
    # Admin
    "activate_heavy_mode", "activate_ym_raw", "list_platforms",
}
```

**Step 2: Run full test suite**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: ALL PASS

**Step 3: Commit**

```bash
git add -A && git commit -m "test(mcp): update tool list expectations for Phase 4 cleanup"
```

---

### Task 11: Lint + type-check verification

**Files:** None (verification only)

**Step 1: Run ruff check**

```bash
uv run ruff check app/mcp/ tests/mcp/ && uv run ruff format --check app/mcp/ tests/mcp/
```

Fix any issues.

**Step 2: Run mypy**

```bash
uv run mypy app/mcp/
```

Fix any type errors (especially from moved types).

**Step 3: Run full pytest**

```bash
uv run pytest -v --tb=short
```

Expected: ALL tests pass (not just `tests/mcp/` but the entire suite).

**Step 4: Commit fixes if any**

```bash
git add -A && git commit -m "fix(mcp): lint and type-check fixes for Phase 4 cleanup"
```

---

### Task 12: Final integration verification

**Step 1: Count tools**

```bash
make mcp-list 2>/dev/null | wc -l
```

Verify tool count matches expectations (removed 7 tools, should be ~40-45 DJ tools).

**Step 2: Run the MCP server**

```bash
timeout 5 make run 2>&1 | head -10
```

Verify no import errors at startup.

**Step 3: Commit final state**

```bash
git add -A && git commit -m "chore(mcp): Phase 4 cleanup complete — 7 legacy tools removed, types consolidated"
```

---

## Summary

| Task | Action | Tools affected |
|------|--------|---------------|
| 1 | Delete `analysis_tools.py` | -`get_playlist_status`, -`get_track_details` |
| 2 | Extract `download_tools.py`, delete import stubs | -`import_playlist`, -`import_tracks` |
| 3 | Remove `search_by_criteria` | -`search_by_criteria` |
| 4 | Remove old M3U/JSON export | -`export_set_m3u`, -`export_set_json` |
| 5 | Migrate types to `types_v2.py` | Type files consolidated |
| 6-9 | Refactor survivors to use refs | `find_similar_tracks`, `build_set`, etc. |
| 10 | Update test expectations | `test_client_integration.py` |
| 11-12 | Verification | Lint, types, integration |

**Estimated time:** 2-3 hours
**Risk:** Low — pure cleanup, no new functionality
