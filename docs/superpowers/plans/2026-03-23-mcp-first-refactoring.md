# MCP-First Architecture Refactoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the repository from a multi-transport app (REST + CLI + MCP) into an MCP-first architecture by removing redundant layers and restructuring into clean domain boundaries.

**Architecture:** Remove FastAPI/REST (19 router files, 22 schema files) and Typer CLI (10 files). Restructure `app/` into `core/` (models, config, errors), `infrastructure/` (repos, DB, clients), `services/` (unchanged), `audio/` (promoted from utils), and `mcp/` (tools consolidated into 7 domain providers). MCP namespace mounting preserved to keep `dj_` prefix on all tool names.

**Tech Stack:** Python 3.12, FastMCP 3.0, SQLAlchemy 2.0 async, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-mcp-first-refactoring-design.md`

---

## File Structure

### New directories to create
- `app/core/` — config, errors, text_sort, models/
- `app/infrastructure/` — database, repositories/, clients/
- `app/audio/` — promoted from app/utils/audio/
- `app/mcp/providers/` — 7 domain provider files replacing 18 tool files

### Directories to delete
- `app/routers/` (19 files, ~1700 lines)
- `app/schemas/` (22 files, ~840 lines)
- `app/cli/` (10 files, ~1730 lines)
- `app/middleware/` (3 files, ~25 lines)
- `app/mcp/tools/` (18 files — after migration to providers/)
- `tests/cli/` (10 files)

### Files to delete
- `app/main.py`, `app/dependencies.py`
- ~15 REST/schema test files
- `tests/test_sentry_init.py` (rewrite for new location)

---

## Task 1: Create directory structure and move core files

**Files:**
- Create: `app/core/__init__.py`, `app/core/models/__init__.py`
- Move: `app/config.py` → `app/core/config.py`
- Move: `app/errors.py` → `app/core/errors.py`
- Move: `app/utils/text_sort.py` → `app/core/text_sort.py`
- Move: `app/models/*` → `app/core/models/*`

- [ ] **Step 1: Create core directory and __init__.py files**

```bash
mkdir -p app/core/models
touch app/core/__init__.py
```

- [ ] **Step 2: Move config, errors, text_sort to core/**

```bash
git mv app/config.py app/core/config.py
git mv app/errors.py app/core/errors.py
git mv app/utils/text_sort.py app/core/text_sort.py
```

- [ ] **Step 3: Move all model files to core/models/**

```bash
git mv app/models/__init__.py app/core/models/__init__.py
git mv app/models/base.py app/core/models/base.py
git mv app/models/catalog.py app/core/models/catalog.py
# ... repeat for all 20 model files
```

Use: `for f in app/models/*.py; do git mv "$f" "app/core/models/$(basename $f)"; done`

- [ ] **Step 4: Create compatibility shims at old paths**

Create `app/config.py`:
```python
"""Compatibility shim — import from app.core.config instead."""
from app.core.config import *  # noqa: F401,F403
from app.core.config import settings  # noqa: F401 — explicit re-export
```

Create `app/errors.py`:
```python
"""Compatibility shim — import from app.core.errors instead."""
from app.core.errors import *  # noqa: F401,F403
```

Create `app/models/__init__.py` (new empty dir + shim):
```python
"""Compatibility shim — import from app.core.models instead."""
from app.core.models import *  # noqa: F401,F403
from app.core.models import Base  # noqa: F401 — critical re-export
```

Also shim `app/models/base.py`:
```python
"""Compatibility shim."""
from app.core.models.base import *  # noqa: F401,F403
```

And shim each model submodule that is imported directly (catalog, features, sets, dj, enums, etc.).

- [ ] **Step 5: Run tests to verify shims work**

Run: `uv run pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: All tests pass (shims transparently redirect imports)

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor(core): move config, errors, models to app/core/"
```

---

## Task 2: Create infrastructure directory and move repos/DB/clients

**Files:**
- Create: `app/infrastructure/__init__.py`, `app/infrastructure/repositories/__init__.py`, `app/infrastructure/clients/__init__.py`
- Move: `app/database.py` → `app/infrastructure/database.py`
- Move: `app/repositories/*` → `app/infrastructure/repositories/*`
- Move: `app/clients/*` → `app/infrastructure/clients/*`

- [ ] **Step 1: Create infrastructure directories**

```bash
mkdir -p app/infrastructure/repositories app/infrastructure/clients
touch app/infrastructure/__init__.py
```

- [ ] **Step 2: Move database.py**

```bash
git mv app/database.py app/infrastructure/database.py
```

- [ ] **Step 3: Move all repository files**

```bash
for f in app/repositories/*.py; do git mv "$f" "app/infrastructure/repositories/$(basename $f)"; done
```

- [ ] **Step 4: Move client files**

```bash
for f in app/clients/*.py; do git mv "$f" "app/infrastructure/clients/$(basename $f)"; done
```

- [ ] **Step 5: Create compatibility shims**

Create `app/database.py`:
```python
"""Compatibility shim — import from app.infrastructure.database instead."""
from app.infrastructure.database import *  # noqa: F401,F403
from app.infrastructure.database import (  # noqa: F401
    engine,
    get_session,
    init_db,
    session_factory,
)
```

Create `app/repositories/__init__.py` (new empty dir + init):
```python
"""Compatibility shim — import from app.infrastructure.repositories instead."""
from app.infrastructure.repositories import *  # noqa: F401,F403
```

And shims for commonly-imported repo submodules.

Create `app/clients/__init__.py`:
```python
"""Compatibility shim."""
from app.infrastructure.clients import *  # noqa: F401,F403
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "refactor(infra): move database, repositories, clients to app/infrastructure/"
```

---

## Task 3: Promote audio utils to top-level app/audio/

**Files:**
- Move: `app/utils/audio/*` → `app/audio/*`
- Create: shim at `app/utils/audio/__init__.py`

- [ ] **Step 1: Move audio files**

```bash
mkdir -p app/audio
for f in app/utils/audio/*.py; do git mv "$f" "app/audio/$(basename $f)"; done
```

- [ ] **Step 2: Create compatibility shim**

Create `app/utils/audio/__init__.py`:
```python
"""Compatibility shim — import from app.audio instead."""
from app.audio import *  # noqa: F401,F403
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/utils/ -x -q --tb=short 2>&1 | tail -20`
Expected: All audio tests pass

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor(audio): promote app/utils/audio/ to app/audio/"
```

---

## Task 4: Bulk-update all imports to new paths

**Files:**
- Modify: ~300+ import statements across app/, tests/, scripts/

This is the largest mechanical change. Use `sed` or a script to bulk-replace.

- [ ] **Step 1: Update imports in app/ (services, mcp, etc.)**

Priority import replacements (order matters — longest match first):

```bash
# Core
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.models\.base/from app.core.models.base/g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.models\./from app.core.models./g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.models import/from app.core.models import/g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.config/from app.core.config/g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.errors/from app.core.errors/g' {} +

# Infrastructure
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.repositories\./from app.infrastructure.repositories./g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.repositories import/from app.infrastructure.repositories import/g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.database/from app.infrastructure.database/g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.clients\./from app.infrastructure.clients./g' {} +

# Audio
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.utils\.audio\./from app.audio./g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.utils\.audio import/from app.audio import/g' {} +
find app/ -name "*.py" -exec sed -i '' \
  's/from app\.utils\.text_sort/from app.core.text_sort/g' {} +
```

**IMPORTANT**: Do NOT replace imports inside the shim files themselves. Exclude `app/config.py`, `app/errors.py`, `app/database.py`, `app/models/`, `app/repositories/`, `app/clients/`, `app/utils/`.

- [ ] **Step 2: Update imports in tests/**

Same sed commands but targeting `tests/` directory. Exclude files that will be deleted in Task 6.

- [ ] **Step 3: Update imports in scripts/**

Same sed commands but targeting `scripts/` directory.

- [ ] **Step 4: Fix any remaining import issues**

Run: `uv run ruff check app/ tests/ scripts/ --select E402,F401,F811 2>&1 | head -30`
Fix any broken imports manually.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q --tb=short 2>&1 | tail -30`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor: bulk-update import paths to new structure"
```

---

## Task 5: Move Sentry/OTEL init to observability.py

**Files:**
- Modify: `app/mcp/observability.py`
- Modify: `app/mcp/gateway.py`

- [ ] **Step 1: Extract `_init_sentry()` from app/main.py to observability.py**

Read current `app/main.py` lines 16-49 to get the exact Sentry init code.
Add `init_observability()` function to `app/mcp/observability.py`.

- [ ] **Step 2: Call init_observability() from gateway.py**

Add call at the top of `create_dj_mcp()` before any tool registration.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -x -q --tb=short 2>&1 | tail -20`

- [ ] **Step 4: Commit**

```bash
git add app/mcp/observability.py app/mcp/gateway.py && git commit -m "refactor(mcp): move Sentry/OTEL init to observability.py"
```

---

## Task 6: Consolidate MCP tools into domain providers

**Files:**
- Create: `app/mcp/providers/__init__.py` with `create_workflow_mcp()`
- Create: `app/mcp/providers/catalog.py` ← tools/track.py + tools/playlist.py + tools/set.py + tools/features.py
- Create: `app/mcp/providers/analysis.py` ← tools/compute.py + tools/curation.py
- Create: `app/mcp/providers/setbuilder.py` ← tools/setbuilder.py + tools/delivery.py
- Create: `app/mcp/providers/sync.py` ← tools/sync.py
- Create: `app/mcp/providers/discovery.py` ← tools/search.py + tools/discovery.py + tools/curation_discovery.py + tools/download.py
- Create: `app/mcp/providers/export.py` ← tools/export.py + tools/unified_export.py
- Create: `app/mcp/providers/admin.py` ← tools/server.py visibility tools
- Move: `app/mcp/tools/_scoring_helpers.py` → `app/mcp/providers/_scoring_helpers.py`
- Modify: `app/mcp/gateway.py` to use providers

This is a large task. Each provider file consolidates multiple tool modules. The tool functions themselves stay identical — only the file locations change.

- [ ] **Step 1: Create providers/ directory**

```bash
mkdir -p app/mcp/providers
touch app/mcp/providers/__init__.py
```

- [ ] **Step 2: Create each provider file**

For each provider, concatenate the `register_*_tools()` functions from source files into one `register_<domain>_tools(mcp)` function. Keep all imports, all `@mcp.tool()` decorators, all function bodies unchanged.

Example for `catalog.py`:
```python
"""Catalog provider — CRUD tools for tracks, playlists, sets, features."""
from __future__ import annotations
# ... merge imports from track.py, playlist.py, set.py, features.py ...

def register_catalog_tools(mcp: FastMCP) -> None:
    # All @mcp.tool() functions from track.py
    # All @mcp.tool() functions from playlist.py
    # All @mcp.tool() functions from set.py
    # All @mcp.tool() functions from features.py
    ...
```

- [ ] **Step 3: Move _scoring_helpers.py**

```bash
git mv app/mcp/tools/_scoring_helpers.py app/mcp/providers/_scoring_helpers.py
```

- [ ] **Step 4: Create providers/__init__.py with create_workflow_mcp()**

```python
"""MCP workflow providers — domain-grouped tool registration."""
from __future__ import annotations
from fastmcp import FastMCP
from .catalog import register_catalog_tools
from .analysis import register_analysis_tools
from .setbuilder import register_setbuilder_tools
from .sync import register_sync_tools
from .discovery import register_discovery_tools
from .export import register_export_tools
from .admin import register_admin_tools

def create_workflow_mcp() -> FastMCP:
    wf = FastMCP("DJ Workflows")
    register_catalog_tools(wf)
    register_analysis_tools(wf)
    register_setbuilder_tools(wf)
    register_sync_tools(wf)
    register_discovery_tools(wf)
    register_export_tools(wf)
    register_admin_tools(wf)
    # Register prompts and resources on the workflow server
    from app.mcp.prompts.workflows import register_prompts
    from app.mcp.resources.status import register_resources
    register_prompts(wf)
    register_resources(wf)
    wf.disable(tags={"heavy"})
    return wf
```

- [ ] **Step 5: Update gateway.py**

Replace current `create_workflow_mcp` import and usage:
```python
from app.mcp.providers import create_workflow_mcp
```

Keep `mcp.mount("dj", wf)` — this preserves the `dj_` prefix on all tool names.

- [ ] **Step 6: Run MCP tests to verify all tools registered**

Run: `uv run pytest tests/mcp/ -x -q --tb=short 2>&1 | tail -20`
Expected: All MCP tests pass, tool names unchanged (still `dj_*` prefixed)

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "refactor(mcp): consolidate 18 tool files into 7 domain providers"
```

---

## Task 7: Delete REST/CLI layers and their tests

**Files to delete:**
- `app/routers/` (entire directory)
- `app/schemas/` (entire directory)
- `app/cli/` (entire directory)
- `app/middleware/` (entire directory)
- `app/main.py`
- `app/dependencies.py`
- `app/mcp/tools/` (old tool files, now in providers/)
- `tests/cli/` (entire directory)
- REST test files (see list below)

- [ ] **Step 1: Update tests/conftest.py FIRST (critical ordering)**

Remove `client` fixture and REST-specific imports:
```python
# REMOVE these imports:
# from httpx import ASGITransport, AsyncClient
# from app.main import create_app
# from app.dependencies import get_session  (if present)

# REMOVE the entire `client` fixture

# KEEP engine, session, _connection, seed_providers fixtures
# UPDATE their imports to new paths (app.core.models, app.infrastructure.database)
```

- [ ] **Step 2: Fix service tests that import from app.schemas**

4 service test files import REST schemas as DTOs:
- `tests/services/test_analysis_service.py` — uses `AnalysisRequest`
- `tests/services/test_playlists_service.py` — uses playlist schemas
- `tests/services/test_tracks_service.py` — uses track schemas
- `tests/services/test_set_generation.py` — uses set generation schemas

Replace REST schema imports with direct dict/model construction. These services accept Pydantic models or keyword args — pass those directly instead of REST schema objects.

- [ ] **Step 3: Delete REST/CLI/old-tools directories**

```bash
rm -rf app/routers app/schemas app/cli app/middleware app/mcp/tools
rm -f app/main.py app/dependencies.py
```

- [ ] **Step 4: Delete REST and CLI test files**

```bash
rm -rf tests/cli
rm -f tests/test_tracks.py tests/test_health.py tests/test_set_generation.py
rm -f tests/test_sections_api.py tests/test_features_api.py
rm -f tests/test_analysis_api.py tests/test_batch_analysis_api.py
rm -f tests/test_imports_api.py tests/test_candidates.py
rm -f tests/test_schemas_imports.py tests/test_schemas_ym.py
rm -f tests/test_sentry_init.py
rm -f tests/test_runs.py
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q --tb=short 2>&1 | tail -30`
Expected: All remaining tests pass. Fix any broken imports.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor: remove FastAPI/REST, CLI, and old MCP tool files"
```

---

## Task 8: Clean up dependencies and project config

**Files:**
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Verify: `fastmcp.json`

- [ ] **Step 1: Remove FastAPI/typer from pyproject.toml dependencies**

Remove from `[project.dependencies]`:
- `fastapi` (and any version specifier)
- `typer` (and any version specifier)

Move `uvicorn[standard]` to `[project.optional-dependencies.dev]` (needed for `make mcp-dev`).

Remove `[project.scripts]`:
```toml
# DELETE this:
# [project.scripts]
# dj = "app.cli.main:app"
```

Check if `rich` is used by anything other than CLI. If not, remove it too.

- [ ] **Step 2: Update Makefile**

Remove `make run` target (was `uvicorn app.main:app`).
Keep all `make mcp-*` targets.

- [ ] **Step 3: Verify fastmcp.json**

Confirm `source.path` is `app/mcp/gateway.py` and `source.entrypoint` is `create_dj_mcp`. No changes needed if these are correct.

- [ ] **Step 4: Sync and verify**

```bash
uv sync && make check
```

Expected: lint passes, tests pass, no missing deps.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml Makefile uv.lock && git commit -m "chore: remove FastAPI/typer deps, clean up project config"
```

---

## Task 9: Remove compatibility shims

**Files to delete (shim files):**
- `app/config.py` (shim)
- `app/errors.py` (shim)
- `app/database.py` (shim)
- `app/models/` (shim directory)
- `app/repositories/` (shim directory)
- `app/clients/` (shim directory)
- `app/utils/audio/` (shim)
- `app/utils/text_sort.py` (already moved)

- [ ] **Step 1: Update scripts/ to use new import paths**

```bash
find scripts/ -name "*.py" -exec sed -i '' \
  's/from app\.models/from app.core.models/g; s/from app\.config/from app.core.config/g; s/from app\.database/from app.infrastructure.database/g; s/from app\.repositories/from app.infrastructure.repositories/g; s/from app\.utils\.audio/from app.audio/g; s/from app\.errors/from app.core.errors/g; s/from app\.clients/from app.infrastructure.clients/g' {} +
```

- [ ] **Step 2: Verify scripts work**

Run a quick import check:
```bash
uv run python -c "from scripts.checkpoint import CheckpointManager; print('OK')"
```

- [ ] **Step 3: Delete shim files**

```bash
rm -f app/config.py app/errors.py app/database.py
rm -rf app/models app/repositories app/clients
rm -rf app/utils
```

- [ ] **Step 4: Run full check**

Run: `make check`
Expected: All lint + tests pass

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: remove compatibility shims, use new import paths everywhere"
```

---

## Task 10: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.claude/rules/api.md`
- Modify: `.claude/rules/mcp.md`
- Modify: `.claude/rules/testing.md`
- Modify: `.claude/rules/documentation.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CLAUDE.md**

- Remove REST API references from Architecture section
- Update architecture diagram:
```text
MCP Gateway (FastMCP 3.0)
  ├── Yandex Music (namespace "ym") — 28 OpenAPI-generated tools
  └── DJ Workflows (namespace "dj") — 7 domain providers, ~56 tools

Domain: Service → Repository → AsyncSession → DB
Audio: Pure functions (no DB deps)
```
- Remove `make run` from Commands section
- Remove CLI commands (`dj ...`)
- Remove FastAPI/uvicorn from Commands section
- Update file paths to new structure

- [ ] **Step 2: Update .claude/rules/api.md**

Remove entire REST-specific content (router pattern, DI pattern, OpenAPI responses, schema conventions). Replace with brief note that MCP is the sole transport layer. Keep service/repository patterns as they're still valid.

- [ ] **Step 3: Update .claude/rules/mcp.md**

- Update tools/ section to reference providers/ structure
- Update tool count (7 providers, ~56 tools)
- Update gateway composition description
- Keep DI, types, prompts, resources, testing sections

- [ ] **Step 4: Update .claude/rules/testing.md**

- Remove REST test patterns (AsyncClient, ASGITransport)
- Remove `client` fixture documentation
- Remove CLI test documentation
- Update conftest.py description
- Update test organization tree

- [ ] **Step 5: Update CHANGELOG.md**

Add to `[Unreleased]`:
```markdown
### Changed
- Restructured `app/` into `core/`, `infrastructure/`, `services/`, `audio/`, `mcp/` hierarchy
- Consolidated 18 MCP tool files into 7 domain providers
- Moved Sentry/OTEL initialization to `app/mcp/observability.py`

### Removed
- FastAPI REST API layer (routers, schemas, middleware, main.py)
- Typer CLI layer (app/cli/)
- FastAPI, uvicorn (core dep), typer from dependencies
- ~60 files, ~6300 lines of redundant transport code
- REST and CLI test suites
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "docs: update all documentation for MCP-first architecture"
```

---

## Task 11: Final verification and cleanup

- [ ] **Step 1: Run full check**

```bash
make check
```

Expected: lint + tests all pass.

- [ ] **Step 2: Check for dead imports/code**

```bash
uv run ruff check app/ --select F401,F811 2>&1 | head -20
```

Fix any unused imports.

- [ ] **Step 3: Verify MCP tool count**

```bash
make mcp-list 2>&1 | wc -l
```

Expected: ~84 tools (same as before refactoring).

- [ ] **Step 4: Verify no references to deleted modules**

```bash
grep -r "from app\.routers\|from app\.schemas\|from app\.cli\|from app\.middleware\|from app\.main\|from app\.dependencies" app/ tests/ scripts/ --include="*.py" 2>/dev/null
```

Expected: No output (no remaining references to deleted modules).

- [ ] **Step 5: Check for empty directories**

```bash
find app/ -type d -empty 2>/dev/null
```

Remove any empty dirs.

- [ ] **Step 6: Final commit if any cleanup**

```bash
git add -A && git commit -m "chore: final cleanup after MCP-first refactoring"
```

- [ ] **Step 7: Push branch**

```bash
git push -u origin refactor/mcp-first-architecture
```
