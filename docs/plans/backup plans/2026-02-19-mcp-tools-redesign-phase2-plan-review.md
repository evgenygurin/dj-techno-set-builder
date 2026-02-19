# MCP Tools Redesign (Phase 2) — Plan Review (Critical)

Date: 2026-02-19
Target plan: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md`
Prereq: Phase 1 must be correct/merged first.

This is a critical review in the "code review" sense: blockers first, then high-risk gaps, then concrete plan fixes.

## Executive Summary

Phase 2 goals (CRUD tools, compute/persist split, unified export, stub removal) are good, but the current plan is not implementable as written:

- It repeats Phase 1's biggest contract mistake: treating `Client.call_tool()` as if it returns a list of text blocks (`result[0].text`) and building tools that return JSON strings.
- Several code snippets are incorrect against the current codebase (wrong imports, wrong repo method names, wrong model requirements).
- Update tools are designed in a way that will accidentally overwrite required fields with `None` (because FastMCP passes defaults).
- The "compute-only analyze_track -> save_features(features_json)" split is currently not viable because `TrackFeatures` is a nested dataclass with numpy arrays and the run model requires required fields.
- The plan has multiple scalability regressions (loading all features then slicing; N+1 DB queries in list_features).

Net: this plan needs a "Phase 2.0" correction pass (tool contract, tests, serialization + DB wiring) before implementation.

## Blockers (Must Fix Before Coding)

### 1) Tool output contract and tests are incompatible with FastMCP usage in this repo

Pattern appears throughout Phase 2:

- Tests: `json.loads(result[0].text)` (e.g. `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:667`)
- Tools: return `str` that is already JSON (e.g. `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:761`)

In this repo, `Client.call_tool()` returns a `CallToolResult` with:

- `result.data` (structured/typed) and
- `result.content` (list of content blocks; `result.content[0].text` is the JSON text, if needed).

Fix:

- Stop returning JSON strings from tools. Return Pydantic models (or plain dicts) and let FastMCP generate structured output.
- Update tests to assert on `result.data` / `result.structured_content` (or `result.content[0].text` as fallback), never `result[0]`.

### 2) Converters test assumes the wrong Camelot mapping

`key_code_to_camelot(8)` is `9A` (Em), not `5A`.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:395`
- Fix: update expected values in tests and any doc assumptions.

### 3) Update tools will clobber required fields with `None`

Example: `update_track` constructs `TrackUpdate(title=title, duration_ms=duration_ms)` even when user did not pass those fields, so they become explicitly set to `None` and propagate into `exclude_unset=True` updates.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:846`
- Impact: `title` is NOT NULL; this will produce invalid updates or silent corruption attempts.

Fix options:

- Preferred: accept a single Pydantic input object (`data: TrackUpdate`) so unset stays unset.
- Alternative: build `update_kwargs = {k: v for k, v in {...}.items() if v is not None}` before constructing update schema.

### 4) Error handling is inconsistent (returns `{error: ...}` instead of raising)

Plan returns JSON objects with `"error"` keys and still reports tool call success (`is_error=False`).

- Example: `get_track` not found returns `json.dumps({"error": ...})` at `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:810`.

Fix:

- Raise `NotFoundError` / `ValueError` (FastMCP maps it to ToolError for clients) or return an explicit `ActionResponse(success=False, ...)` but keep one consistent policy across tools.

### 5) `save_features` is not implementable with current models/repos

Problems in the plan snippet:

- Wrong repo name: `FeatureExtractionRunRepository` does not exist; repo is `FeatureRunRepository`.
- Run model requires `pipeline_name` and `pipeline_version` (and likely parameters), so `create(status="completed")` is invalid.
- Wrong import: `from app.utils.audio.types import TrackFeatures` (does not exist; it's `app.utils.audio._types`).
- `TrackFeatures` is a nested dataclass with numpy arrays; `TrackFeatures(**features_data)` from JSON will fail.

Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:1457`

Fix:

