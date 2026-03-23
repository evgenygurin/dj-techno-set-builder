# MCP-First Architecture Refactoring — Design Spec

**Date**: 2026-03-23
**Branch**: `refactor/mcp-first-architecture`
**Approach**: B (Remove + Restructure MCP)

---

## 1. Problem Statement

The repository has three transport layers (REST API, Typer CLI, MCP) exposing the same domain services. REST (66 endpoints, 78 schemas) and CLI (23 commands) are fully redundant — MCP tools already cover 100% of their functionality plus 30+ additional workflows (build_set, deliver_set, sync, export, classify, etc.).

This creates:
- **78 dead schema classes** in `app/schemas/` (never used by MCP)
- **15 router files** with thin wrappers over the same services MCP calls
- **10 CLI files** duplicating MCP tools
- **Split DI**: `app/dependencies.py` (1 REST provider) vs `app/mcp/dependencies.py` (13 providers)
- **Split transaction boundaries**: routers commit vs MCP DI session commits
- **FastAPI/uvicorn/typer/rich** as unnecessary dependencies

The business logic layer (services, repositories, models, audio utils) is already transport-agnostic. The refactoring is primarily a **surface removal** + **MCP reorganization**.

---

## 2. Goals

1. Remove FastAPI/REST layer completely (routers, schemas, middleware, main.py)
2. Remove Typer CLI layer completely (app/cli/)
3. Reorganize MCP tools from 18 flat files into 6 domain-oriented providers
4. Restructure `app/` into cleaner `core/infrastructure/services/audio/mcp` hierarchy
5. Remove FastAPI/uvicorn/typer/rich from core dependencies
6. Move Sentry initialization from `app/main.py` to `app/mcp/observability.py`
7. Update tests to remove REST/CLI tests, keep domain + MCP tests
8. Update docs, Makefile, pyproject.toml, CLAUDE.md

---

## 3. Target Architecture

### 3.1 Directory Structure

