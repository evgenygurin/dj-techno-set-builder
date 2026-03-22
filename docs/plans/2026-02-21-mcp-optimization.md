# MCP DJ Workflow Optimization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 3 missing MCP tools and extend `TransitionScoreResult` so that working with a set requires 1-2 tool calls instead of 5-10, eliminating the need to reason through intermediate steps.

**Architecture:** All new tools follow the existing pattern: `register_*_tools(mcp: FastMCP)` in `app/mcp/tools/`, new types in `app/mcp/types/workflows.py`, reuse `_collect_track_data` and `_generate_cheat_sheet` already in `delivery.py`.

**Tech Stack:** FastMCP 3.0, SQLAlchemy async, Pydantic v2, pytest-asyncio.

---

## Problem statement

Current set workflow requires ~8 tool calls to answer "what's in my set and are the transitions good?":
1. `get_set` → get version_id
2. 15× `get_track` → get titles
3. 15× `get_features` → get BPM/key/LUFS
4. `score_transitions` → get transition scores (but no BPM/key in output)
5. Mentally join all results

**After this plan:** 2 tool calls — `get_set_tracks` + `score_transitions` (extended), or just `get_set_cheat_sheet` for everything at once.

---

## Task 1: Add `SetTrackItem` type and `get_set_tracks` tool

**Files:**
- Modify: `app/mcp/types/workflows.py`
- Modify: `app/mcp/tools/set.py`
- Test: `tests/mcp/test_set_tools.py` (create if not exists)

### Step 1: Write the failing test

```python
# tests/mcp/test_set_tools.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_set_tracks_returns_ordered_items(client: AsyncClient, db_set_with_tracks):
    """get_set_tracks must return tracks in sort_index order with position starting at 1."""
    set_id, version_id = db_set_with_tracks
    resp = await client.post("/mcp/mcp", json={
        "method": "tools/call",
        "params": {"name": "dj_get_set_tracks", "arguments": {"set_ref": set_id}}
    })
    # For E2E via MCP tool, use dj_get_set_tracks MCP tool call pattern
    # ... (see existing test_e2e_dj_tools.py for exact call pattern)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_get_set_tracks_latest_version_by_default(client, db_set_with_tracks):
    """When version_id is None, uses latest version."""
    pass
```

**Run:** `uv run pytest tests/mcp/test_set_tools.py -v`
Expected: FAIL — `dj_get_set_tracks` tool not found.

### Step 2: Add `SetTrackItem` to `app/mcp/types/workflows.py`

Add after `TransitionSummary`:

```python
class SetTrackItem(BaseModel):
    """Track with position and audio features for set view (Level 2.5: ~200 bytes)."""

    position: int  # 1-based play order
    track_id: int
    title: str
    artists: str = ""
    bpm: float | None = None
    key: str | None = None  # Camelot notation e.g. "8A", "11B"
    energy_lufs: float | None = None
    duration_s: int | None = None
    pinned: bool = False
```

Also add `"SetTrackItem"` to `__all__`.

### Step 3: Export from `app/mcp/types/__init__.py`

Add `SetTrackItem` to the imports and `__all__` in `app/mcp/types/__init__.py`.

### Step 4: Add `get_set_tracks` tool to `app/mcp/tools/set.py`

Add inside `register_set_tools()`, after `delete_set`:

