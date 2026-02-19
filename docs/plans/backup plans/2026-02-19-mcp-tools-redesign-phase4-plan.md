# MCP Tools Redesign — Phase 4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all legacy tools, stubs, dead-code types, and duplicates — completing the migration to the new agent-first MCP architecture built in Phases 1–3.

**Architecture:** Phase 4 is pure cleanup. No new modules. Delete legacy tool files, consolidate types into `types_v2.py`, update `server.py` registrations, refactor surviving tools (curation, discovery, setbuilder) to use Phase 1–3 infrastructure (EntityFinder refs, response envelopes, converters). Remove corresponding test files.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest

**Design doc:** `docs/plans/2026-02-19-mcp-tools-redesign-design.md`
**Phase 1 plan:** `docs/plans/2026-02-19-mcp-tools-redesign-plan.md` (prerequisite)
**Phase 2 plan:** `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md` (prerequisite)
**Phase 3 plan:** `docs/plans/2026-02-19-mcp-tools-redesign-phase3-plan.md` (prerequisite)

**Phase 1 delivers (used by this plan):**
- `app/mcp/types_v2.py` — TrackSummary, TrackDetail, PlaylistSummary, SetSummary, ArtistSummary, LibraryStats, PaginationInfo, SearchResponse, FindResult
- `app/mcp/refs.py` — parse_ref, ParsedRef, RefType
- `app/mcp/entity_finder.py` — TrackFinder, PlaylistFinder, SetFinder, ArtistFinder
- `app/mcp/pagination.py` — encode_cursor, decode_cursor, paginate_params
- `app/mcp/library_stats.py` — get_library_stats(session)
- `app/mcp/workflows/search_tools.py` — search, filter_tracks tools

**Phase 2 delivers (used by this plan):**
- `app/mcp/response.py` — wrap_list, wrap_detail, wrap_action helpers
- `app/mcp/converters.py` — track_to_summary, playlist_to_summary, set_to_summary, features_to_detail
- CRUD tools: list_tracks, get_track, list_playlists, get_playlist, list_sets, get_set, etc.
- Unified `export_set(format=...)` tool
- Compute/persist split: analyze, build_set, score_transitions return data; save_features, create_set persist

**Phase 3 delivers (used by this plan):**
- `app/mcp/platforms/` — MusicPlatform protocol, PlatformRegistry, YandexMusicAdapter
- `app/mcp/sync/` — SyncEngine, DbTrackMapper, compute_sync_diff
- Rewritten sync tools: sync_playlist, sync_set_to_ym, sync_set_from_ym
- Visibility tools: activate_ym_raw, list_platforms

---

## Inventory: What to Remove / Refactor

### Files to DELETE entirely

| File | Reason | Replaced by |
|------|--------|-------------|
| `app/mcp/workflows/analysis_tools.py` | `get_playlist_status`, `get_track_details` | Phase 2 CRUD: `list_playlists`/`get_playlist`, `list_tracks`/`get_track` |
| `app/mcp/workflows/sync_tools.py` | 3 stubs (sync_set_to_ym, sync_set_from_ym, sync_playlist) | Phase 3 rewritten tools in same file |
| `app/mcp/types.py` | 13 legacy models (PlaylistStatus, TrackDetails, etc.) | `types_v2.py` + Phase 2 envelope models |
| `app/mcp/types_curation.py` | 8 models (2 dead: CurateCandidate, CurateSetResult) | Surviving models merged into `types_v2.py` |
| `tests/mcp/test_workflow_analysis.py` | Tests for deleted analysis_tools.py | Phase 2 CRUD tests |
| `tests/mcp/test_workflow_sync.py` | Tests for deleted sync stubs | Phase 3 sync tests |
| `tests/mcp/test_workflow_import.py` | Tests for deleted import stubs | Phase 2 CRUD tests |

### Tools to REMOVE from existing files

| File | Tool to remove | Reason | Replaced by |
|------|---------------|--------|-------------|
| `app/mcp/workflows/import_tools.py` | `import_playlist` (stub) | Never implemented | Phase 2 CRUD `create_playlist` + `download_tracks` |
| `app/mcp/workflows/import_tools.py` | `import_tracks` (stub) | Never implemented | Phase 2 CRUD `create_track` + `download_tracks` |
| `app/mcp/workflows/discovery_tools.py` | `search_by_criteria` | Replaced | Phase 1 `filter_tracks` |
| `app/mcp/workflows/setbuilder_tools.py` | `export_set_m3u` (duplicate) | Simpler duplicate | Phase 2 unified `export_set(format="m3u")` |
| `app/mcp/workflows/setbuilder_tools.py` | `export_set_json` (duplicate) | Simpler duplicate | Phase 2 unified `export_set(format="json")` |

