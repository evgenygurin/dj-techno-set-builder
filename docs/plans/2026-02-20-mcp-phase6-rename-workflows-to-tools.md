# Phase 6: Rename `workflows/` → `tools/` Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename `app/mcp/workflows/` to `app/mcp/tools/` and update all references — gateway, tests, pyproject.toml, docs.

**Architecture:** Pure mechanical rename. `git mv` for the directory, then find-and-replace across 4 scopes: production imports, test imports/fixtures, pyproject.toml B008 rules, documentation. No logic changes.

**Tech Stack:** Python 3.12, FastMCP, pytest, ruff, mypy, git

---

## Scope

| What | Count |
|------|-------|
| Files to move | 15 Python files in `app/mcp/workflows/` |
| Production imports to update | 15 (in `server.py` + `__init__.py` + `gateway.py`) |
| Test files with `workflow_mcp` fixture | 17 files, ~164 occurrences |
| pyproject.toml B008 per-file-ignores | 13 entries |
| `.claude/rules/mcp.md` | 1 file, ~10 references |
| CLAUDE.md / MEMORY.md | A few mentions |

**NOT in scope:** Renaming `create_workflow_mcp` → `create_tools_mcp` (too many test references; keep function name for now, just update module path).

---

### Task 1: Move directory with `git mv`

**Files:**
- Move: `app/mcp/workflows/` → `app/mcp/tools/`

**Step 1: Verify no uncommitted changes**

Run: `git status --short`
Expected: Clean working tree

**Step 2: Move the directory**

```bash
git mv app/mcp/workflows app/mcp/tools
```

**Step 3: Verify move**

Run: `ls app/mcp/tools/`
Expected: `__init__.py`, `server.py`, `compute_tools.py`, ... (15 files)

Run: `ls app/mcp/workflows/ 2>&1`
Expected: error (directory no longer exists)

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(mcp): git mv workflows/ → tools/"
```

> **Important:** This commit will break imports. That's OK — next tasks fix them. Commit early so git tracks the rename.

---

### Task 2: Update production imports

**Files:**
- Modify: `app/mcp/tools/__init__.py`
- Modify: `app/mcp/tools/server.py`
- Modify: `app/mcp/gateway.py`

**Step 1: Update `__init__.py`**

Replace the entire contents of `app/mcp/tools/__init__.py`:

```python
"""DJ workflow MCP tools."""

from app.mcp.tools.server import create_workflow_mcp

__all__ = ["create_workflow_mcp"]
```

**Step 2: Update `server.py` imports**

In `app/mcp/tools/server.py`, replace all 13 `from app.mcp.workflows.` → `from app.mcp.tools.`:

```python
from app.mcp.tools.compute_tools import register_compute_tools
from app.mcp.tools.curation_tools import register_curation_tools
from app.mcp.tools.discovery_tools import register_discovery_tools
from app.mcp.tools.download_tools import register_download_tools
from app.mcp.tools.export_tools import register_export_tools
from app.mcp.tools.features_tools import register_features_tools
from app.mcp.tools.playlist_tools import register_playlist_tools
from app.mcp.tools.search_tools import register_search_tools
from app.mcp.tools.set_tools import register_set_tools
from app.mcp.tools.setbuilder_tools import register_setbuilder_tools
from app.mcp.tools.sync_tools import register_sync_tools
from app.mcp.tools.track_tools import register_track_tools
from app.mcp.tools.unified_export_tools import register_unified_export_tools
```

**Step 3: Update `gateway.py`**

In `app/mcp/gateway.py`, line 13:

```python
# OLD:
from app.mcp.workflows import create_workflow_mcp
# NEW:
from app.mcp.tools import create_workflow_mcp
```

**Step 4: Run import smoke test**

```bash
uv run python -c "from app.mcp.gateway import create_dj_mcp; mcp = create_dj_mcp(); print('OK')"
```

Expected: `OK`

**Step 5: Commit**

```bash
git add -A && git commit -m "refactor(mcp): update production imports workflows → tools"
```

---

### Task 3: Update test fixtures and imports

**Files:**
- Modify: `tests/mcp/conftest.py`
- Modify: `tests/mcp/test_workflow_download.py` (has `from app.mcp.workflows.download_tools`)

**Step 1: Update `conftest.py`**

In `tests/mcp/conftest.py`, replace 2 occurrences:

```python
# OLD (line 21):
from app.mcp.workflows import create_workflow_mcp
# NEW:
from app.mcp.tools import create_workflow_mcp

# OLD (line 49):
from app.mcp.workflows import create_workflow_mcp
# NEW:
from app.mcp.tools import create_workflow_mcp
```

**Step 2: Update `test_workflow_download.py`**

Check for any direct imports from `app.mcp.workflows`:

```bash
grep -n "app.mcp.workflows" tests/mcp/test_workflow_download.py
```

Replace any found `app.mcp.workflows` → `app.mcp.tools`.

**Step 3: Run all MCP tests**

```bash
uv run pytest tests/mcp/ -v --tb=short 2>&1 | tail -20
```

Expected: ALL PASS (should be ~260+ tests)

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(mcp): update test imports workflows → tools"
```