```bash
app/
├── _compat.py                    # TypeForm patch (unchanged)
├── __init__.py                   # Applies compat patch
│
├── core/                         # Domain fundamentals
│   ├── __init__.py
│   ├── config.py                 # ← app/config.py (remove FastAPI settings)
│   ├── errors.py                 # ← app/errors.py (unchanged)
│   ├── text_sort.py              # ← app/utils/text_sort.py
│   └── models/                   # ← app/models/ (unchanged, 20 files)
│       ├── __init__.py
│       ├── base.py
│       ├── catalog.py
│       ├── features.py
│       ├── sets.py
│       ├── dj.py
│       ├── transitions.py
│       ├── sections.py
│       ├── harmony.py
│       ├── runs.py
│       ├── enums.py
│       ├── ingestion.py
│       ├── providers.py
│       ├── assets.py
│       ├── timeseries.py
│       ├── embeddings.py
│       ├── metadata_yandex.py
│       ├── metadata_spotify.py
│       ├── metadata_soundcloud.py
│       └── metadata_beatport.py
│
├── infrastructure/               # Persistence + external services
│   ├── __init__.py
│   ├── database.py               # ← app/database.py (unchanged)
│   ├── repositories/             # ← app/repositories/ (22 files)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── tracks.py
│   │   ├── artists.py
│   │   ├── genres.py
│   │   ├── keys.py               # Was missing in v1 spec
│   │   ├── labels.py
│   │   ├── releases.py
│   │   ├── playlists.py
│   │   ├── sets.py
│   │   ├── audio_features.py
│   │   ├── sections.py
│   │   ├── runs.py
│   │   ├── transitions.py
│   │   ├── candidates.py
│   │   ├── harmony.py
│   │   ├── yandex_metadata.py
│   │   ├── providers.py
│   │   ├── dj_library_items.py
│   │   ├── dj_beatgrid.py
│   │   ├── dj_cue_points.py
│   │   └── dj_saved_loops.py
│   └── clients/                  # ← app/clients/ (unchanged)
│       ├── __init__.py
│       └── yandex_music.py
│
├── services/                     # ← app/services/ (29 files, unchanged logic)
│   ├── __init__.py
│   ├── base.py
│   ├── tracks.py
│   ├── artists.py
│   ├── genres.py
│   ├── labels.py
│   ├── releases.py
│   ├── keys.py
│   ├── playlists.py
│   ├── sets.py
│   ├── features.py
│   ├── sections.py
│   ├── track_analysis.py
│   ├── analysis.py               # (NOT analysis_orchestrator.py)
│   ├── set_generation.py
│   ├── set_curation.py
│   ├── transition_scoring.py
│   ├── transition_scoring_unified.py  # (NOT unified_transition_scoring.py)
│   ├── transition_persistence.py
│   ├── transition_type.py
│   ├── transitions.py
│   ├── camelot_lookup.py
│   ├── mix_points.py
│   ├── set_export.py
│   ├── rekordbox_types.py
│   ├── download.py
│   ├── import_yandex.py
│   ├── runs.py                   # (single file, NOT feature_runs + transition_runs)
│   ├── yandex_music_enrichment.py  # (NOT yandex_enrichment.py)
│   └── yandex_music_client.py    # Service-level YM client wrapper
│
├── audio/                        # ← app/utils/audio/ (promoted to top-level)
│   ├── __init__.py
│   ├── _types.py
│   ├── _errors.py
│   ├── loader.py
│   ├── bpm.py
│   ├── key_detect.py
│   ├── loudness.py
│   ├── energy.py
│   ├── spectral.py
│   ├── beats.py
│   ├── groove.py
│   ├── structure.py
│   ├── stems.py
│   ├── camelot.py
│   ├── transition_score.py
│   ├── set_generator.py
│   ├── mfcc.py
│   ├── pipeline.py
│   ├── mood_classifier.py
│   ├── set_templates.py
│   ├── greedy_chain.py
│   └── feature_conversion.py
│
└── mcp/                          # MCP layer (restructured)
    ├── __init__.py               # re-exports create_dj_mcp
    ├── gateway.py                # Compose providers + mount YM + transforms
    ├── dependencies.py           # DI providers (unchanged, 13 providers)
    ├── observability.py          # Caching, OTEL, Sentry init (← from app/main.py)
    ├── lifespan.py               # MCP lifespan management
    ├── session_state.py          # Ephemeral session storage
    ├── elicitation.py            # Human-in-loop helpers
    │
    ├── providers/                # NEW: domain-grouped tool registration
    │   ├── __init__.py
    │   ├── _scoring_helpers.py   # ← tools/_scoring_helpers.py (shared helper)
    │   ├── catalog.py            # ← tools/track.py + tools/playlist.py + tools/set.py + tools/features.py
    │   ├── analysis.py           # ← tools/compute.py + tools/curation.py
    │   ├── setbuilder.py         # ← tools/setbuilder.py + tools/delivery.py
    │   ├── sync.py               # ← tools/sync.py
    │   ├── discovery.py          # ← tools/search.py + tools/discovery.py + tools/curation_discovery.py + tools/download.py
    │   ├── export.py             # ← tools/export.py + tools/unified_export.py
    │   └── admin.py              # ← tools/server.py visibility tools (activate_heavy_mode, activate_ym_raw, list_platforms)
    │
    ├── tools/                    # REMOVED after migration to providers/
    │
    ├── types/                    # Pydantic response models (unchanged)
    │   ├── __init__.py
    │   ├── entities.py
    │   ├── responses.py
    │   ├── workflows.py
    │   └── curation.py
    │
    ├── converters.py             # ORM → Pydantic helpers
    ├── entity_finder.py          # Fuzzy entity resolution
    ├── pagination.py             # Cursor-based pagination
    ├── refs.py                   # Reference parsing
    ├── resolve.py                # Ref → local ID
    ├── response.py               # Response wrapping
    ├── library_stats.py          # Catalog metrics
    │
    ├── prompts/                  # Workflow recipe prompts (unchanged)
    │   └── workflows.py
    ├── resources/                # Read-only resources (unchanged)
    │   └── status.py
    ├── skills/                   # MCP skills (unchanged)
    │   ├── build-set-from-scratch/
    │   ├── expand-playlist/
    │   └── improve-set/
    ├── platforms/                # Platform abstraction (unchanged)
    │   ├── __init__.py
    │   ├── factory.py            # Was missing in v1 spec
    │   ├── protocol.py
    │   ├── registry.py
    │   └── yandex.py
    ├── sync/                     # Sync engine (unchanged)
    │   ├── diff.py
    │   ├── engine.py
    │   └── track_mapper.py
    └── yandex_music/             # OpenAPI YM tools (unchanged)
        ├── __init__.py
        ├── server.py
        ├── config.py
        └── response_filters.py
```

