# MCP Tool Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all MCP tool gaps discovered during DJ set building session — eliminate the need for ad-hoc Python scripts.

**Architecture:** Each gap becomes a new MCP tool or parameter extension in `app/mcp/tools/`. Tools follow existing patterns: DI via `Depends`, Pydantic return types, tags for visibility, docstrings for MCP client.

**Tech Stack:** FastMCP 3.0, SQLAlchemy async, Pydantic v2, pytest-asyncio

---

## Session Audit: 7 Moments Where Ad-Hoc Code Was Required

| # | What happened | Lines of ad-hoc code | Root cause |
|---|--------------|---------------------|------------|
| 1 | **Populated playlist from YM** — `sync_playlist` returned 0 (provider_code bug), wrote raw SQL INSERT into `dj_playlist_items` | ~15 lines Python+SQL | No `import_ym_playlist` tool; `sync_playlist` depends on provider_code match |
| 2 | **Fetched albumIds for YM upload** — queried `yandex_metadata` + called `ym_get_tracks` for missing ones, then manually assembled diff JSON | ~30 lines | No tool wraps "resolve albumIds + push to YM" in one call |
| 3 | **Greedy chain builder** — GA timed out on 343+ tracks, wrote 100-line greedy algorithm with Camelot neighbors + energy arc targeting | ~100 lines | `build_set` only supports GA mode (O(n^2) matrix), no greedy/fast mode |
| 4 | **Copied MP3 files** — `deliver_set` only wrote metadata files, wrote shutil.copy2 script with iCloud stub detection | ~40 lines | Fixed: `_copy_mp3_files()` now in deliver_set |
| 5 | **Created YM playlists manually** — `sync_set_to_ym` blocked by elicitation, called `ym_create_playlist` + `ym_change_playlist_tracks` manually | ~10 lines per set | Fixed: `force` param added |
| 6 | **Bulk pushed 5 sets to YM** — wrote Python loop with rate limiting over `YandexMusicClient` | ~40 lines | No batch tool exists |
| 7 | **Selected tracks by audio quality** — wrote complex SQL with weighted scoring (kick_prominence, pulse_clarity, hp_ratio, centroid) | ~50 lines SQL | `filter_tracks` only supports BPM/key/energy, not extended features |