### Dead-code types to REMOVE

| Type | File | Reason |
|------|------|--------|
| `SwapSuggestion` | `types.py` | Was for removed `adjust_set` tool |
| `ReorderSuggestion` | `types.py` | Was for removed `adjust_set` tool |
| `AdjustmentPlan` | `types.py` | Was for removed `adjust_set` tool |
| `CurateCandidate` | `types_curation.py` | Was for removed `curate_set` tool |
| `CurateSetResult` | `types_curation.py` | Was for removed `curate_set` tool |

### Tools to REFACTOR (keep, but update to new infra)

| Tool | Current file | Changes needed |
|------|-------------|----------------|
| `download_tracks` | `import_tools.py` | Move to own file, use refs instead of track_ids, wrap in response envelope |
| `find_similar_tracks` | `discovery_tools.py` | Use refs, PlatformRegistry for search, response envelope |
| `build_set` | `setbuilder_tools.py` | Use refs for playlist_ref, response envelope |
| `rebuild_set` | `setbuilder_tools.py` | Use refs for set_ref, response envelope |
| `score_transitions` | `setbuilder_tools.py` | Use refs for set_ref, response envelope |
| `classify_tracks` | `curation_tools.py` | Use new types (merge MoodDistribution into types_v2), response envelope |
| `analyze_library_gaps` | `curation_tools.py` | Use new types, response envelope |
| `review_set` | `curation_tools.py` | Use refs for set_ref, response envelope |

---

## Task 1: Delete analysis_tools.py and its tests

**Files:**
- Delete: `app/mcp/workflows/analysis_tools.py`
- Delete: `tests/mcp/test_workflow_analysis.py`
- Modify: `app/mcp/workflows/server.py:10,36` — remove import and registration

Phase 2 already provides `list_playlists`, `get_playlist`, `list_tracks`, `get_track` with richer data (response envelope, stats, pagination). The old `get_playlist_status` and `get_track_details` are redundant.

**Step 1: Verify Phase 2 CRUD tools exist**

Check that Phase 2 CRUD tools are registered and working. These replace the analysis tools:

```bash
uv run pytest tests/mcp/test_crud_tools.py -v --tb=short
```

Expected: All CRUD tests pass (list_tracks, get_track, list_playlists, get_playlist).

**Step 2: Remove analysis_tools import and registration from server.py**

In `app/mcp/workflows/server.py`:

Remove line 10:
```python
from app.mcp.workflows.analysis_tools import register_analysis_tools
```

Remove line 36:
```python
    register_analysis_tools(mcp)
```

**Step 3: Delete the files**

```bash
rm app/mcp/workflows/analysis_tools.py
rm tests/mcp/test_workflow_analysis.py
```

**Step 4: Run tests to verify nothing breaks**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: All tests pass. No imports reference `analysis_tools` or `get_playlist_status`/`get_track_details`.

**Step 5: Fix any broken imports**

Search for stale references:

```bash
rg "analysis_tools\|get_playlist_status\|get_track_details" app/ tests/ --type py
```

Expected: No results (or only in docs/comments). Fix any real imports.

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(mcp): remove legacy analysis_tools (replaced by Phase 2 CRUD)"
```

---

## Task 2: Delete sync stubs (replaced by Phase 3)

**Files:**
- Delete: `app/mcp/workflows/sync_tools.py` (the OLD file with stubs)
- Delete: `tests/mcp/test_workflow_sync.py` (tests for stubs)
- Modify: `app/mcp/workflows/server.py` — remove old sync import, add Phase 3 sync registration

Phase 3 replaces all 3 stubs with working implementations using SyncEngine + PlatformRegistry. The new sync tools are registered in a different module (Phase 3 plan Task 9–11).

**Step 1: Verify Phase 3 sync tools exist**

Check that Phase 3 sync tools are registered:

```bash
rg "sync_playlist|sync_set_to_ym|sync_set_from_ym" app/mcp/ --type py -l
```

Expected: New implementations exist in Phase 3 module (e.g. `app/mcp/workflows/sync_tools.py` or `app/mcp/sync/tools.py` — wherever Phase 3 placed them).

**Step 2: Update server.py**

If Phase 3 already updated `server.py` to register the new sync tools, simply verify. If the old `register_sync_tools` still points to the stub file:

Remove from `app/mcp/workflows/server.py`:
```python
from app.mcp.workflows.sync_tools import register_sync_tools
```

Replace with Phase 3's registration (check Phase 3's actual implementation for the correct import path).

**Step 3: Delete old files**

```bash
rm app/mcp/workflows/sync_tools.py
rm tests/mcp/test_workflow_sync.py
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: All pass. Phase 3 sync tests cover the new implementations.