### 3.2 Provider Consolidation Map

Current 18 tool files → 7 provider files:

| Provider | Source files | Tools | Domain |
|----------|------------|-------|--------|
| `catalog.py` | track.py, playlist.py, set.py, features.py | ~22 | CRUD for all entities |
| `analysis.py` | compute.py, curation.py | ~8 | Audio analysis, classification, library gaps |
| `setbuilder.py` | setbuilder.py, delivery.py | ~6 | Build, rebuild, score, deliver |
| `sync.py` | sync.py | ~8 | Platform sync, link, source-of-truth |
| `discovery.py` | search.py, discovery.py, curation_discovery.py, download.py | ~7 | Search, filter, discover, expand, download |
| `export.py` | export.py, unified_export.py | ~2 | M3U, JSON, Rekordbox export |
| `admin.py` | server.py (_register_visibility_tools) | 3 | activate_heavy_mode, activate_ym_raw, list_platforms |

Shared: `_scoring_helpers.py` moves to `providers/_scoring_helpers.py`.

Total: ~56 tools (same count, better organization).

### 3.3 Gateway Changes

**CRITICAL**: The current gateway mounts the workflow sub-server with namespace `"dj"`, which prefixes all tool names with `dj_`. This prefix is referenced by:
- All 4 prompts in `prompts/workflows.py`
- `.mcp.json` client configuration
- Claude Code usage patterns
- All MCP tests asserting tool names

**Decision**: Keep the namespace mounting pattern. The gateway still creates an intermediate workflow server and mounts it at namespace `"dj"`. The only change is that the workflow server's internal tool registration uses the new provider modules instead of the old tool modules.

```python
def create_dj_mcp() -> FastMCP:
    mcp = FastMCP("DJ Set Builder", ...)

    # Sentry/OTEL initialization (moved from app/main.py)
    init_observability()

    # Create workflow sub-server (preserves dj_ namespace prefix)
    wf = create_workflow_mcp()  # Uses new providers/ internally
    mcp.mount("dj", wf)

    # Mount YM sub-server (preserves ym_ namespace prefix)
    ym = create_yandex_music_mcp()
    mcp.mount("ym", ym)

    # Skills directory
    mcp.add_provider(SkillsDirectoryProvider(skills_dir))

    # Transforms + observability middleware
    apply_observability_middleware(mcp)
    mcp.add_tool_transform(PromptsAsTools())
    mcp.add_tool_transform(ResourcesAsTools())

    return mcp
```

`create_workflow_mcp()` in `providers/__init__.py`:
```python
def create_workflow_mcp() -> FastMCP:
    wf = FastMCP("DJ Workflows")
    register_catalog_tools(wf)
    register_analysis_tools(wf)
    register_setbuilder_tools(wf)
    register_sync_tools(wf)
    register_discovery_tools(wf)
    register_export_tools(wf)
    register_admin_tools(wf)
    register_prompts(wf)
    register_resources(wf)
    wf.disable(tags={"heavy"})
    return wf
```

### 3.4 Import Path Migration

All internal imports change from `app.X` to `app.core.X`, `app.infrastructure.X`, etc.

| Old | New |
|-----|-----|
| `from app.models import Track` | `from app.core.models import Track` |
| `from app.models.base import Base` | `from app.core.models.base import Base` |
| `from app.repositories.tracks import TrackRepository` | `from app.infrastructure.repositories.tracks import TrackRepository` |
| `from app.repositories.keys import KeyRepository` | `from app.infrastructure.repositories.keys import KeyRepository` |
| `from app.database import session_factory` | `from app.infrastructure.database import session_factory` |
| `from app.config import settings` | `from app.core.config import settings` |
| `from app.errors import NotFoundError` | `from app.core.errors import NotFoundError` |
| `from app.services.tracks import TrackService` | `from app.services.tracks import TrackService` |
| `from app.utils.audio.bpm import detect_bpm` | `from app.audio.bpm import detect_bpm` |
| `from app.utils.text_sort import sort_key` | `from app.core.text_sort import sort_key` |
| `from app.clients.yandex_music import YandexMusicClient` | `from app.infrastructure.clients.yandex_music import YandexMusicClient` |