```python
@mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True}, timeout=60)
async def get_set_tracks(
    set_ref: str | int,
    version_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[SetTrackItem]:
    """Get all tracks of a set version with BPM/key/LUFS in one call.

    If version_id is None, uses the latest version automatically.
    Returns tracks in play order with position (1-based), pinned flag,
    and audio features (BPM, Camelot key, LUFS). No separate get_features
    calls needed.

    Args:
        set_ref: DJ set ref (int, "42", or "local:42").
        version_id: Specific version ID, or None for latest.
    """
    from contextlib import suppress

    from app.services.features import AudioFeaturesService
    from app.services.tracks import TrackService
    from app.utils.audio.camelot import key_code_to_camelot

    ref = parse_ref(str(set_ref))
    if ref.ref_type != RefType.LOCAL or ref.local_id is None:
        return []

    set_id = ref.local_id
    svc = _make_svc(session)
    track_svc = TrackService(session)
    features_svc = AudioFeaturesService(session)  # needs FeaturesRepository

    # Resolve version
    if version_id is None:
        versions = await svc.list_versions(set_id)
        if not versions.items:
            return []
        version_id = max(v.set_version_id for v in versions.items)

    items_list = await svc.list_items(version_id, offset=0, limit=500)
    items = sorted(items_list.items, key=lambda i: i.sort_index)

    # Batch fetch artists
    track_ids = [item.track_id for item in items]
    artists_map = await track_svc.get_track_artists(track_ids)

    result: list[SetTrackItem] = []
    for pos, item in enumerate(items, 1):
        entry = SetTrackItem(
            position=pos,
            track_id=item.track_id,
            title=f"Track {item.track_id}",
            pinned=item.pinned,
        )
        with suppress(Exception):
            track = await track_svc.get(item.track_id)
            entry.title = track.title
            entry.duration_s = track.duration_ms // 1000
        entry.artists = ", ".join(artists_map.get(item.track_id, []))
        with suppress(Exception):
            feat = await features_svc.get_latest(item.track_id)
            entry.bpm = feat.bpm
            entry.energy_lufs = feat.lufs_i
            with suppress(ValueError):
                entry.key = key_code_to_camelot(feat.key_code)
        result.append(entry)

    return result
```

**Note:** `AudioFeaturesService` requires its own repository. Check `app/mcp/dependencies.py` → `get_features_service`. Use `Depends(get_features_service)` instead of creating directly if the DI is available.

Correct version (using existing DI):

```python
@mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True}, timeout=60)
async def get_set_tracks(
    set_ref: str | int,
    version_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    features_svc: AudioFeaturesService = Depends(get_features_service),
    track_svc: TrackService = Depends(get_track_service),
) -> list[SetTrackItem]:
    ...
```

Also add imports at top of `set.py`:
```python
from app.mcp.dependencies import get_features_service, get_track_service
from app.mcp.types import SetTrackItem
from app.services.features import AudioFeaturesService
from app.services.tracks import TrackService
from app.utils.audio.camelot import key_code_to_camelot
```

### Step 5: Run tests

`uv run pytest tests/mcp/ -v -k "set_tracks"`
Expected: PASS (or skip if fixtures not yet wired — check `tests/mcp/test_e2e_dj_tools.py` for existing E2E pattern)

### Step 6: Lint + type check

```bash
uv run ruff check app/mcp/tools/set.py app/mcp/types/workflows.py
uv run mypy app/mcp/tools/set.py app/mcp/types/workflows.py
```

### Step 7: Commit

```bash
git add app/mcp/tools/set.py app/mcp/types/workflows.py app/mcp/types/__init__.py
git commit -m "feat(mcp): add get_set_tracks tool — BPM/key/LUFS in one call"
```

---

## Task 2: Add `list_set_versions` tool

**Files:**
- Modify: `app/mcp/tools/set.py`
- Modify: `app/mcp/types/workflows.py`
- Test: `tests/mcp/test_set_tools.py`

### Step 1: Write the failing test

```python
async def test_list_set_versions_returns_versions(client, db_set_with_tracks):
    """list_set_versions returns version_id, track_count, score for each version."""
    set_id, _ = db_set_with_tracks
    # Call via MCP E2E pattern from test_e2e_dj_tools.py
    # Expect: list of versions with version_id, track_count >= 0
    pass
```

### Step 2: Add `SetVersionSummary` to `app/mcp/types/workflows.py`

```python
class SetVersionSummary(BaseModel):
    """Summary of a single DJ set version."""

    version_id: int
    version_label: str | None = None
    created_at: str | None = None  # ISO 8601
    track_count: int = 0
    score: float | None = None
```

Add to `__all__`.

### Step 3: Add `list_set_versions` tool to `app/mcp/tools/set.py`

Add inside `register_set_tools()`:

```python
@mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True})
async def list_set_versions(
    set_ref: str | int,
    session: AsyncSession = Depends(get_session),
) -> list[SetVersionSummary]:
    """List all versions of a DJ set with date, score, and track count.

    Most recent version is last. Use version_id from here to pass to
    score_transitions, get_set_tracks, deliver_set, etc.

    Args:
        set_ref: DJ set ref (int, "42", or "local:42").
    """
    from app.mcp.types import SetVersionSummary

    ref = parse_ref(str(set_ref))
    if ref.ref_type != RefType.LOCAL or ref.local_id is None:
        return []

    svc = _make_svc(session)
    versions = await svc.list_versions(ref.local_id)
    if not versions.items:
        return []

    result: list[SetVersionSummary] = []
    for v in sorted(versions.items, key=lambda x: x.set_version_id):
        items_list = await svc.list_items(v.set_version_id, offset=0, limit=500)
        created = v.created_at.isoformat() if v.created_at else None
        result.append(
            SetVersionSummary(
                version_id=v.set_version_id,
                version_label=v.version_label,
                created_at=created,
                track_count=items_list.total,
                score=v.score,
            )
        )
    return result
```