**Step 5: Fix stale references**

```bash
rg "from app.mcp.workflows.sync_tools" app/ tests/ --type py
```

Fix any remaining imports.

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(mcp): remove sync stubs (replaced by Phase 3 SyncEngine)"
```

---

## Task 3: Remove import stubs, keep download_tracks

**Files:**
- Modify: `app/mcp/workflows/import_tools.py` — remove `import_playlist` and `import_tracks` stubs
- Modify: `tests/mcp/test_workflow_import.py` — remove stub tests (or delete file if only stub tests)
- Modify: `tests/mcp/test_import_playlist.py` — delete if tests only test the stub

The stubs return zero results and print manual instructions. Phase 2 CRUD tools (`create_track`, `create_playlist`) + `download_tracks` replace them. The working `download_tracks` tool stays.

**Step 1: Edit import_tools.py — remove stubs**

Keep only `download_tracks`. The file becomes:

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

def register_import_tools(mcp: FastMCP) -> None:
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

        Returns:
            Download statistics (downloaded, skipped, failed counts)
        """
        library_path = Path(settings.dj_library_path).expanduser()

        download_svc = DownloadService(
            session=session,
            ym_client=ym_client,
            library_path=library_path,
        )

        result = await download_svc.download_tracks_batch(
            track_ids=track_ids,
            prefer_bitrate=prefer_bitrate,
        )

        return result
```

Note: removed imports of `ImportResult` (from deleted `types.py`).

**Step 2: Clean up test files**

Delete `tests/mcp/test_import_playlist.py` (if it only tests the stub).
Update `tests/mcp/test_workflow_import.py` — remove tests for `import_playlist` and `import_tracks`. Keep tests for `download_tracks`.

**Step 3: Run tests**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: All pass.

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(mcp): remove import stubs (import_playlist, import_tracks)"
```

---

## Task 4: Remove search_by_criteria from discovery_tools.py

**Files:**
- Modify: `app/mcp/workflows/discovery_tools.py` — remove `search_by_criteria` tool
- Modify: `tests/mcp/test_workflow_discovery.py` — remove `search_by_criteria` tests

Phase 1's `filter_tracks` tool (in `search_tools.py`) replaces this with richer filtering (response envelope, pagination, refs).

**Step 1: Verify Phase 1 filter_tracks exists**

```bash
rg "def filter_tracks" app/mcp/workflows/search_tools.py
```

Expected: Found in Phase 1's search_tools.py.

**Step 2: Remove search_by_criteria from discovery_tools.py**

Remove the entire `search_by_criteria` function (lines 190–264 in current file) and its imports. The file keeps only `find_similar_tracks`.

After edit, remove unused imports:
- Remove `TrackDetails` from `from app.mcp.types import ...` (this import will be gone entirely after types.py deletion)
- Remove `TrackService` import and `get_track_service` DI if only used by search_by_criteria

Updated imports for discovery_tools.py:

```python
"""Discovery tools for DJ workflow MCP server."""

from __future__ import annotations

import contextlib

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError
from app.mcp.dependencies import get_features_service, get_playlist_service
from app.mcp.types import SimilarTracksResult
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.utils.audio.camelot import key_code_to_camelot
```

Note: `get_track_service` and `TrackService` removed (only used by `search_by_criteria`). `TrackDetails` removed. `SimilarTracksResult` kept for now (migrated in Task 8).

**Step 3: Update tests**

Remove `search_by_criteria` tests from `tests/mcp/test_workflow_discovery.py`. Keep `find_similar_tracks` tests.

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_discovery.py -v --tb=short
```

Expected: All remaining tests pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(mcp): remove search_by_criteria (replaced by Phase 1 filter_tracks)"
```

---

## Task 5: Remove duplicate exports from setbuilder_tools.py

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py` — remove `export_set_m3u` and `export_set_json`
- Modify: `tests/mcp/test_workflow_setbuilder.py` — remove duplicate export tests