**Items 4 and 5 are already fixed.** This plan covers items 1, 2, 3, 6, 7.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/mcp/tools/search.py` | Modify | Extend `filter_tracks` with advanced audio params |
| `app/mcp/tools/setbuilder.py` | Modify | Add `optimizer` param (`ga` / `greedy`) to `build_set` |
| `app/mcp/tools/sync.py` | Modify | Add `batch_sync_sets_to_ym` tool, fix `import_ym_to_local` flow |
| `app/mcp/tools/playlist.py` | Modify | Add `populate_from_ym` tool |
| `app/utils/audio/greedy_chain.py` | Create | Greedy chain builder (extracted from session script) |
| `app/mcp/types/workflows.py` | Modify | New result types if needed |
| `tests/mcp/test_workflow_setbuilder.py` | Modify | Tests for greedy mode |
| `tests/mcp/test_workflow_sync.py` | Modify | Tests for batch sync |
| `tests/mcp/test_search_filter.py` | Modify | Tests for extended filter |
| `tests/utils/test_greedy_chain.py` | Create | Unit tests for greedy builder |

---

## Task 1: Extend `filter_tracks` with advanced audio parameters

**Why:** User wrote 50-line SQL to filter by `kick_prominence`, `hp_ratio`, `centroid_mean_hz`, `pulse_clarity`. Current `filter_tracks` only supports BPM, key_code, energy.

**Files:**
- Modify: `app/mcp/tools/search.py` (filter_tracks function)
- Test: `tests/mcp/test_search_filter.py`

- [ ] **Step 1: Read current `filter_tracks` signature**
  - File: `app/mcp/tools/search.py`, find `filter_tracks` function
  - Note existing params: `bpm_min`, `bpm_max`, `key_code`, `energy_min`, `energy_max`

- [ ] **Step 2: Add new optional parameters**
  ```python
  async def filter_tracks(
      # ... existing params ...
      kick_min: float | None = None,
      kick_max: float | None = None,
      hp_ratio_min: float | None = None,
      hp_ratio_max: float | None = None,
      centroid_min: float | None = None,
      centroid_max: float | None = None,
      camelot_keys: list[str] | None = None,  # e.g. ["4A","5A","6A"]
      min_quality_score: float | None = None,  # composite quality threshold
      # ... existing DI params ...
  )
  ```

- [ ] **Step 3: Add filter logic**
  - For each new param, add `WHERE` clause to the SQL query
  - `camelot_keys`: join `keys` table, filter by `keys.camelot IN (:keys)`
  - `min_quality_score`: compute `kick_prominence * 0.3 + pulse_clarity * 0.2 + tempo_confidence * 0.2 + bpm_stability * 0.15 + energy_mean * 0.15` and filter

- [ ] **Step 4: Add metadata test**
  ```python
  async def test_filter_tracks_extended_params(workflow_mcp):
      tools = await workflow_mcp.list_tools()
      tool = next(t for t in tools if t.name == "filter_tracks")
      props = set(tool.parameters.get("properties", {}).keys())
      assert "kick_min" in props
      assert "camelot_keys" in props
  ```

- [ ] **Step 5: Run tests, commit**
  ```bash
  uv run pytest tests/mcp/test_search_filter.py -v
  git add app/mcp/tools/search.py tests/mcp/test_search_filter.py
  git commit -m "feat(mcp): extend filter_tracks with kick, hp_ratio, centroid, camelot_keys"
  ```

---

## Task 2: Add greedy chain builder as alternative to GA

**Why:** GA builds O(n^2) transition matrix and runs 200 generations — takes 5+ minutes on 300+ tracks. User's greedy script ran in 0.1s with avg score 0.97.

**Files:**
- Create: `app/utils/audio/greedy_chain.py`
- Modify: `app/mcp/tools/setbuilder.py` (build_set)
- Modify: `app/services/set_generation.py`
- Test: `tests/utils/test_greedy_chain.py`

- [ ] **Step 1: Create `greedy_chain.py`**

  Core algorithm from session (tested, works):
  ```python
  @dataclass(frozen=True, slots=True)
  class GreedyChainConfig:
      track_count: int = 20
      energy_arc: str = "classic"  # classic/progressive/roller/wave/flat
      bpm_tolerance: float = 4.0
      seed: int | None = None

  @dataclass(frozen=True, slots=True)
  class GreedyChainResult:
      track_ids: list[int]
      scores: list[float]
      avg_score: float
      min_score: float

  def build_greedy_chain(
      features: list[TrackData],
      config: GreedyChainConfig,
  ) -> GreedyChainResult:
      """O(n*k) greedy chain: pick best compatible next track at each step."""
  ```

  Key logic:
  - Camelot neighbors (distance 0 or 1 only)
  - BPM tolerance check (reject > bpm_tolerance)
  - Energy arc targeting via LUFS
  - Greedy: at each step pick best `compat * 0.65 + energy_fit * 0.35`

- [ ] **Step 2: Write unit tests for greedy_chain**
  ```python
  def test_greedy_chain_basic():
      tracks = [make_track_data(i, bpm=128, key_code=0) for i in range(30)]
      result = build_greedy_chain(tracks, GreedyChainConfig(track_count=10))
      assert len(result.track_ids) == 10
      assert result.avg_score > 0.8

  def test_greedy_chain_respects_bpm_tolerance():
      # tracks at 128 and 140 BPM should not be adjacent
      ...

  def test_greedy_chain_energy_arc():
      # classic arc: first track should have lowest LUFS
      ...
  ```

- [ ] **Step 3: Run tests to verify**
  ```bash
  uv run pytest tests/utils/test_greedy_chain.py -v
  ```

- [ ] **Step 4: Wire into `build_set` via `optimizer` param**
  ```python
  async def build_set(
      # ... existing params ...
      optimizer: str = "ga",  # "ga" | "greedy"
      # ...
  ):
  ```
  When `optimizer="greedy"`: call `build_greedy_chain()` directly, skip GA.

- [ ] **Step 5: Wire into `SetGenerationService`**
  - Add `optimizer` field to `SetGenerationRequest`
  - In `generate()`: if `optimizer == "greedy"`, call greedy builder instead of GA
  - Return same `SetGenerationResponse` format

- [ ] **Step 6: Metadata test + commit**
  ```bash
  uv run pytest tests/mcp/test_workflow_setbuilder.py tests/utils/test_greedy_chain.py -v
  git commit -m "feat(mcp): add greedy chain builder as fast alternative to GA"
  ```

---

## Task 3: Add `populate_from_ym` tool

**Why:** User had to write raw SQL to insert 962 tracks into local playlist because `sync_playlist` failed (provider_code bug). Even after the bug fix, there's no simple "import this YM playlist into local DB" tool.

**Files:**
- Modify: `app/mcp/tools/playlist.py`
- Test: `tests/mcp/test_workflow_playlist.py` (or inline in existing)

- [ ] **Step 1: Add `populate_from_ym` tool**
  ```python
  @mcp.tool(tags={"sync", "yandex"})
  async def populate_from_ym(
      playlist_id: int,
      ym_kind: int,
      ctx: Context,
      # ... DI ...
  ) -> dict[str, object]:
      """Populate a local playlist with tracks from a YM playlist.

      Fetches YM playlist tracks, matches them against local DB
      via provider_track_ids, adds matched tracks to local playlist.
      Skips tracks not in local DB (reports count).
      """
  ```

  Logic:
  1. Fetch YM playlist tracks via `YandexMusicClient.fetch_playlist_tracks()`
  2. Extract track IDs from response
  3. Query `provider_track_ids` for matches (provider_code = "ym")
  4. INSERT matched track_ids into `dj_playlist_items`
  5. Return `{"added": N, "skipped": M, "total_ym": K}`

- [ ] **Step 2: Link + populate in one call**
  - Also update `platform_ids` JSON on the playlist (auto-link)

- [ ] **Step 3: Metadata test**
  ```python
  async def test_populate_from_ym_registered(workflow_mcp):
      tools = await workflow_mcp.list_tools()
      names = {t.name for t in tools}
      assert "populate_from_ym" in names
  ```

- [ ] **Step 4: Commit**
  ```bash
  git commit -m "feat(mcp): add populate_from_ym tool for YM playlist import"
  ```

---

## Task 4: Add `batch_sync_sets_to_ym` tool

**Why:** User wrote 40-line Python loop to push 5 sets to YM with rate limiting. No batch tool existed.

**Files:**
- Modify: `app/mcp/tools/sync.py`
- Test: `tests/mcp/test_workflow_sync.py`

- [ ] **Step 1: Add batch tool**
  ```python
  @mcp.tool(tags={"sync", "yandex"}, timeout=600)
  async def batch_sync_sets_to_ym(
      set_ids: list[int],
      force: bool = True,
      ctx: Context | None = None,
      # ... DI ...
  ) -> dict[str, object]:
      """Push multiple DJ sets to YM as playlists.

      Creates/updates a YM playlist for each set. Rate-limited
      with 1.5s delay between API calls. Reports per-set status.
      """
  ```

  Logic:
  - Loop over set_ids
  - For each: resolve tracks, map to YM IDs, create/update playlist
  - `ctx.report_progress(i, len(set_ids))` for each
  - Rate limit: `asyncio.sleep(1.5)` between sets
  - Return `{"synced": N, "failed": M, "results": [per-set status]}`

- [ ] **Step 2: Metadata test + commit**
  ```bash
  git commit -m "feat(mcp): add batch_sync_sets_to_ym for bulk YM push"
  ```

---

## Task 5: Add `score_track_pairs` standalone tool

**Why:** User needed to pre-score compatibility of track pairs before building a set. Current `score_transitions` requires an existing set+version.

**Files:**
- Modify: `app/mcp/tools/setbuilder.py`
- Reuse: `app/mcp/tools/_scoring_helpers.py` (score_consecutive_transitions)
- Test: `tests/mcp/test_workflow_setbuilder.py`

- [ ] **Step 1: Add tool**
  ```python
  @mcp.tool(tags={"setbuilder"}, annotations={"readOnlyHint": True})
  async def score_track_pairs(
      track_ids: list[int],
      ctx: Context,
      # ... DI (unified_svc, track_svc, features_svc) ...
  ) -> list[TransitionScoreResult]:
      """Score transitions between consecutive track pairs.

      Does NOT require a set — works on any ordered list of track IDs.
      Useful for pre-analysis before build_set.
      """
  ```

  Logic: reuse `score_consecutive_transitions()` from `_scoring_helpers.py` with mock items.

- [ ] **Step 2: Metadata test + commit**
  ```bash
  git commit -m "feat(mcp): add score_track_pairs for pre-build analysis"
  ```

---

## Order of Implementation

1. **Task 2** (greedy chain) — highest impact, eliminates 100-line scripts
2. **Task 1** (extended filter) — enables smart track selection via MCP
3. **Task 3** (populate_from_ym) — eliminates raw SQL for playlist import
4. **Task 5** (score_track_pairs) — enables pre-build scoring
5. **Task 4** (batch sync) — convenience for multi-set workflows

## Verification

```bash
make check  # all tests pass

# Task 1:
make mcp-call TOOL=dj_filter_tracks \
  ARGS='{"bpm_min":125,"bpm_max":132,"camelot_keys":["4A","5A","6A"],"kick_min":0.5}'

# Task 2:
make mcp-call TOOL=dj_build_set \
  ARGS='{"playlist_ref":25,"set_name":"Greedy Test","optimizer":"greedy"}'
# Should complete in <1 sec

# Task 3:
make mcp-call TOOL=dj_populate_from_ym ARGS='{"playlist_id":25,"ym_kind":1280}'

# Task 5:
make mcp-call TOOL=dj_score_track_pairs ARGS='{"track_ids":[701,734,146617556]}'
```
