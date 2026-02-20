# MCP Tools Redesign (Phase 4) -- Plan Review (Critical)

Date: 2026-02-19
Target plan: `docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md`

This is a critical plan review (blockers first). It is written against the current repository state, not an idealized greenfield.

## Blockers (Must Fix Before Implementation)

### 1) The plan deletes `sync_tools.py`, but Phase 3 also says "rewritten sync tools" (same name/path ambiguity)

In the Phase 4 inventory, `app/mcp/workflows/sync_tools.py` is listed as a file to delete entirely. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:46`)

However, Phase 4 also claims Phase 3 delivers "Rewritten sync tools" and does not pin down where those tools live (it even says they might still be in `app/mcp/workflows/sync_tools.py`). (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:34`, `docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:155`)

Impact:
- If Phase 3 rewrites sync tools in-place (same file), Phase 4 will delete the *new* implementations.
- If Phase 3 puts them elsewhere, Phase 4 needs an explicit import path update in `app/mcp/workflows/server.py`.

Fix:
- Make Phase 3 a hard prerequisite with a *single canonical module path* for sync tools (e.g. keep `app/mcp/workflows/sync_tools.py` but replace its contents; or move to `app/mcp/sync/tools.py` and update imports).
- In Phase 4, delete only the stub functions (or delete the file only if the new tools are guaranteed elsewhere).

### 2) Test plan references files that do not exist (and misses several that will definitely fail)

The plan says to verify CRUD tools via `tests/mcp/test_crud_tools.py`, but that file does not exist today. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:101`)

More importantly, Phase 4 removes multiple tools, but does not mention updating/removing tests that currently assert those tools exist:
- `tests/mcp/test_client_integration.py` hard-codes the full workflow tool list, including `get_playlist_status`, `import_playlist`, `search_by_criteria`, and all sync stubs.
- `tests/mcp/test_progress.py` asserts `import_playlist` and `import_tracks` exist.
- `tests/mcp/test_visibility.py` spot-checks `dj_get_playlist_status` and `dj_export_set_m3u`.
- `tests/mcp/test_skills.py` asserts skill text includes `dj_get_playlist_status`.

Net: Phase 4 as written will fail tests even if the code changes are correct.

Fix:
- Add an explicit Phase 4 task: update test expectations + skill references to match the *post-Phase-4* tool set.
- Replace the referenced CRUD test command with the actual test module(s) created in Phase 2 (or explicitly add them in Phase 2).

### 3) The plan says "pure cleanup / no new modules" but proposes moving tools to new files

Phase 4 says: "No new modules." (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:7`)

But the inventory explicitly requires moving `download_tracks` "to own file". (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:77`) Task 11 also suggests renaming `import_tools.py` -> `download_tools.py`. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:1059`)

Fix:
- Decide: either allow module moves/renames (and track them in "new modules"), or keep the file structure and treat Phase 4 as "pure deletion + refactor in-place".

### 4) Plan's ref-migration tests/examples do not match FastMCP client/tool return contracts used in this repo

The plan's example tests treat tool results like raw dicts (e.g. `assert "playlist_id" in result or "error" in result`). (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:726`)

But current integration tests use FastMCP `Client.call_tool(...)` and assert on `CallToolResult.data.*` (structured output). See `tests/mcp/test_client_integration.py`.

Fix:
- Update all Phase 4 test snippets to match the existing pattern:
  - `async with Client(workflow_mcp) as client: result = await client.call_tool(...)`
  - Assert on `result.is_error` and `result.data.<field>`.

### 5) Export "unification" is still internally inconsistent (risk of ending Phase 4 with duplicate exports again)

Phase 4 removes duplicate exports from `setbuilder_tools.py` and says Phase 2 unifies to `export_set(format=...)`. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:389`)

But the plan's expected final tool list still includes `export_set_m3u`, `export_set_json` (and optionally `export_set`). (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:1203`)

Fix:
- Decide the canonical public surface:
  - Either keep only `export_set(format=...)`, and make `export_set_m3u/json/rekordbox` internal helpers (not MCP tools),
  - or keep the format-specific tools, and do NOT add a unified `export_set` tool (or hide one set behind tags).

## High-Risk / Likely Rework

### 6) Deleting `analysis_tools.py` may remove a high-signal summary tool unless CRUD explicitly replaces the *aggregated stats*

The plan asserts Phase 2 CRUD makes `get_playlist_status` redundant. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:95`)

CRUD list/get tools often do not replace:
- derived aggregates (bpm range, analyzed_tracks, key distribution),
- "one-shot" status UX that saves multiple calls.

Suggestion:
- If the goal is minimal tools, keep a single `playlist_status(playlist_ref)` (refs + envelope) that returns a small aggregated view + pagination stats.
- Or explicitly add the same aggregate fields to `get_playlist` response in Phase 2 so Phase 4 deletion is safe.

### 7) New Pydantic models in `types_v2.py` repeat current mutable-default patterns

The plan proposes list defaults like `energy_curve: list[float] = []`. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:474`)

Even if Pydantic copies defaults, this is easy to regress later and it is inconsistent with "clean final architecture".

Suggestion:
- Use `Field(default_factory=list)` for list defaults in `types_v2.py`.

### 8) Ref resolution loops can become N+1 queries for large batches

E.g. `download_tracks(track_refs=[...])` resolves refs one-by-one. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:1027`)

Suggestion:
- Add batch resolution helpers in EntityFinder (e.g. `find_many([...])`) or accept a mixed list and resolve in one DB query when possible.

### 9) Error handling in snippets uses `ValueError`, which will produce inconsistent ToolError messages

Several snippets raise `ValueError(...)` on not-found. (`docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:870`, `docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md:951`)

Suggestion:
- Use project-standard exceptions (`app.errors.NotFoundError` / `ValidationError`) or a Phase 2 envelope error schema consistently.

## Concrete Plan Edits I Recommend

1) Add "Task 0: Preflight audit" (before Task 1):
   - Verify Phase 1--3 modules actually exist at the referenced paths (search_tools.py, types_v2.py, entity_finder.py, response.py, platforms/sync modules).
   - Verify the tool surface you expect to end with (names, namespaces, tags).

2) Expand each deletion task with "update external references":
   - Update `tests/mcp/test_client_integration.py`, `tests/mcp/test_progress.py`, `tests/mcp/test_visibility.py`, `tests/mcp/test_skills.py`.
   - Update skill text under `app/mcp/skills/` to stop referencing removed tools (or keep compatibility aliases).

3) Resolve the exports decision explicitly (see blocker #5).

4) Make the sync module location explicit and non-ambiguous (see blocker #1).