Phase 2 unifies exports into `export_set(format=...)`. The rich export tools in `export_tools.py` are the canonical implementations that Phase 2 wraps. The duplicate simple versions in `setbuilder_tools.py` must go.

**Step 1: Verify Phase 2 unified export_set exists**

```bash
rg "def export_set" app/mcp/ --type py
```

Expected: Phase 2 unified `export_set` tool found.

**Step 2: Remove duplicate tools from setbuilder_tools.py**

Remove `export_set_m3u` (lines 276–325 in current file) and `export_set_json` (lines 327–431) from `setbuilder_tools.py`.

After removal, clean up imports — remove:
```python
from app.mcp.types import ExportResult
```
(if `ExportResult` was only used by the deleted functions).

Also remove `UnifiedTransitionScoringService` import if it was only used by `export_set_json` (check — `score_transitions` also uses it, so keep it).

**Step 3: Update tests**

Remove export-related tests from `tests/mcp/test_workflow_setbuilder.py`.

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_setbuilder.py tests/mcp/test_workflow_export.py -v --tb=short
```

Expected: All pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(mcp): remove duplicate export tools from setbuilder_tools"
```

---

## Task 6: Delete legacy types.py

**Files:**
- Delete: `app/mcp/types.py`
- Modify: all files that import from `app.mcp.types` — switch to `app.mcp.types_v2`

This is the most impactful deletion. Every module importing from `types.py` must be updated.

**Step 1: Find all imports from types.py**

```bash
rg "from app\.mcp\.types import" app/ tests/ --type py
```

Expected results (after Tasks 1–5 cleanup):
- `app/mcp/workflows/discovery_tools.py` — `SimilarTracksResult`
- `app/mcp/workflows/setbuilder_tools.py` — `SetBuildResult`, `TransitionScoreResult`
- `app/mcp/workflows/export_tools.py` — `ExportResult`
- Various test files

**Step 2: Migrate surviving types to types_v2.py**

Types that are still used by surviving tools and NOT already in `types_v2.py`:

| Type | Used by | Action |
|------|---------|--------|
| `SetBuildResult` | `setbuilder_tools.py` | Add to `types_v2.py` |
| `TransitionScoreResult` | `setbuilder_tools.py` | Add to `types_v2.py` |
| `ExportResult` | `export_tools.py` | Add to `types_v2.py` (or Phase 2 already has it) |
| `SimilarTracksResult` | `discovery_tools.py` | Add to `types_v2.py` |
| `SearchStrategy` | `discovery_tools.py` (inside find_similar_tracks) | Add to `types_v2.py` |
| `ImportResult` | Removed in Task 3 | Skip — dead code |
| `PlaylistStatus` | Removed in Task 1 | Skip — dead code |
| `TrackDetails` | Removed in Task 4 | Skip — dead code |
| `AnalysisResult` | Not used by any surviving tool | Skip — dead code |
| `SwapSuggestion` | Dead code | Skip |
| `ReorderSuggestion` | Dead code | Skip |
| `AdjustmentPlan` | Dead code | Skip |

Add to `app/mcp/types_v2.py` (at the end, before any `__all__`):

```python
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
    structure: float = 0.5
    recommended_type: str | None = None
    type_confidence: float | None = None
    reason: str | None = None
    alt_type: str | None = None

class ExportResult(BaseModel):
    """Result of exporting a set."""

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
    """LLM-generated search strategy for finding similar tracks."""

    queries: list[str]
    target_bpm_range: tuple[float, float]
    target_keys: list[str]
    target_energy_range: tuple[float, float]
    reasoning: str
```

**Step 3: Update all imports**

Replace `from app.mcp.types import X` with `from app.mcp.types_v2 import X` in:

- `app/mcp/workflows/setbuilder_tools.py`
- `app/mcp/workflows/export_tools.py`
- `app/mcp/workflows/discovery_tools.py`
- Any test files that reference these types

**Step 4: Delete types.py**

```bash
rm app/mcp/types.py
```

**Step 5: Run tests**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: All pass. No `ModuleNotFoundError` for `app.mcp.types`.

**Step 6: Lint and type-check**

```bash
uv run ruff check app/mcp/ tests/mcp/ && uv run mypy app/mcp/
```

Expected: Clean.

**Step 7: Commit**

```bash
git add -A
git commit -m "refactor(mcp): delete legacy types.py, migrate surviving types to types_v2"
```

---

## Task 7: Delete types_curation.py, merge survivors into types_v2.py