**Verify schema:** Check `app/schemas/sets.py` and `app/models/sets.py` for actual field names of `DjSetVersion` (look for `score`, `version_label`, `created_at`).

### Step 4: Run tests + lint + mypy

```bash
uv run pytest tests/mcp/ -v
uv run ruff check app/mcp/tools/set.py app/mcp/types/workflows.py
uv run mypy app/mcp/tools/set.py
```

### Step 5: Commit

```bash
git add app/mcp/tools/set.py app/mcp/types/workflows.py app/mcp/types/__init__.py
git commit -m "feat(mcp): add list_set_versions tool"
```

---

## Task 3: Extend `TransitionScoreResult` with audio features fields

**Files:**
- Modify: `app/mcp/types/workflows.py`
- Modify: `app/mcp/tools/setbuilder.py` (score_transitions implementation)
- Modify: `app/mcp/tools/delivery.py` (_score_version helper)
- Test: `tests/mcp/test_e2e_dj_tools.py` (add assertion on new fields)

**Why:** After `score_transitions`, you currently need to call `get_features` twice per transition to know the BPM delta and Camelot distance. Adding these directly eliminates 2*(N-1) tool calls.

### Step 1: Write the failing test

In `tests/mcp/test_e2e_dj_tools.py`, find the `score_transitions` test and add:

```python
# After getting TransitionScoreResult list:
# Each result should have from_bpm, to_bpm fields (may be None if no features)
for tx in transitions:
    # Structural check: new fields must exist in response
    assert "from_bpm" in tx or tx.get("from_bpm") is None  # field must be present
    assert "bpm_delta" in tx
    assert "camelot_distance" in tx
```

### Step 2: Add fields to `TransitionScoreResult` in `app/mcp/types/workflows.py`

Add after existing fields:

```python
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
    # New fields: audio context (None when features unavailable)
    from_bpm: float | None = None
    to_bpm: float | None = None
    from_key: str | None = None   # Camelot e.g. "8A"
    to_key: str | None = None
    camelot_distance: int | None = None  # 0-6 (0=same, 6=worst)
    bpm_delta: float | None = None       # abs(from_bpm - to_bpm)
```

### Step 3: Update `score_transitions` in `app/mcp/tools/setbuilder.py`

In the section where features are fetched for transition type recommendation (already done in the try block), extend to also populate the new fields.

Find the block:
```python
try:
    feat_a_raw = await features_svc.get_latest(from_item.track_id)
    feat_b_raw = await features_svc.get_latest(to_item.track_id)
    ...
    cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)
    rec = recommend_transition(...)
    rec_type = str(rec.transition_type)
    rec_confidence = rec.confidence
    rec_reason = rec.reason
    rec_alt = str(rec.alt_type) if rec.alt_type else None
except (NotFoundError, ValueError):
    pass
```

Extend to also capture:
```python
# Add these variables before the try block:
from_bpm_val: float | None = None
to_bpm_val: float | None = None
from_key_val: str | None = None
to_key_val: str | None = None
cam_dist_val: int | None = None
bpm_delta_val: float | None = None

try:
    feat_a_raw = await features_svc.get_latest(from_item.track_id)
    feat_b_raw = await features_svc.get_latest(to_item.track_id)
    tf_a = orm_features_to_track_features(feat_a_raw)
    tf_b = orm_features_to_track_features(feat_b_raw)
    cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)
    rec = recommend_transition(tf_a, tf_b, camelot_compatible=cam_dist <= 1)
    rec_type = str(rec.transition_type)
    rec_confidence = rec.confidence
    rec_reason = rec.reason
    rec_alt = str(rec.alt_type) if rec.alt_type else None
    # Populate new fields
    from_bpm_val = tf_a.bpm
    to_bpm_val = tf_b.bpm
    with contextlib.suppress(ValueError):
        from_key_val = key_code_to_camelot(tf_a.key_code)
        to_key_val = key_code_to_camelot(tf_b.key_code)
    cam_dist_val = cam_dist
    if tf_a.bpm and tf_b.bpm:
        bpm_delta_val = abs(tf_a.bpm - tf_b.bpm)
except (NotFoundError, ValueError):
    pass
```