---

### Task 4: Update `pyproject.toml` B008 per-file-ignores

**Files:**
- Modify: `pyproject.toml:65-77`

**Step 1: Replace all 13 entries**

In `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` section, replace:

```toml
# OLD:
"app/mcp/workflows/analysis_tools.py" = ["B008"]
"app/mcp/workflows/curation_tools.py" = ["B008"]
"app/mcp/workflows/discovery_tools.py" = ["B008"]
"app/mcp/workflows/setbuilder_tools.py" = ["B008"]
"app/mcp/workflows/sync_tools.py" = ["B008"]
"app/mcp/workflows/export_tools.py" = ["B008"]
"app/mcp/workflows/search_tools.py" = ["B008"]
"app/mcp/workflows/track_tools.py" = ["B008"]
"app/mcp/workflows/playlist_tools.py" = ["B008"]
"app/mcp/workflows/set_tools.py" = ["B008"]
"app/mcp/workflows/features_tools.py" = ["B008"]
"app/mcp/workflows/compute_tools.py" = ["B008"]
"app/mcp/workflows/unified_export_tools.py" = ["B008"]

# NEW:
"app/mcp/tools/*.py" = ["B008"]
```

> **Simplification:** Instead of 13 entries, use one glob pattern. `analysis_tools.py` no longer exists, so removing that line too.

**Step 2: Verify ruff still passes**

```bash
uv run ruff check app/mcp/tools/ 2>&1
```

Expected: `All checks passed!`

**Step 3: Commit**

```bash
git add pyproject.toml && git commit -m "refactor(mcp): consolidate B008 per-file-ignores for tools/"
```

---

### Task 5: Update `.claude/rules/mcp.md` documentation

**Files:**
- Modify: `.claude/rules/mcp.md`

**Step 1: Replace all references**

Use `replace_all` to update:
- `workflows/` → `tools/` (directory references)
- `app/mcp/workflows/` → `app/mcp/tools/` (import paths)
- `create_workflow_mcp` — keep as-is (function name unchanged)
- Update the directory tree structure
- Update the "adding a new tool" instructions
- Remove references to deleted files (`analysis_tools.py`, `import_tools.py`)

**Step 2: Verify doc renders**

Skim the file to make sure all references are consistent.

**Step 3: Commit**

```bash
git add -f .claude/rules/mcp.md && git commit -m "docs(mcp): update rules for tools/ rename"
```

---

### Task 6: Update MEMORY.md and other docs

**Files:**
- Modify: `/Users/laptop/.claude/projects/-Users-laptop-dev-dj-techno-set-builder/memory/MEMORY.md`
- Check: `CLAUDE.md` (if any workflows references)

**Step 1: Update MEMORY.md**

Replace any `app/mcp/workflows/` → `app/mcp/tools/` in MEMORY.md.

**Step 2: Check CLAUDE.md**

```bash
grep -n workflows CLAUDE.md
```

If found, update.

**Step 3: Commit**

```bash
git add -A && git commit -m "docs: update memory and project docs for tools/ rename"
```

---

### Task 7: Full verification

**Files:** None (verification only)

**Step 1: Lint**

```bash
uv run ruff check app/mcp/ tests/mcp/ && uv run ruff format --check app/mcp/ tests/mcp/
```

Expected: All clean

**Step 2: Type-check**

```bash
uv run mypy app/mcp/
```

Expected: Same pre-existing errors (12), no new ones

**Step 3: Full test suite**

```bash
uv run pytest -v --tb=short 2>&1 | tail -5
```

Expected: 914+ passed, 0 failed

**Step 4: Verify no stale references**

```bash
# Should find ZERO results in production code:
grep -r "app.mcp.workflows\|app/mcp/workflows" app/ --include="*.py"

# Should find ZERO results in test code:
grep -r "app.mcp.workflows\|app/mcp/workflows" tests/ --include="*.py"
```

Expected: No matches

**Step 5: Final commit (squash-ready)**

```bash
git add -A && git commit -m "refactor(mcp): Phase 6 complete — rename workflows/ → tools/"
```

---

## Summary

| Task | What | Files changed |
|------|------|---------------|
| 1 | `git mv` directory | 15 files moved |
| 2 | Production imports | 3 files |
| 3 | Test imports | 2 files |
| 4 | pyproject.toml B008 | 1 file |
| 5 | `.claude/rules/mcp.md` | 1 file |
| 6 | MEMORY.md + CLAUDE.md | 1-2 files |
| 7 | Full verification | 0 files |

**Total: ~7 commits, pure rename, zero logic changes.**