- Decide the actual persistence API:
  - Either keep `analyze_track` as compute+persist (agent-first), or
  - Define a JSON-serializable `TrackFeaturesPayload` schema and implement robust (de)serialization to/from dataclasses (including arrays).
- Use proper run creation: create a run with required fields, then mark completed via `FeatureRunRepository.mark_completed()`.

### 6) `analyze_track` compute tool references non-existent functions and wrong repo methods

- Uses `DjLibraryItemRepository.get_by_track(...)` but current method is `get_by_track_id`.
- Calls `run_full_analysis` and `features.to_dict()` which do not exist in `app/utils/audio/pipeline.py`.

Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:1576`

Fix:

- Use `TrackAnalysisService._extract_full_sync()` (or a new pure function) to compute without persisting.
- Add an explicit serializer for the returned dataclasses, or drop the compute/persist split for this tool.

### 7) Integration tests are knowingly broken without DB wiring changes

Plan admits MCP tools might use the wrong session, but never actually implements the override.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:2286`

Fix:

- Add an MCP test fixture that builds `workflow_mcp` with `get_session` overridden to use the test `engine` (or monkeypatch `app.database.session_factory`).

## High-Risk Issues (Will "Work" but Be Wrong/Costly)

### 8) `list_features` is not scalable

The plan loads all features with `list_all()` and slices in Python, then does N+1 queries to load tracks.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:1386`

Fix:

- Implement a paginated SQL query for "latest per track" + optional filters.
- Batch-load tracks in one query (`WHERE track_id IN (...)`) and batch-load artists.

### 9) Phase 2 continues the "JSON string envelope" approach, which undermines structured output

Returning JSON strings from tools means the output is just a giant string (and is harder for clients/agents to consume safely).

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:254`

Fix:

- Make wrappers return `EntityListResponse` / `ActionResponse` models directly, not `str`.

### 10) Unified export tool is underspecified and likely to regress behavior

The plan uses placeholders (`DjSetService(...)`, `SetExportService(...)`) and does not preserve existing parameters/behavior (rekordbox flags, base_path, cues, etc).

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:1852`

Fix:

- Start by wrapping existing export functions behind `export_set(format=...)` and keep all existing options, then deprecate old names.

### 11) Removing tools requires a migration plan for tests and clients

Phase 2 proposes removing import/sync/analysis/discovery tools, but the current test suite asserts they exist (`tests/mcp/test_workflow_sync.py`, `tests/mcp/test_workflow_analysis.py`, `tests/mcp/test_workflow_discovery.py`).

Fix:

- Plan must explicitly list test updates/removals and any backwards-compat aliases (optional).

## Concrete Plan Corrections (Minimal, Makes Phase 2 Executable)

1) Introduce "Task 0: Tool Contract + MCP Test DB Wiring"
   - Standardize on returning Pydantic models (no JSON strings).
   - Fix tests to use `result.data`.
   - Provide a `workflow_mcp_testdb` fixture (or override `get_session`) so integration tests can actually run.

2) Fix update tool inputs
   - Use `data: TrackUpdate` / `data: DjSetUpdate` / etc as a single argument, or filter `None` fields before building schemas.

3) Re-scope compute/persist split for audio features
   - Either keep a single `analyze_track_and_save` tool (agent-first), OR
   - Define a real serializable payload + run creation contract.

4) Fix scalability in list_features
   - No `list_all()` + slicing; do SQL pagination.
   - No per-track `get_by_id` loop; batch load.

5) Fix incorrect imports/APIs in snippets
   - `DjLibraryItemRepository.get_by_track_id`
   - `extract_all_features` / `TrackAnalysisService._extract_full_sync`
   - `FeatureRunRepository` + required run fields
   - `SetGenerationRequest` import from `app.schemas.set_generation`

## Notes

The file still contains the "For Claude: REQUIRED SUB-SKILL ..." line at the top, which is not relevant for Codex and should be removed or rewritten for this repo's agent workflow:

- `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md:3`
