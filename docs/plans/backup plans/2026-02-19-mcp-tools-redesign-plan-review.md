# MCP Tools Redesign (Phase 1) — Critical Plan Review

Date: 2026-02-19
Target plan: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md`
Related design: `docs/plans/2026-02-19-mcp-tools-redesign-design.md`

This review is "critical" in the code-review sense: findings ordered by severity (blockers first), with concrete fixes.

## Executive Summary

The plan is directionally correct (refs/EntityFinder + response envelope + universal search + pagination), but in its current form it is not implementable end-to-end:

- The proposed `search` tool contract + tests do not match how FastMCP tools return structured outputs in this repo.
- Pagination and "total_matches" stats are currently designed in a way that will lie to the agent (offset isn't applied; totals are page-lens).
- Track search cannot satisfy the stated goals ("search by artist/title/album/genre") with the current repository queries.
- Integration tests cannot work unless MCP DB sessions are wired to the test engine (currently they won't be).
- "SQL-level filter" is incorrect for a composite PK features table (it will duplicate tracks by `run_id` unless "latest per track" is enforced).
- Audio namespace tasks are blocked by missing `track_ref -> audio_path` resolution (assets exist as a model but are not used anywhere).

## Blockers (Must Fix)

### 1) Incorrect tool result contract in tests and implementation

Plan uses `Client.call_tool(...)` then `json.loads(result[0].text)` in `tests/mcp/test_search_tools.py`, and implements `search(...) -> str` that manually returns JSON.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1042`, `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1089`
- Why it breaks: in this repo, tools typically return Pydantic models and FastMCP client exposes them as `ToolResult.data` (see `tests/mcp/test_client_integration.py`).
- Fix:
  - Make `search(...) -> SearchResponse` (Pydantic model), not `str`.
  - Update tests to assert `result.data` shape (or `result.data.model_dump()`), not `result[0].text`.

### 2) Pagination is designed but not actually applied

The plan calculates `offset` from cursor, but then ignores it in finders (hardcoded `offset=0` in repository calls).

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1103`, `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:740`
- Why it breaks: the cursor will keep returning the same "first page"; `has_more` and `next_cursor` will drift into nonsense.
- Fix:
  - Extend Finder API to accept `offset` and return real `total`.
  - Wire `offset` into repo calls (e.g. `search_by_title(query, offset=offset, limit=limit)`).

### 3) Universal search does not meet the stated search semantics

`TrackFinder` searches only `Track.title`, but the project requirements repeatedly mention search by artist/title/album/genre and OCR-tolerant fuzzy matching.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:741`
- Why it breaks: agent will type artist name and get 0 results unless it is in the track title string.
- Fix:
  - Add DB query that joins `artists` (and later `releases/labels/genres`) and searches across those fields.
  - Even Phase 1 should do at least `Track.title OR Artist.name`.

### 4) Integration tests do not connect MCP DB to the test engine

The plan proposes an integration test that writes to `session` fixture, but `workflow_mcp` tools will use `app.database.session_factory` (dev DB) via `app.mcp.dependencies.get_session`.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1380`
- Why it breaks: the tool reads a different database than the test writes to.
- Fix options:
  - Patch `app.database.session_factory` in MCP tests to use the test `engine`/`async_sessionmaker`, or
  - Make `create_workflow_mcp()` accept a session provider override (dependency injection entrypoint), or
  - Provide an MCP-specific test fixture that builds `workflow_mcp` with an overridden `get_session`.

### 5) AudioFeatures SQL filter will return duplicates across runs

`track_audio_features_computed` has PK `(track_id, run_id)`. A naive `list(filters=...)` query returns multiple rows per track and inflates totals.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:988`, `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1002`
- Fix:
  - Query "latest features per track" (same pattern as `AudioFeaturesRepository.list_all()`), then apply filters on that derived set.
  - Alternatively, require `run_id` as an explicit filter for Phase 1 (but that undermines "agent-first" simplicity).

## High-Risk Design Gaps (Will Mislead Agent)

### 6) `total_matches` is page-length, not total