### 3.5 Compatibility Shims

Temporary re-export modules at old paths to avoid breaking `scripts/`:

| Shim file | Re-exports from |
|-----------|----------------|
| `app/config.py` | `from app.core.config import *` |
| `app/database.py` | `from app.infrastructure.database import *` |
| `app/errors.py` | `from app.core.errors import *` |
| `app/models/__init__.py` | `from app.core.models import *` |
| `app/repositories/__init__.py` | `from app.infrastructure.repositories import *` |
| `app/utils/audio/__init__.py` | `from app.audio import *` |

Shims will be removed in a follow-up PR after scripts are updated.

### 3.6 Sentry/OTEL Initialization

Currently `_init_sentry()` lives in `app/main.py` and runs at module import time. After deleting `main.py`:
- Move to `app/mcp/observability.py` as `init_observability()`
- Called from `create_dj_mcp()` in gateway.py (before any tool registration)
- Covers both Sentry SDK init and OTEL TracerProvider setup

---

## 4. What Gets Deleted

### 4.1 Files

| Path | Files | Lines | Reason |
|------|-------|-------|--------|
| `app/routers/` (incl v1/) | 19 | ~1700 | 100% covered by MCP tools |
| `app/schemas/` | 22 | ~840 | REST-only Pydantic models |
| `app/cli/` | 10 | ~1730 | 100% covered by MCP tools |
| `app/middleware/` | 3 | ~25 | RequestIdMiddleware — REST-only |
| `app/main.py` | 1 | ~90 | FastAPI app factory (Sentry init moves to observability.py) |
| `app/dependencies.py` | 1 | ~15 | REST DI (1 provider) |
| `tests/cli/` | 10 | ~800 | CLI tests |
| `tests/test_tracks.py` | 1 | ~200 | REST endpoint tests |
| `tests/test_health.py` | 1 | ~20 | REST health check |
| `tests/test_sections_api.py` | 1 | ~80 | REST endpoint tests |
| `tests/test_features_api.py` | 1 | ~80 | REST endpoint tests |
| `tests/test_analysis_api.py` | 1 | ~100 | REST endpoint tests |
| `tests/test_batch_analysis_api.py` | 1 | ~100 | REST endpoint tests |
| `tests/test_imports_api.py` | 1 | ~100 | REST endpoint tests |
| `tests/test_candidates.py` | 1 | ~80 | REST endpoint tests (imports from app.schemas) |
| `tests/test_schemas_imports.py` | 1 | ~50 | Tests REST schemas (imports from app.schemas.imports) |
| `tests/test_schemas_ym.py` | 1 | ~50 | Tests REST schemas (imports from app.schemas.yandex_music) |
| `tests/test_set_generation.py` | 1 | ~100 | Uses AsyncClient |
| `tests/test_sentry_init.py` | 1 | ~30 | Tests app.main Sentry init (needs rewrite for new location) |

**Total deleted**: ~60 files, ~6300 lines

### 4.2 Dependencies Changes in pyproject.toml

**Remove from core dependencies:**

| Package | Reason |
|---------|--------|
| `fastapi` | No HTTP app |
| `typer` | No CLI |

**Move to dev/optional dependencies:**

| Package | Reason |
|---------|--------|
| `uvicorn[standard]` | Only needed for `make mcp-dev` (FastMCP HTTP transport) |
| `starlette` | Transitive dep of FastMCP for HTTP transport |

**Keep in core:**

| Package | Reason |
|---------|--------|
| `httpx` | YM client + MCP tests |
| `pydantic` | MCP types + ORM models |
| `rich` | Review: check if FastMCP uses it; if not, remove |

### 4.3 Makefile Targets

| Target | Action |
|--------|--------|
| `make run` | Remove (was `uvicorn app.main:app`) |
| `make mcp-dev` | Keep (FastMCP dev server) |
| `make mcp-inspect` | Keep |
| `make mcp-call` | Keep |
| `make mcp-list` | Keep |
| `make test` | Keep |
| `make lint` | Keep |
| `make coverage` | Keep |
| `make db-schema` | Keep |

### 4.4 pyproject.toml Scripts

Remove: `[project.scripts] dj = "app.cli.main:app"`

---

## 5. What Gets Preserved (unchanged logic)