**Files:**
- Delete: `app/mcp/types_curation.py`
- Modify: `app/mcp/types_v2.py` — add surviving curation types
- Modify: `app/mcp/workflows/curation_tools.py` — update imports
- Modify: `tests/mcp/test_workflow_curation.py` — update imports

**Step 1: Identify surviving types**

From `types_curation.py`:

| Type | Used by | Action |
|------|---------|--------|
| `MoodDistribution` | `curation_tools.py` (classify_tracks, analyze_library_gaps) | Move to `types_v2.py` |
| `ClassifyResult` | `curation_tools.py` (classify_tracks) | Move to `types_v2.py` |
| `WeakTransition` | `curation_tools.py` (review_set) | Move to `types_v2.py` |
| `SetReviewResult` | `curation_tools.py` (review_set) | Move to `types_v2.py` |
| `GapDescription` | `curation_tools.py` (analyze_library_gaps) | Move to `types_v2.py` |
| `LibraryGapResult` | `curation_tools.py` (analyze_library_gaps) | Move to `types_v2.py` |
| `CurateCandidate` | Dead (curate_set removed) | Don't migrate |
| `CurateSetResult` | Dead (curate_set removed) | Don't migrate |

**Step 2: Add to types_v2.py**

Append to `app/mcp/types_v2.py`:

```python
# --- Curation types ---

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
    """A weak transition identified during review."""

    position: int
    from_track_id: int
    to_track_id: int
    score: float
    reason: str

class SetReviewResult(BaseModel):
    """Result of reviewing a set version."""

    overall_score: float
    energy_arc_adherence: float
    variety_score: float
    weak_transitions: list[WeakTransition]
    suggestions: list[str]

class GapDescription(BaseModel):
    """Description of a library gap."""

    mood: str
    needed: int
    available: int
    deficit: int

class LibraryGapResult(BaseModel):
    """Result of analyzing library gaps."""

    total_tracks: int
    tracks_with_features: int
    mood_distribution: list[MoodDistribution]
    gaps: list[GapDescription]
    recommendations: list[str]
```

**Step 3: Update curation_tools.py imports**

Replace:
```python
from app.mcp.types_curation import (
    ClassifyResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
    SetReviewResult,
    WeakTransition,
)
```

With:
```python
from app.mcp.types_v2 import (
    ClassifyResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
    SetReviewResult,
    WeakTransition,
)
```

**Step 4: Update test imports**

Update `tests/mcp/test_workflow_curation.py` — replace any `from app.mcp.types_curation import` with `from app.mcp.types_v2 import`.

**Step 5: Delete types_curation.py**

```bash
rm app/mcp/types_curation.py
```

**Step 6: Check for stale references**

```bash
rg "types_curation" app/ tests/ --type py
```

Expected: No results.

**Step 7: Run tests + lint**

```bash
uv run pytest tests/mcp/test_workflow_curation.py -v --tb=short
uv run ruff check app/mcp/ tests/mcp/
```

Expected: All pass, clean lint.

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor(mcp): delete types_curation.py, merge survivors into types_v2"
```

---

## Task 8: Refactor discovery_tools.py — use Phase 1–3 infra

**Files:**
- Modify: `app/mcp/workflows/discovery_tools.py`
- Modify: `tests/mcp/test_workflow_discovery.py`

After Tasks 4 and 6, `discovery_tools.py` only has `find_similar_tracks`. Refactor it to use:
- EntityFinder refs (`playlist_ref: str` instead of `playlist_id: int`)
- PlatformRegistry for platform search (Phase 3)
- Response envelope via `wrap_action` (Phase 2)
- `types_v2.SimilarTracksResult`

**Step 1: Write updated test**

In `tests/mcp/test_workflow_discovery.py`:

```python
async def test_find_similar_tracks_accepts_ref():
    """find_similar_tracks should accept playlist_ref string."""
    # Call with ref string instead of int
    result = await call_tool("find_similar_tracks", {
        "playlist_ref": "local:1",
        "count": 5,
    })
    # Should resolve ref and return SimilarTracksResult
    assert "playlist_id" in result or "error" in result
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_workflow_discovery.py::test_find_similar_tracks_accepts_ref -v
```

Expected: FAIL — `find_similar_tracks` doesn't accept `playlist_ref` yet.

**Step 3: Update find_similar_tracks signature and body**

```python
from app.mcp.entity_finder import PlaylistFinder
from app.mcp.refs import parse_ref