Plan sets `total_matches["tracks"] = len(found.entities)` which is "items returned" not "items exist".

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1118`
- Why it matters: stats are part of the response envelope contract; wrong stats = bad agent decisions (pagination, filtering, "how big is this result set?").
- Fix:
  - Finder should return `(items, total)`; stats should use `total`, while response includes only `items`.

### 7) One cursor for multi-category results is underspecified

If `scope="all"` returns `tracks/playlists/sets/artists`, a single cursor cannot represent pagination state for 4 independent result sets.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1085`
- Fix options:
  - Make `scope` required to be a single category for paginated calls, or
  - Return per-category cursors/totals (more complex but consistent).

### 8) Response levels are declared but not operationalized

"Summary/detail/full" is core to "token budget principle", but Phase 1 tools don't accept a `level` parameter and finders always build one shape.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:21`
- Fix:
  - Add `level: Literal['summary','detail'] = 'summary'` to `search`/`filter_tracks`, and implement field selection accordingly.
  - Keep "full" for Phase 2+ (audio namespace).

## Feasibility / Scope Issues

### 9) Audio namespace tasks are blocked by missing `track_ref -> audio_path` mapping

Audio compute tools need to load audio. The DB does not store a path on `Track`; there is an `AudioAsset` model but no repository/service usage.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1286`
- Fix:
  - Phase 1: implement audio tools as `audio_path`-only (explicit path input), OR
  - Add `AudioAssetRepository` + a resolver `resolve_audio_path(track_ref)` and integrate it first.

### 10) Visibility toggles across mounted servers need a proof test

Plan assumes `dj_activate_audio_mode` can enable `audio_*` tools hidden by tag on the gateway/mounted server graph.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1259`
- Risk: if `ctx.enable_components(tags=...)` scope is not global across mounts, activation will silently not work.
- Fix:
  - Add a small spike test that mounts a server with a tagged tool, disables the tag, then enables it via an activation tool and asserts visibility flips.

### 11) YM "extended visibility" may not be taggable per-tool post-generation

`FastMCP.from_openapi(...)` generates tools. Plan assumes we can tag "non-core" tools with `ym_extended` and hide them.

- Where: `docs/plans/2026-02-19-mcp-tools-redesign-plan.md:1330`
- Risk: depends on FastMCP OpenAPI provider API; may require route-map rules rather than per-tool tags.
- Mitigation:
  - Prefer routing/exclusion via `RouteMap` patterns (already used), and only add "extended" gating if FastMCP exposes per-operation metadata.

## Concrete Plan Improvements (Minimal Changes)

### A) Fix ordering: test harness before feature work

Add a "Task 0" (or move tasks) to make integration possible:

- Provide a test-only session provider for MCP tools (`get_session` override) so that DB-backed tools are testable.
- Decide and codify tool result format: return Pydantic models, not JSON strings.

### B) Adjust Finder API

Change Finder contract to support correct stats/pagination:

- Input: `ref, offset, limit, level`
- Output: `items, total, exact, source`

### C) Narrow universal search v1 scope

To ship Phase 1 safely:

- Make `search(scope='tracks'|'playlists'|'sets'|'artists')` the default; `scope='all'` can be added later with per-category pagination.
- Implement Track search across `Track.title` + `Artist.name` first; add album/genre/label in Phase 2.

### D) Make filtering correct for "latest features"

`filter_tracks` should filter on "latest computed features per track", not raw `track_audio_features_computed` rows.

## Time Estimate Reality Check

The plan estimates ~3.5 hours total. With the above blockers fixed, it is still likely closer to:

- 1.0–1.5h: test harness + tool contract alignment
- 1.0–2.0h: correct finders + SQL joins + pagination + totals
- 0.5–1.0h: library stats + envelope integration + ruff/mypy cleanup
- 0.5–1.0h: visibility spike + YM gating feasibility check

Total: ~3–5 hours (without audio namespace implementations).

## Recommended Next Step

If you want this to be executable immediately, update the plan first in these exact places:

- Replace `search(...) -> str` with `search(...) -> SearchResponse` and fix tests accordingly.
- Add `offset` and `total` into finder paths; pass `offset` to repositories.
- Wire MCP tests to an in-memory engine (override `app.database.session_factory` or inject `get_session`).