| Layer | Files | Why |
|-------|-------|-----|
| `app/services/` (29 files) | All business logic | Transport-agnostic, called by MCP DI |
| `app/repositories/` (22 files) | All persistence | Transport-agnostic |
| `app/models/` (20 files, 44 ORM models) | All domain models | No transport coupling |
| `app/utils/audio/` (22 files) | Pure functions | No transport coupling |
| `app/clients/yandex_music.py` | YM HTTP client | Used by services |
| `app/mcp/dependencies.py` (13 providers) | MCP DI | Already complete |
| `app/mcp/types/` (37 Pydantic models) | MCP response types | Already complete |
| `app/mcp/prompts/` (4 recipes) | Workflow prompts | Already complete |
| `app/mcp/resources/` (3 resources) | Read-only resources | Already complete |
| `app/mcp/skills/` (3 skills) | MCP skills | Already complete |
| `app/mcp/yandex_music/` (4 files incl response_filters.py) | OpenAPI → FastMCP | Already complete |
| `app/mcp/platforms/` (5 files incl factory.py) | Platform abstraction | Already complete |
| `app/mcp/sync/` (3 files) | Sync engine | Already complete |
| `scripts/` | Batch operations | Unique logic not in MCP |
| `tests/mcp/` (~49 files) | MCP tests | Primary test suite |
| `tests/utils/` (25 files) | Audio util tests | Pure function tests |
| `tests/services/` (16 files) | Service unit tests | Transport-agnostic |
| `migrations/` | Alembic migrations | DB schema management |

---

## 6. Test Impact

### Tests to DELETE

**REST API tests** (files importing AsyncClient/ASGITransport or testing REST endpoints):
- `tests/test_tracks.py`
- `tests/test_health.py`
- `tests/test_sections_api.py`
- `tests/test_features_api.py`
- `tests/test_analysis_api.py`
- `tests/test_batch_analysis_api.py`
- `tests/test_imports_api.py`
- `tests/test_candidates.py`
- `tests/test_set_generation.py`
- `tests/test_schemas_imports.py` (imports from deleted app.schemas.imports)
- `tests/test_schemas_ym.py` (imports from deleted app.schemas.yandex_music)

**CLI tests** (entire directory):
- `tests/cli/` (10 files: conftest, test_context, test_delivery, test_formatting, test_main, test_playlists, test_setbuilder, test_sets, test_tracks)

**Sentry test** (needs rewrite, not just delete):
- `tests/test_sentry_init.py` — rewrite to test `init_observability()` in new location

### Tests to UPDATE (import paths)

All remaining tests need import path updates:
- `from app.models import X` → `from app.core.models import X`
- `from app.repositories.X import Y` → `from app.infrastructure.repositories.X import Y`
- `from app.database import X` → `from app.infrastructure.database import X`
- `from app.config import X` → `from app.core.config import X`
- `from app.errors import X` → `from app.core.errors import X`
- `from app.utils.audio.X import Y` → `from app.audio.X import Y`
- `from app.clients.X import Y` → `from app.infrastructure.clients.X import Y`

### MCP test fixture patch paths

`tests/mcp/conftest.py` patches `app.mcp.dependencies.session_factory`. The `session_factory` is imported from `app.database` inside `dependencies.py`. After moving to `app.infrastructure.database`, the patch target in `workflow_mcp_with_db` may need updating to `app.mcp.dependencies.session_factory` (which should still work if `dependencies.py` imports from the new path).

### conftest.py Changes (CRITICAL ORDERING)

`tests/conftest.py` currently imports `create_app` from `app.main` and `get_session` from `app.dependencies` for the `client` fixture. These imports will fail at **collection time** after deletion, breaking ALL tests.

**Fix**: Update `conftest.py` BEFORE or SIMULTANEOUSLY with deleting `app/main.py` and `app/dependencies.py`:
- Remove `client` fixture entirely
- Remove imports of `create_app`, `get_session` from deleted modules
- Keep `engine` and `session` fixtures (used by service/repo/MCP tests)
- Update remaining imports to new paths

---

## 7. Migration Sequence (rollback-safe order)

### Phase 1: Create new directory structure (additive only)
1. Create `app/core/`, `app/infrastructure/`, `app/audio/`
2. `git mv` files to preserve history
3. Add `__init__.py` re-exports at new paths
4. Add compatibility shims at old paths (Section 3.5)
5. Move `_init_sentry()` to `app/mcp/observability.py`
6. Run `make check` — everything must pass with both old and new paths working