@mcp.tool(tags={"discovery"})
async def find_similar_tracks(
    playlist_ref: str,
    ctx: Context,
    count: int = 10,
    criteria: str = "bpm,key,energy",
    playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    features_svc: AudioFeaturesService = Depends(get_features_service),
) -> SimilarTracksResult:
    """Find tracks similar to those in a playlist using LLM-assisted search.

    Args:
        playlist_ref: Playlist reference (local:42, "playlist name", or int).
        count: How many candidates to find.
        criteria: Comma-separated similarity criteria (bpm, key, energy).
    """
    # Resolve ref → playlist_id
    parsed = parse_ref(playlist_ref)
    finder = PlaylistFinder(playlist_svc)
    found = await finder.find(parsed)
    if not found.exact or not found.entities:
        return SimilarTracksResult(
            playlist_id=0,
            candidates_found=0,
            candidates_selected=0,
            added_count=0,
        )
    playlist_id = found.entities[0].playlist_id

    # ... rest of existing logic using playlist_id ...
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/mcp/test_workflow_discovery.py -v --tb=short
```

Expected: All pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(mcp): find_similar_tracks uses EntityFinder refs"
```

---

## Task 9: Refactor setbuilder_tools.py — use refs + envelope

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py`
- Modify: `tests/mcp/test_workflow_setbuilder.py`

After Task 5 (duplicate exports removed) and Task 6 (types migrated), refactor the remaining tools to use EntityFinder refs.

**Step 1: Write updated tests**

```python
async def test_build_set_accepts_playlist_ref():
    """build_set should accept playlist_ref string."""
    result = await call_tool("build_set", {
        "playlist_ref": "local:1",
        "set_name": "Test Set",
    })
    assert "set_id" in result

async def test_score_transitions_accepts_set_ref():
    """score_transitions should accept set_ref + version_ref."""
    result = await call_tool("score_transitions", {
        "set_ref": "local:1",
        "version_id": 1,
    })
    assert isinstance(result, list)
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/mcp/test_workflow_setbuilder.py -v -k "ref" --tb=short
```

Expected: FAIL — tools don't accept refs yet.

**Step 3: Update build_set**

Change `playlist_id: int` → `playlist_ref: str`, resolve via `PlaylistFinder`:

```python
from app.mcp.entity_finder import PlaylistFinder, SetFinder
from app.mcp.refs import parse_ref

@mcp.tool(tags={"setbuilder"})
async def build_set(
    playlist_ref: str,
    set_name: str,
    ctx: Context,
    template: str | None = None,
    energy_arc: str = "classic",
    exclude_track_ids: list[int] | None = None,
    set_svc: DjSetService = Depends(get_set_service),
    gen_svc: SetGenerationService = Depends(get_set_generation_service),
    playlist_svc: DjPlaylistService = Depends(get_playlist_service),
) -> SetBuildResult:
    """Build a DJ set from a playlist using template + genetic algorithm.

    Args:
        playlist_ref: Source playlist reference (local:42, "playlist name").
        set_name: Name for the new DJ set.
        template: Template name (classic_60, peak_hour_60, etc.) or None.
        energy_arc: Energy arc shape.
        exclude_track_ids: Track IDs to exclude from selection.
    """
    parsed = parse_ref(playlist_ref)
    finder = PlaylistFinder(playlist_svc)
    found = await finder.find(parsed)
    if not found.exact or not found.entities:
        raise ValueError(f"Playlist not found: {playlist_ref}")
    playlist_id = found.entities[0].playlist_id

    # ... rest of existing logic using playlist_id ...
```

**Step 4: Update rebuild_set and score_transitions**

Change `set_id: int` → `set_ref: str`, resolve via `SetFinder`.

**Step 5: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_setbuilder.py -v --tb=short
```

Expected: All pass.

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(mcp): setbuilder tools use EntityFinder refs"
```

---

## Task 10: Refactor curation_tools.py — use refs + types_v2

**Files:**
- Modify: `app/mcp/workflows/curation_tools.py`
- Modify: `tests/mcp/test_workflow_curation.py`

After Task 7, imports already point to `types_v2`. Now add ref support for `review_set`.

**Step 1: Write test for ref-based review_set**

```python
async def test_review_set_accepts_refs():
    """review_set should accept set_ref string."""
    result = await call_tool("review_set", {
        "set_ref": "local:1",
        "version_id": 1,
    })
    assert "overall_score" in result
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_workflow_curation.py -v -k "ref" --tb=short
```

Expected: FAIL.

**Step 3: Update review_set**

Change `set_id: int` → `set_ref: str`:

```python
from app.mcp.entity_finder import SetFinder
from app.mcp.refs import parse_ref