Then in `results.append(TransitionScoreResult(...))`, add:
```python
from_bpm=from_bpm_val,
to_bpm=to_bpm_val,
from_key=from_key_val,
to_key=to_key_val,
camelot_distance=cam_dist_val,
bpm_delta=bpm_delta_val,
```

Add imports at top of `setbuilder.py`:
```python
import contextlib
from app.utils.audio.camelot import key_code_to_camelot
```

### Step 4: Update `_score_version` helper in `app/mcp/tools/delivery.py`

Same pattern — the helper has a smaller try block. Add the same new variable initialization + population pattern. The `_score_version` helper doesn't return `from_bpm` etc to the cheat sheet (which uses its own data), so the new fields will just be present in the `DeliveryResult.transitions` data.

### Step 5: Run full test suite

```bash
uv run pytest tests/ -v
```

Expected: All passing. If `TransitionScoreResult` serialization tests exist, they should still pass since new fields have defaults of `None`.

### Step 6: Lint + type check

```bash
uv run ruff check app/mcp/tools/setbuilder.py app/mcp/tools/delivery.py app/mcp/types/workflows.py
uv run mypy app/mcp/tools/setbuilder.py app/mcp/tools/delivery.py app/mcp/types/workflows.py
```

### Step 7: Commit

```bash
git add app/mcp/types/workflows.py app/mcp/tools/setbuilder.py app/mcp/tools/delivery.py
git commit -m "feat(mcp): extend TransitionScoreResult with from_bpm/to_bpm/key/camelot_distance"
```

---

## Task 4: Add `get_set_cheat_sheet` tool (structured + text)

**Files:**
- Modify: `app/mcp/types/workflows.py`
- Create: `app/mcp/tools/cheat_sheet.py` (or add to `set.py`)
- Modify: `app/mcp/tools/__init__.py` (register)
- Modify: `app/mcp/gateway.py` (register)
- Test: `tests/mcp/test_set_tools.py`

**Why:** `deliver_set` writes files to disk and is the only way to get a cheat sheet. Adding `get_set_cheat_sheet` returns the same content as a structured MCP response + text string without file I/O. Ideal for "show me the set" without committing to delivery.

### Step 1: Write the failing test

```python
async def test_get_set_cheat_sheet_returns_text(client, db_set_with_tracks):
    """get_set_cheat_sheet must return text containing BPM and track titles."""
    # Call tool, check result.text contains "BPM ARC" and "CHEAT SHEET"
    pass
```

### Step 2: Add `SetCheatSheet` type to `app/mcp/types/workflows.py`

```python
class SetCheatSheet(BaseModel):
    """Structured cheat sheet for a DJ set version."""

    set_id: int
    version_id: int
    set_name: str
    tracks: list[SetTrackItem]
    transitions: list[TransitionScoreResult]
    summary: TransitionSummary
    bpm_range: tuple[float, float] | None = None
    harmonic_chain: list[str] = []
    duration_min: int = 0
    text: str  # Same content as cheat_sheet.txt (for terminal display / LLM reasoning)
```

Add to `__all__`.

### Step 3: Add `get_set_cheat_sheet` tool

Add inside `register_set_tools()` (or create `app/mcp/tools/cheat_sheet.py`):