### Phase 2: Update all imports
1. Bulk update imports across all Python files (app/, tests/, scripts/)
2. Update `tests/conftest.py` — remove `client` fixture and REST imports
3. Run `make lint` to verify
4. Run `make test` to verify

### Phase 3: Consolidate MCP providers
1. Create `app/mcp/providers/` with 7 provider files + `_scoring_helpers.py`
2. Move tool functions from 18 tool files → 7 providers
3. Update `create_workflow_mcp()` to use new providers
4. Keep gateway namespace mounting (`mcp.mount("dj", wf)`) — tool names unchanged
5. Run MCP tests to verify all tools still registered with correct names

### Phase 4: Remove REST/CLI layers
1. Delete `app/routers/`, `app/schemas/`, `app/cli/`, `app/middleware/`
2. Delete `app/main.py`, `app/dependencies.py`
3. Delete `app/mcp/tools/` (old tool files, now in providers/)
4. Delete REST + CLI test files (Section 6)
5. Rewrite `tests/test_sentry_init.py` for new observability location
6. Run `make check`

### Phase 5: Clean up dependencies and config
1. Remove `fastapi`, `typer` from core dependencies in pyproject.toml
2. Move `uvicorn` to dev/optional dependencies
3. Remove `[project.scripts]` CLI entrypoint
4. Update Makefile (remove `make run`)
5. Verify `fastmcp.json` source path still correct (`app/mcp/gateway.py:create_dj_mcp`)
6. Run `uv sync && make check`

### Phase 6: Remove compatibility shims
1. Update `scripts/` imports to use new paths directly
2. Remove shim files (Section 3.5)
3. Remove old empty directories (`app/utils/`, etc.)
4. Run `make check`

### Phase 7: Update documentation
1. Rewrite CLAUDE.md architecture section
2. Update `.claude/rules/api.md` (remove REST references)
3. Update `.claude/rules/mcp.md` (new provider structure)
4. Update `.claude/rules/testing.md` (remove REST test info)
5. Update `.claude/rules/documentation.md` if needed
6. Update CHANGELOG.md

---

## 8. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Import path breakage | Medium | Phase 1 adds shims; Phase 2 updates all; `make test` gates each step |
| MCP tool regression | Low | Tool functions just move files; names preserved via namespace mount |
| `dj_` prefix loss | **Eliminated** | Gateway keeps `mcp.mount("dj", wf)` pattern (Section 3.3) |
| Script breakage | Medium | Compatibility shims (Section 3.5) cover transition; Phase 6 removes them |
| FastMCP transitive deps | Low | `uvicorn`/`starlette` moved to dev deps; `make mcp-dev` still works |
| Test collection failure | **High if misordered** | conftest.py updated BEFORE `app/main.py` deletion (Section 6, Phase 2) |
| Sentry init gap | Low | Moved to `observability.py`, called from gateway before tool registration |
| MCP test fixture patches | Medium | Verify `workflow_mcp_with_db` patch target after import path changes |

---

## 9. Decisions Record

| Decision | Rationale |
|----------|-----------|
| Delete REST completely | No external consumers; 100% covered by MCP |
| Delete CLI completely | 100% covered by MCP; scripts/ kept for batch ops |
| Keep scripts/ | Unique batch logic (fill_and_verify, refresh_data, rescore_sets) |
| 7 MCP providers (6 domain + 1 admin) | Matches domain boundaries; admin tools separate from domain |
| Keep `dj_` namespace prefix | Avoids breaking all prompts, tests, and client usage patterns |
| Move models to core/ | Models are domain fundamentals, not infrastructure |
| Move repos to infrastructure/ | Repos are persistence implementation detail |
| Keep services at top level | Services are the primary API; short import path matters |
| Promote audio/ to top level | Audio utils are a distinct domain, not a generic utility |
| Move text_sort.py to core/ | Utility used across domains, not audio-specific |
| Compatibility shims during migration | Allows incremental migration; removed in Phase 6 |
| Delete REST tests | No value without REST layer |
| Delete CLI tests | No value without CLI layer |
| Rewrite sentry test | Test still valuable but needs new import path |
| uvicorn to dev deps | Only needed for `make mcp-dev` HTTP transport |