@mcp.tool(annotations={"readOnlyHint": True}, tags={"curation", "setbuilder"})
async def review_set(
    set_ref: str,
    version_id: int,
    ctx: Context,
    set_svc: DjSetService = Depends(get_set_service),
    features_svc: AudioFeaturesService = Depends(get_features_service),
) -> SetReviewResult:
    """Review a DJ set version — identify weak spots and suggest improvements.

    Args:
        set_ref: DJ set reference (local:42, "set name").
        version_id: Set version to review.
    """
    parsed = parse_ref(set_ref)
    finder = SetFinder(set_svc)
    found = await finder.find(parsed)
    if not found.exact or not found.entities:
        raise ValueError(f"Set not found: {set_ref}")
    set_id = found.entities[0].set_id

    # ... rest of existing logic using set_id ...
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_workflow_curation.py -v --tb=short
```

Expected: All pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(mcp): curation review_set uses EntityFinder refs"
```

---

## Task 11: Refactor download_tracks — use refs + envelope

**Files:**
- Modify: `app/mcp/workflows/import_tools.py`
- Modify: `tests/mcp/test_download_tools.py`

After Task 3, `import_tools.py` only has `download_tracks`. Refactor to accept `track_refs: list[str]` instead of `track_ids: list[int]`.

**Step 1: Write test**

```python
async def test_download_tracks_accepts_refs():
    """download_tracks should accept track_refs list."""
    result = await call_tool("download_tracks", {
        "track_refs": ["local:1", "local:2"],
    })
    assert "downloaded" in result or "error" in result
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_download_tools.py -v -k "ref" --tb=short
```

Expected: FAIL.

**Step 3: Update download_tracks**

```python
from app.mcp.entity_finder import TrackFinder
from app.mcp.refs import parse_ref

@mcp.tool(
    name="download_tracks",
    description="Download MP3 files for tracks from Yandex Music to iCloud library",
    tags={"download", "yandex"},
    annotations={"readonly": False},
)
async def download_tracks(
    track_refs: list[str],
    prefer_bitrate: int = 320,
    ctx: Context | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ym_client: YandexMusicClient = Depends(get_ym_client),  # noqa: B008
    track_svc: TrackService = Depends(get_track_service),  # noqa: B008
) -> DownloadResult:
    """Download tracks from Yandex Music to local library.

    Args:
        track_refs: List of track references (local:42, "track name").
        prefer_bitrate: Preferred bitrate in kbps (default: 320).
    """
    # Resolve refs → track_ids
    finder = TrackFinder(track_svc)
    track_ids: list[int] = []
    for ref_str in track_refs:
        parsed = parse_ref(ref_str)
        found = await finder.find(parsed)
        if found.exact and found.entities:
            track_ids.append(found.entities[0].track_id)

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

Note: Added `TrackService` dependency for ref resolution.

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_download_tools.py -v --tb=short
```

Expected: All pass.

**Step 5: Rename file (optional)**