```python
@mcp.tool(tags={"set", "setbuilder"}, annotations={"readOnlyHint": True}, timeout=120)
async def get_set_cheat_sheet(
    set_ref: str | int,
    version_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    features_svc: AudioFeaturesService = Depends(get_features_service),
    track_svc: TrackService = Depends(get_track_service),
) -> SetCheatSheet:
    """Get a complete cheat sheet for a set version: tracks + transitions + summary.

    Returns the same content as cheat_sheet.txt but as a structured MCP response
    without writing any files. Use this to inspect a set before running deliver_set.
    version_id defaults to the latest version if not specified.

    Args:
        set_ref: DJ set ref (int, "42", or "local:42").
        version_id: Specific version ID, or None for latest.
    """
    # 1. Get tracks (reuse get_set_tracks logic)
    tracks = await _get_set_tracks_impl(set_ref, version_id, session, features_svc, track_svc)

    # 2. Score transitions (reuse _score_version from delivery.py)
    set_id = resolve_local_id(set_ref, "set")
    svc = _make_svc(session)
    dj_set = await svc.get(set_id)

    if version_id is None:
        versions = await svc.list_versions(set_id)
        version_id = max(v.set_version_id for v in versions.items)

    from app.mcp.tools.delivery import _generate_cheat_sheet, _score_version, _build_transition_summary

    scores = await _score_version(set_id, version_id, svc, features_svc, track_svc)
    summary = _build_transition_summary(scores)

    # 3. Build text
    track_dicts = [
        {
            "position": t.position,
            "track_id": t.track_id,
            "title": t.title,
            "bpm": t.bpm,
            "key": t.key,
            "lufs": t.energy_lufs,
            "duration_s": t.duration_s,
        }
        for t in tracks
    ]
    text = _generate_cheat_sheet(dj_set.name, track_dicts, scores)

    # 4. Derived stats
    bpms = [t.bpm for t in tracks if t.bpm is not None]
    keys = [t.key for t in tracks if t.key is not None]
    total_s = sum(t.duration_s or 0 for t in tracks)

    return SetCheatSheet(
        set_id=set_id,
        version_id=version_id,
        set_name=dj_set.name,
        tracks=tracks,
        transitions=scores,
        summary=summary,
        bpm_range=(min(bpms), max(bpms)) if bpms else None,
        harmonic_chain=keys,
        duration_min=total_s // 60,
        text=text,
    )
```

**Note:** Extract the `get_set_tracks` implementation into a private `_get_set_tracks_impl(...)` helper to avoid calling the tool function directly (FastMCP tools are not directly callable from Python). Alternatively, just duplicate the logic (DRY exception justified since it's ~20 lines).

### Step 4: Register in `app/mcp/tools/__init__.py` and `app/mcp/gateway.py`

Check how other tools are registered (e.g. `register_set_tools` is called from `gateway.py`). If `get_set_cheat_sheet` is added to `register_set_tools`, no change to `__init__.py` is needed.

### Step 5: Run tests

```bash
uv run pytest tests/ -v
```

### Step 6: Lint + mypy

```bash
uv run ruff check app/mcp/tools/set.py app/mcp/types/workflows.py
uv run mypy app/mcp/tools/set.py app/mcp/types/workflows.py
```

### Step 7: Commit

```bash
git add app/mcp/tools/set.py app/mcp/types/workflows.py app/mcp/types/__init__.py
git commit -m "feat(mcp): add get_set_cheat_sheet tool — full set view without file I/O"
```

---

## Task 5: Full test suite + finish

### Step 1: Run full suite

```bash
uv run pytest tests/ -v
```

Expected: all tests pass (same baseline as before: 975+).

### Step 2: Update `.claude/rules/mcp.md` tool table

Add new tools to the tool table in `.claude/rules/mcp.md`:

```markdown
| `get_set_tracks` | set | Returns SetTrackItem list with BPM/key/LUFS + pinned flag |
| `list_set_versions` | set | Returns SetVersionSummary list for all versions |
| `get_set_cheat_sheet` | set/setbuilder | Full set view: tracks + transitions + text |
```

### Step 3: Final commit

```bash
git add .claude/rules/mcp.md
git commit -m "docs: update mcp.md with new set tools"
```

---

## Quick reference: new tools

| Tool | Input | Output | Replaces |
|------|-------|--------|---------|
| `get_set_tracks` | set_ref, version_id? | `list[SetTrackItem]` | N× get_track + N× get_features |
| `list_set_versions` | set_ref | `list[SetVersionSummary]` | Manual get_set + list_items N× |
| `get_set_cheat_sheet` | set_ref, version_id? | `SetCheatSheet` (tracks + transitions + text) | score_transitions + N× get_features + deliver_set |
| `score_transitions` (extended) | set_ref, version_id | `list[TransitionScoreResult]` + from_bpm/to_bpm/key/camelot_distance | Same tool + 2× get_features per transition |

## Post-plan: workflow before vs after

**Before (building and reviewing set 9, version 14):**
```text
get_set → get version_id (1)
score_transitions → get score list, no BPM/key (2)
get_features × 15 → get BPM/key per track (17)
get_track × 15 → get title per track (32)
[mentally join everything]
```

**After:**
```bash
get_set_cheat_sheet → everything in one call (1)
```