Consider renaming `import_tools.py` → `download_tools.py` since it no longer has import stubs. Update `server.py` import accordingly.

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(mcp): download_tracks uses EntityFinder refs"
```

---

## Task 12: Update server.py registrations + final cleanup

**Files:**
- Modify: `app/mcp/workflows/server.py`
- Modify: `app/mcp/workflows/__init__.py` (if exists)

**Step 1: Verify current server.py state**

After Tasks 1–11, `server.py` should register:
- ~~`register_analysis_tools`~~ (removed in Task 1)
- `register_import_tools` — now only has `download_tracks`
- `register_discovery_tools` — now only has `find_similar_tracks`
- `register_setbuilder_tools` — has `build_set`, `rebuild_set`, `score_transitions`
- `register_export_tools` — has rich `export_set_m3u`, `export_set_json`, `export_set_rekordbox`
- `register_curation_tools` — has `classify_tracks`, `analyze_library_gaps`, `review_set`
- ~~`register_sync_tools`~~ (old stubs removed in Task 2, Phase 3 tools registered)
- `_register_visibility_tools` — has `activate_heavy_mode`

Update `server.py` to reflect the final state:

```python
"""DJ Workflow MCP server — high-level tools for DJ set building."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.context import Context

from app.mcp.prompts import register_prompts
from app.mcp.resources import register_resources
from app.mcp.workflows.curation_tools import register_curation_tools
from app.mcp.workflows.discovery_tools import register_discovery_tools
from app.mcp.workflows.export_tools import register_export_tools
from app.mcp.workflows.import_tools import register_import_tools
from app.mcp.workflows.setbuilder_tools import register_setbuilder_tools
# Phase 3 sync tools — use actual import path from Phase 3 implementation
# from app.mcp.sync.tools import register_sync_tools

def _register_visibility_tools(mcp: FastMCP) -> None:
    """Register admin/visibility-control tools on the MCP server."""

    @mcp.tool(tags={"admin"})
    async def activate_heavy_mode(ctx: Context) -> str:
        """Enable heavy analysis tools (full audio feature extraction)."""
        await ctx.enable_components(tags={"heavy"})
        return "Heavy analysis tools are now available."

def create_workflow_mcp() -> FastMCP:
    """Create the DJ Workflows MCP server with all tools registered."""
    mcp = FastMCP("DJ Workflows")
    register_import_tools(mcp)
    register_discovery_tools(mcp)
    register_setbuilder_tools(mcp)
    register_export_tools(mcp)
    register_curation_tools(mcp)
    # register_sync_tools(mcp)  # Phase 3 — uncomment after Phase 3 implementation
    register_prompts(mcp)
    register_resources(mcp)
    _register_visibility_tools(mcp)

    mcp.disable(tags={"heavy"})

    return mcp
```

**Step 2: Run full test suite**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: All pass.

**Step 3: Run lint + type-check**

```bash
uv run ruff check app/mcp/ tests/mcp/ && uv run ruff format --check app/mcp/ tests/mcp/
uv run mypy app/mcp/
```

Expected: Clean.

**Step 4: Verify no stale references**

```bash
rg "from app\.mcp\.types import" app/ tests/ --type py
rg "from app\.mcp\.types_curation import" app/ tests/ --type py
rg "analysis_tools" app/ tests/ --type py
rg "import_playlist|import_tracks" app/mcp/ --type py
rg "search_by_criteria" app/mcp/ --type py
```

Expected: No results for any of these.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(mcp): final server.py cleanup after Phase 4 migration"
```

---

## Task 13: Full integration test + lint verification

**Files:**
- No new files — verification only

**Step 1: Run the full project test suite**

```bash
uv run pytest -v --tb=short
```

Expected: All tests pass (~745+ tests).

**Step 2: Run full lint chain**

```bash
make lint
```

Expected: ruff check + format + mypy all clean.

**Step 3: Verify MCP tool list**

```bash
make mcp-list
```

Expected: No stubs, no duplicates. Tool list should show:
- **CRUD tools** (Phase 2): list_tracks, get_track, list_playlists, get_playlist, list_sets, get_set, etc.
- **Search** (Phase 1): search, filter_tracks
- **Orchestrators**: build_set, rebuild_set, score_transitions, download_tracks, classify_tracks, analyze_library_gaps, review_set
- **Export**: export_set_m3u, export_set_json, export_set_rekordbox (or unified export_set)
- **Sync** (Phase 3): sync_playlist, sync_set_to_ym, sync_set_from_ym, set_source_of_truth, link_playlist
- **Visibility**: activate_heavy_mode, activate_ym_raw, list_platforms
- **YM raw** (hidden): ~30 tools via from_openapi()

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore(mcp): Phase 4 complete — verify all tests + lint pass"
```

---

## Summary: Before vs After Phase 4

| Metric | Before Phase 4 | After Phase 4 |
|--------|----------------|---------------|
| Tool files in `workflows/` | 7 files | 5 files |
| Stub tools | 5 (2 import + 3 sync) | 0 |
| Duplicate tools | 2 (export_m3u, export_json) | 0 |
| Type model files | 2 (types.py + types_curation.py) | 1 (types_v2.py) |
| Dead-code types | 5 (Swap, Reorder, Adjustment, CurateCandidate, CurateSetResult) | 0 |
| Legacy analysis tools | 2 (get_playlist_status, get_track_details) | 0 |
| Legacy search tool | 1 (search_by_criteria) | 0 |
| All tools use URN refs | No | Yes |
| All tools use types_v2 | No | Yes |

### Deleted files
- `app/mcp/workflows/analysis_tools.py`
- `app/mcp/workflows/sync_tools.py` (old stubs)
- `app/mcp/types.py`
- `app/mcp/types_curation.py`
- `tests/mcp/test_workflow_analysis.py`
- `tests/mcp/test_workflow_sync.py`
- `tests/mcp/test_workflow_import.py`
- `tests/mcp/test_import_playlist.py`
