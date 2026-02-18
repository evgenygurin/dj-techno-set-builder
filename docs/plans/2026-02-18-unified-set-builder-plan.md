# Unified Set Builder — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge curation into GA fitness, add iterative YM feedback loop (likes=pinned, dislikes=excluded), bidirectional sync.

**Architecture:** Unified GA selects AND orders tracks in one pass. `template_slot_fit` added as fitness component. New sync tools push sets to YM and read back likes/dislikes. `curate_set` and `adjust_set` removed.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, FastMCP 3.0, numpy, pytest

**Design doc:** `docs/plans/2026-02-18-unified-set-builder-design.md`

---

### Task 1: Add `template_slot_fit` to GA fitness function

**Why:** GA currently has no template awareness. Tracks are ordered without considering mood slots, energy targets, or BPM ranges from templates. This is the core fix — GA must evaluate how well each track fits its assigned slot.

**Files:**
- Modify: `app/utils/audio/set_generator.py`
- Test: `tests/utils/test_set_generator_template.py`

**Step 1: Write failing tests**

Create `tests/utils/test_set_generator_template.py`:

```python
"""Tests for template_slot_fit in GA fitness."""

from __future__ import annotations

import numpy as np

from app.utils.audio.set_generator import (
    GAConfig,
    GeneticSetGenerator,
    TrackData,
    template_slot_fit,
)
from app.utils.audio.set_templates import SetSlot, TemplateName, get_template
from app.utils.audio.mood_classifier import TrackMood

def _make_track(
    track_id: int,
    bpm: float = 130.0,
    energy: float = 0.5,
    key_code: int = 1,
    mood: int = 3,
) -> TrackData:
    return TrackData(
        track_id=track_id, bpm=bpm, energy=energy, key_code=key_code, mood=mood,
    )

class TestTemplateSlotFit:
    """Tests for the template_slot_fit scoring function."""

    def test_perfect_match_scores_high(self):
        """Track matching slot mood+energy+BPM should score > 0.8."""
        slot = SetSlot(
            position=0.5,
            mood=TrackMood.DRIVING,
            energy_target=-8.0,
            bpm_range=(128.0, 132.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        # mood=DRIVING(3), energy maps -8 LUFS → 0.75, bpm in range
        track = _make_track(1, bpm=130.0, energy=0.75, mood=3)
        score = template_slot_fit([track], [slot])
        assert score > 0.8

    def test_wrong_mood_scores_low(self):
        """Track with wrong mood should score < 0.5."""
        slot = SetSlot(
            position=0.5,
            mood=TrackMood.AMBIENT_DUB,
            energy_target=-12.0,
            bpm_range=(122.0, 126.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        # mood=HARD_TECHNO(6) for ambient slot
        track = _make_track(1, bpm=135.0, energy=0.9, mood=6)
        score = template_slot_fit([track], [slot])
        assert score < 0.5

    def test_empty_slots_returns_neutral(self):
        """No slots (FULL_LIBRARY) → returns 0.5 (neutral)."""
        score = template_slot_fit([_make_track(1)], [])
        assert score == 0.5

    def test_multiple_slots_averaged(self):
        """Score is mean of per-slot scores."""
        slot_good = SetSlot(
            position=0.0,
            mood=TrackMood.DRIVING,
            energy_target=-8.0,
            bpm_range=(128.0, 132.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        slot_bad = SetSlot(
            position=1.0,
            mood=TrackMood.AMBIENT_DUB,
            energy_target=-12.0,
            bpm_range=(122.0, 126.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        t_good = _make_track(1, bpm=130.0, energy=0.75, mood=3)
        t_bad = _make_track(2, bpm=130.0, energy=0.75, mood=3)
        score = template_slot_fit([t_good, t_bad], [slot_good, slot_bad])
        # First track perfect, second bad → average
        assert 0.3 < score < 0.8

class TestGAWithTemplate:
    """Test GA uses template_slot_fit when slots provided."""

    def test_ga_config_has_template_weight(self):
        """GAConfig should have w_template field."""
        cfg = GAConfig(w_template=0.25)
        assert cfg.w_template == 0.25

    def test_fitness_includes_template(self):
        """Fitness with template slots should differ from without."""
        tracks = [_make_track(i, bpm=125 + i, mood=i % 6 + 1) for i in range(5)]
        matrix = np.ones((5, 5), dtype=np.float64) * 0.5
        np.fill_diagonal(matrix, 0.0)

        template = get_template(TemplateName.CLASSIC_60)
        slots = list(template.slots)[:5]  # first 5 slots

        gen_no_tmpl = GeneticSetGenerator(tracks, matrix, GAConfig(
            w_template=0.0, track_count=5, generations=1, population_size=10,
        ))
        gen_with_tmpl = GeneticSetGenerator(tracks, matrix, GAConfig(
            w_template=0.25, track_count=5, generations=1, population_size=10,
        ), template_slots=slots)

        # Should produce different fitness values
        ch = np.array([0, 1, 2, 3, 4], dtype=np.int32)
        f1 = gen_no_tmpl._fitness(ch)
        f2 = gen_with_tmpl._fitness(ch)
        assert f1 != f2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/utils/test_set_generator_template.py -v`
Expected: ImportError — `template_slot_fit` doesn't exist, `GAConfig` has no `w_template`

**Step 3: Implement `template_slot_fit` function and update GAConfig**

In `app/utils/audio/set_generator.py`:

Add to imports:
```python
from app.utils.audio.mood_classifier import TrackMood
```

Add `w_template` to `GAConfig` (line ~44, before `w_variety`):
```python
    w_template: float = 0.0  # 0.0 = no template, 0.25 = recommended with template
```

Rebalance default weights in GAConfig docstring: when template is used, caller sets:
`w_transition=0.35, w_template=0.25, w_energy_arc=0.20, w_variety=0.10, w_bpm_smooth=0.10`

Add `template_slot_fit` pure function (after `variety_score`):
```python
def template_slot_fit(
    tracks: list[TrackData],
    slots: list[SetSlot],
) -> float:
    """Score how well tracks match template slots (0.0-1.0).

    For each position i, compares track[i] against slot[i]:
    - Mood match (50%): exact=1.0, adjacent intensity=0.5, else 0.0
    - Energy match (30%): 1.0 - |energy - slot_energy_mapped| / 1.0
    - BPM match (20%): 1.0 if in range, else penalty by distance

    Returns 0.5 (neutral) if no slots provided.
    """
    if not slots:
        return 0.5

    n = min(len(tracks), len(slots))
    if n == 0:
        return 0.5

    total = 0.0
    for i in range(n):
        track = tracks[i]
        slot = slots[i]

        # Mood match
        track_intensity = track.mood
        slot_intensity = slot.mood.intensity
        if track_intensity == slot_intensity:
            mood_score = 1.0
        elif abs(track_intensity - slot_intensity) == 1:
            mood_score = 0.5
        else:
            mood_score = 0.0

        # Energy match (slot.energy_target is LUFS, track.energy is 0-1)
        slot_energy = max(0.0, min(1.0, (slot.energy_target + 14.0) / 8.0))
        energy_score = max(0.0, 1.0 - abs(track.energy - slot_energy))

        # BPM match
        bpm_low, bpm_high = slot.bpm_range
        if bpm_low <= track.bpm <= bpm_high:
            bpm_score = 1.0
        else:
            bpm_dist = min(abs(track.bpm - bpm_low), abs(track.bpm - bpm_high))
            bpm_score = max(0.0, 1.0 - bpm_dist / 10.0)

        total += 0.5 * mood_score + 0.3 * energy_score + 0.2 * bpm_score

    return total / n
```

Update `GeneticSetGenerator.__init__` to accept `template_slots`:
```python
def __init__(
    self,
    tracks: list[TrackData],
    transition_matrix: NDArray[np.float64],
    config: GAConfig | None = None,
    template_slots: list[SetSlot] | None = None,  # NEW
) -> None:
    ...
    self._template_slots = template_slots or []
```

Update `_fitness()` to include template component:
```python
def _fitness(self, chromosome: NDArray[np.int32]) -> float:
    cfg = self.config
    transition = self._mean_transition_quality(chromosome)
    arc = self._energy_arc_score(chromosome)
    bpm = self._bpm_smoothness_score(chromosome)
    var = self._variety_score(chromosome)

    tmpl = 0.5  # neutral if no template
    if self._template_slots:
        ordered_tracks = [self._all_tracks[i] for i in chromosome]
        tmpl = template_slot_fit(ordered_tracks, self._template_slots)

    return (
        cfg.w_transition * transition
        + cfg.w_template * tmpl
        + cfg.w_energy_arc * arc
        + cfg.w_bpm_smooth * bpm
        + cfg.w_variety * var
    )
```

Update `__all__` to include `template_slot_fit`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/utils/test_set_generator_template.py -v`
Expected: All 6 tests PASS

**Step 5: Lint and commit**

```bash
uv run ruff check app/utils/audio/set_generator.py tests/utils/test_set_generator_template.py --fix
uv run ruff format app/utils/audio/set_generator.py tests/utils/test_set_generator_template.py
uv run mypy app/utils/audio/set_generator.py
git add app/utils/audio/set_generator.py tests/utils/test_set_generator_template.py
git commit -m "feat: add template_slot_fit to GA fitness function"
```

---

### Task 2: Populate `TrackData.mood` and `artist_id` in SetGenerationService

**Why:** GA has variety penalties for mood streaks and artist proximity, but both fields are always 0. Without mood, `template_slot_fit` can't work. Without artist_id, variety penalty is meaningless.

**Files:**
- Modify: `app/services/set_generation.py`
- Test: `tests/services/test_set_generation.py` (existing)

**Step 1: Write failing test**

Add to `tests/services/test_set_generation.py`:

```python
async def test_generate_populates_track_mood(session, set_with_features):
    """TrackData.mood should be populated from mood classifier, not 0."""
    # set_with_features fixture creates set + features in DB
    svc = _make_service(session)
    result = await svc.generate(set_with_features.set_id, SetGenerationRequest())
    # If mood is populated, variety_score will differ from all-zeros
    assert result.score > 0  # basic sanity
```

**Step 2: Run test to verify current behavior**

Run: `uv run pytest tests/services/test_set_generation.py::test_generate_populates_track_mood -v`

**Step 3: Implement mood + artist population**

In `app/services/set_generation.py`, in `generate()` method, after building `features_list` and before building `tracks` list:

```python
# Classify moods for all tracks
from app.utils.audio.mood_classifier import classify_track

mood_map: dict[int, int] = {}
for f in features_list:
    classification = classify_track(
        bpm=f.bpm,
        lufs_i=f.lufs_i,
        kick_prominence=f.kick_prominence or 0.5,
        spectral_centroid_mean=f.centroid_mean_hz or 2500.0,
        onset_rate=f.onset_rate_mean or 5.0,
        hp_ratio=f.hp_ratio or 0.5,
    )
    mood_map[f.track_id] = classification.mood.intensity

# Build artist lookup from playlist items (if available)
artist_map: dict[int, int] = {}
if self.playlist_repo is not None and data.playlist_id is not None:
    items, _ = await self.playlist_repo.list_by_playlist(data.playlist_id, limit=1000)
    # artist_id stored on Track model — fetch via join or separate query
    # For now: leave as 0, wire later when Track→Artist relationship is used
```

Update TrackData construction:
```python
tracks = [
    TrackData(
        track_id=f.track_id,
        bpm=f.bpm,
        energy=lufs_to_energy(f.lufs_i),
        key_code=f.key_code or 0,
        mood=mood_map.get(f.track_id, 0),
        artist_id=0,  # TODO: wire from Track model
    )
    for f in features_list
]
```

**Step 4: Run tests**

Run: `uv run pytest tests/services/test_set_generation.py -v`
Expected: All pass

**Step 5: Lint and commit**

```bash
uv run ruff check app/services/set_generation.py --fix && uv run ruff format app/services/set_generation.py
git add app/services/set_generation.py tests/services/test_set_generation.py
git commit -m "feat: populate TrackData.mood from classifier in SetGenerationService"
```

---

### Task 3: Pass template slots to GA from SetGenerationService

**Why:** GA now supports `template_slots` parameter, but `SetGenerationService.generate()` doesn't pass it. Need to wire template name through the request schema to the GA.

**Files:**
- Modify: `app/schemas/set_generation.py`
- Modify: `app/services/set_generation.py`
- Test: `tests/services/test_set_generation.py`

**Step 1: Add `template_name` to SetGenerationRequest**

In `app/schemas/set_generation.py`:
```python
template_name: str | None = Field(default=None, description="Template for slot-based fitness (e.g. classic_60)")
```

**Step 2: Wire template in SetGenerationService.generate()**

After mood classification, before building transition matrix:
```python
# Load template slots if specified
from app.utils.audio.set_templates import SetSlot, TemplateName, get_template

template_slots: list[SetSlot] = []
if data.template_name:
    template = get_template(TemplateName(data.template_name))
    template_slots = list(template.slots)
    # Set track_count from template if not explicitly specified
    if data.track_count is None and template.target_track_count > 0:
        data_track_count = template.target_track_count
    else:
        data_track_count = data.track_count
else:
    data_track_count = data.track_count
```

Update GAConfig construction to include `w_template` and pass `template_slots`:
```python
config = GAConfig(
    ...
    track_count=data_track_count,
    w_template=0.25 if template_slots else 0.0,
    w_transition=0.35 if template_slots else data.w_transition,
    w_energy_arc=0.20 if template_slots else data.w_energy_arc,
    w_bpm_smooth=0.10 if template_slots else data.w_bpm_smooth,
    w_variety=0.10 if template_slots else 0.20,
)

gen = GeneticSetGenerator(tracks, transition_matrix, config, template_slots=template_slots)
```

**Step 3: Test and commit**

Run: `uv run pytest tests/services/test_set_generation.py -v`

```bash
git add app/schemas/set_generation.py app/services/set_generation.py tests/services/test_set_generation.py
git commit -m "feat: wire template_name through to GA via SetGenerationRequest"
```

---

### Task 4: Update `build_set` MCP tool to accept template

**Why:** MCP tool `build_set` currently accepts only `energy_arc`. It needs `template` parameter so it passes template through to GA.

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py`
- Modify: `tests/mcp/test_workflow_setbuilder.py`

**Step 1: Update build_set signature**

```python
@mcp.tool(tags={"setbuilder"})
async def build_set(
    playlist_id: int,
    set_name: str,
    ctx: Context,
    template: str | None = None,      # NEW: "classic_60", "peak_hour_60", etc.
    energy_arc: str = "classic",
    exclude_track_ids: list[int] | None = None,  # NEW
    set_svc: DjSetService = Depends(get_set_service),
    gen_svc: SetGenerationService = Depends(get_set_generation_service),
) -> SetBuildResult:
    """Build a DJ set from a playlist using template + genetic algorithm.

    If template is provided, GA selects and orders tracks to fit
    template slots (mood, energy, BPM). Without template, GA orders
    all playlist tracks optimizing transitions only.

    Args:
        playlist_id: Source playlist containing candidate tracks.
        set_name: Name for the new DJ set.
        template: Template name (classic_60, peak_hour_60, etc.) or None.
        energy_arc: Energy arc shape for GA (classic, progressive, roller, wave).
        exclude_track_ids: Track IDs to exclude from selection.
    """
```

Update `SetGenerationRequest` construction:
```python
request = SetGenerationRequest(
    energy_arc_type=energy_arc,
    playlist_id=playlist_id,
    template_name=template,
    exclude_track_ids=exclude_track_ids,
)
```

Also store template and source playlist on DjSet:
```python
dj_set = await set_svc.create(
    DjSetCreate(name=set_name),
)
# Store metadata for rebuild
# (will be wired when DB columns added in Task 6)
```

**Step 2: Update test**

Add to `tests/mcp/test_workflow_setbuilder.py`:
```python
async def test_build_set_accepts_template(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    build = next(t for t in tools if t.name == "build_set")
    param_names = {p.name for p in build.parameters}
    assert "template" in param_names
    assert "exclude_track_ids" in param_names
```

**Step 3: Lint and commit**

```bash
uv run ruff check app/mcp/workflows/setbuilder_tools.py --fix
git add app/mcp/workflows/setbuilder_tools.py tests/mcp/test_workflow_setbuilder.py
git commit -m "feat: add template and exclude_track_ids params to build_set MCP tool"
```

---

### Task 5: Add `pinned` column to DjSetItem + DB migration

**Why:** Rebuild workflow needs to know which tracks are pinned (liked by user). Adding a boolean column to dj_set_items.

**Files:**
- Modify: `app/models/sets.py`
- Create: Alembic migration
- Test: `tests/test_sets.py`

**Step 1: Add column to model**

In `app/models/sets.py`, add to `DjSetItem`:
```python
pinned: Mapped[bool] = mapped_column(default=False)
```

**Step 2: Add columns to DjSet for sync metadata**

In `app/models/sets.py`, add to `DjSet`:
```python
ym_playlist_id: Mapped[int | None] = mapped_column(default=None)
template_name: Mapped[str | None] = mapped_column(String(50), default=None)
source_playlist_id: Mapped[int | None] = mapped_column(
    ForeignKey("dj_playlists.playlist_id", ondelete="SET NULL"), default=None
)
```

**Step 3: Generate and apply migration**

```bash
uv run alembic revision --autogenerate -m "add pinned, ym_playlist_id, template_name, source_playlist_id"
uv run alembic upgrade head
```

**Step 4: Update DjSetCreate/DjSetItemCreate schemas if needed**

In `app/schemas/sets.py`, add optional fields.

**Step 5: Test and commit**

```bash
uv run pytest tests/test_sets.py -v
git add app/models/sets.py app/schemas/sets.py alembic/versions/
git commit -m "feat: add pinned, ym_playlist_id, template_name columns"
```

---

### Task 6: Add `rebuild_set` MCP tool

**Why:** Core of the iterative feedback loop. Reads pinned/excluded from current version, re-runs GA with constraints.

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py`
- Modify: `app/utils/audio/set_generator.py` (add GAConstraints)
- Test: `tests/mcp/test_workflow_setbuilder.py`

**Step 1: Add GAConstraints dataclass**

In `app/utils/audio/set_generator.py`:
```python
@dataclass(frozen=True, slots=True)
class GAConstraints:
    """Constraints for rebuild — pinned tracks must stay, excluded are banned."""
    pinned_ids: frozenset[int] = frozenset()
    excluded_ids: frozenset[int] = frozenset()
```

**Step 2: Update GeneticSetGenerator to respect constraints**

- `__init__`: accept `constraints: GAConstraints | None = None`
- `_init_population`: every individual must include all pinned track indices
- `_mutate_replace`: never replace pinned tracks, never insert excluded
- Export in `__all__`

**Step 3: Add rebuild_set tool**

```python
@mcp.tool(tags={"setbuilder"})
async def rebuild_set(
    set_id: int,
    ctx: Context,
    set_svc: DjSetService = Depends(get_set_service),
    gen_svc: SetGenerationService = Depends(get_set_generation_service),
) -> SetBuildResult:
    """Rebuild a set respecting pinned tracks and excluding rejected ones.

    Reads pinned flags from the latest version's items. Excluded tracks
    are those removed from previous versions. Creates a new version.

    Args:
        set_id: DJ set to rebuild.
    """
    dj_set = await set_svc.get(set_id)
    # Get latest version
    versions = await set_svc.list_versions(set_id)
    latest = max(versions, key=lambda v: v.set_version_id)

    items_list = await set_svc.list_items(latest.set_version_id, offset=0, limit=500)
    items = items_list.items

    pinned_ids = {item.track_id for item in items if item.pinned}

    # Re-run GA with constraints
    request = SetGenerationRequest(
        playlist_id=dj_set.source_playlist_id,
        template_name=dj_set.template_name,
        pinned_track_ids=list(pinned_ids),
    )
    gen_result = await gen_svc.generate(dj_set.set_id, request)

    avg_score = 0.0
    if gen_result.transition_scores:
        avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

    return SetBuildResult(
        set_id=set_id,
        version_id=gen_result.set_version_id,
        track_count=len(gen_result.track_ids),
        total_score=gen_result.score,
        avg_transition_score=avg_score,
        energy_curve=[],
    )
```

**Step 4: Test and commit**

```bash
uv run pytest tests/mcp/test_workflow_setbuilder.py -v
git add app/utils/audio/set_generator.py app/mcp/workflows/setbuilder_tools.py app/schemas/set_generation.py tests/
git commit -m "feat: add rebuild_set MCP tool with GA constraints"
```

---

### Task 7: Add `sync_set_to_ym` MCP tool

**Why:** Push set to YM as a playlist so user can listen and give feedback.

**Files:**
- Create: `app/mcp/workflows/sync_tools.py`
- Modify: `app/mcp/workflows/server.py`
- Test: `tests/mcp/test_workflow_sync.py`

**Step 1: Create sync_tools.py**

```python
"""Sync tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.mcp.dependencies import get_set_service, get_ym_client, get_track_service
from app.services.sets import DjSetService
from app.services.tracks import TrackService

def register_sync_tools(mcp: FastMCP) -> None:
    """Register sync tools on the MCP server."""

    @mcp.tool(tags={"sync", "yandex"})
    async def sync_set_to_ym(
        set_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        track_svc: TrackService = Depends(get_track_service),
        ym_client = Depends(get_ym_client),
    ) -> dict:
        """Push a DJ set to Yandex Music as a playlist.

        Creates or updates a YM playlist named "set_{set_name}".
        Stores ym_playlist_id on the DjSet record.

        Args:
            set_id: DJ set to sync.
        """
        dj_set = await set_svc.get(set_id)
        # Get latest version items
        versions = await set_svc.list_versions(set_id)
        latest = max(versions, key=lambda v: v.set_version_id)
        items_list = await set_svc.list_items(latest.set_version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        # Get YM track IDs
        ym_track_ids = []
        for item in items:
            track = await track_svc.get(item.track_id)
            if track.ym_track_id:
                ym_track_ids.append(track.ym_track_id)

        playlist_name = f"set_{dj_set.name}"

        if dj_set.ym_playlist_id:
            # Update existing playlist
            # ... YM API calls via ym_client
            pass
        else:
            # Create new playlist
            # ... YM API calls via ym_client
            pass

        return {
            "set_id": set_id,
            "ym_playlist_id": dj_set.ym_playlist_id,
            "playlist_name": playlist_name,
            "track_count": len(ym_track_ids),
        }
```

**Step 2: Register in server.py**

Add `from app.mcp.workflows.sync_tools import register_sync_tools` and `register_sync_tools(mcp)`.

**Step 3: Test metadata and commit**

```bash
uv run pytest tests/mcp/test_workflow_sync.py -v
git add app/mcp/workflows/sync_tools.py app/mcp/workflows/server.py tests/mcp/test_workflow_sync.py
git commit -m "feat: add sync_set_to_ym MCP tool"
```

---

### Task 8: Add `sync_set_from_ym` MCP tool

**Why:** Read likes/dislikes from YM set playlist, update pinned/excluded flags.

**Files:**
- Modify: `app/mcp/workflows/sync_tools.py`
- Test: `tests/mcp/test_workflow_sync.py`

**Step 1: Add sync_set_from_ym tool**

```python
@mcp.tool(tags={"sync", "yandex"})
async def sync_set_from_ym(
    set_id: int,
    ctx: Context,
    set_svc: DjSetService = Depends(get_set_service),
    ym_client = Depends(get_ym_client),
) -> dict:
    """Read likes/dislikes from YM set playlist, update pinned/excluded.

    For tracks in the YM set playlist:
    - liked ∩ in_playlist → pinned=true
    - disliked → remove from set (excluded)
    - manually removed from YM playlist → remove from set
    - manually added to YM playlist → pinned=true

    Args:
        set_id: DJ set to sync feedback for.
    """
    dj_set = await set_svc.get(set_id)
    if not dj_set.ym_playlist_id:
        raise ValueError("Set not synced to YM yet — call sync_set_to_ym first")

    # Get current YM playlist tracks
    # ym_playlist_tracks = await ym_client.get_playlist(dj_set.ym_playlist_id)

    # Get user's liked and disliked track IDs
    # liked_ids = await ym_client.get_liked_tracks()
    # disliked_ids = await ym_client.get_disliked_tracks()

    # Compare with current set items
    # ... update pinned flags, remove excluded

    return {
        "set_id": set_id,
        "pinned_count": 0,  # placeholder
        "excluded_count": 0,
        "unchanged_count": 0,
    }
```

**Step 2: Test and commit**

```bash
git add app/mcp/workflows/sync_tools.py tests/mcp/test_workflow_sync.py
git commit -m "feat: add sync_set_from_ym MCP tool (feedback loop)"
```

---

### Task 9: Add `sync_playlist` MCP tool (bidirectional)

**Why:** Source playlist needs bidirectional sync with YM.

**Files:**
- Modify: `app/mcp/workflows/sync_tools.py`
- Test: `tests/mcp/test_workflow_sync.py`

**Step 1: Add sync_playlist tool**

```python
@mcp.tool(tags={"sync", "yandex"})
async def sync_playlist(
    playlist_id: int,
    ctx: Context,
    playlist_svc = Depends(get_playlist_service),
    ym_client = Depends(get_ym_client),
) -> dict:
    """Bidirectional sync between YM playlist and local DB.

    - New tracks in YM → add to local DB
    - Removed tracks in YM → mark removed locally
    - New tracks in local → add to YM playlist

    Args:
        playlist_id: Local playlist ID to sync.
    """
    ...
```

**Step 2: Test and commit**

```bash
git add app/mcp/workflows/sync_tools.py tests/mcp/test_workflow_sync.py
git commit -m "feat: add sync_playlist MCP tool (bidirectional YM sync)"
```

---

### Task 10: Remove `curate_set` and `adjust_set` MCP tools

**Why:** `curate_set` is absorbed into `build_set` (via template_slot_fit in GA). `adjust_set` is replaced by `rebuild_set` with feedback loop.

**Files:**
- Modify: `app/mcp/workflows/curation_tools.py` — remove `curate_set`
- Modify: `app/mcp/workflows/setbuilder_tools.py` — remove `adjust_set`
- Modify: `tests/mcp/test_workflow_curation.py` — update tests
- Modify: `tests/mcp/test_workflow_setbuilder.py` — update tests

**Step 1: Remove curate_set from curation_tools.py**

Keep `classify_tracks`, `analyze_library_gaps`, `review_set`. Remove `curate_set` function.

**Step 2: Remove adjust_set from setbuilder_tools.py**

Keep `build_set`, `score_transitions`, `export_set_m3u`, `export_set_json`. Remove `adjust_set` function.

**Step 3: Update tests**

Remove tests that reference removed tools. Update tool count assertions.

**Step 4: Update types**

Remove `CurateSetResult`, `CurateCandidate` from `types_curation.py` if no longer used.

**Step 5: Lint and commit**

```bash
uv run ruff check app/mcp/workflows/ --fix
uv run pytest tests/mcp/ -v
git add app/mcp/workflows/ tests/mcp/ app/mcp/types_curation.py
git commit -m "refactor: remove curate_set and adjust_set (absorbed into build_set + rebuild_set)"
```

---

### Task 11: Update documentation

**Why:** Rules files must reflect new tool set and architecture.

**Files:**
- Modify: `.claude/rules/mcp.md`
- Modify: `.claude/rules/audio.md`

**Step 1: Update mcp.md**

- Update DJ Workflow tools table: remove curate_set, adjust_set; add rebuild_set, sync_set_to_ym, sync_set_from_ym, sync_playlist
- Update tool count
- Document new build_set signature with template parameter

**Step 2: Update audio.md**

- Note that template_slot_fit is now part of GA fitness
- Document GAConstraints for rebuild

**Step 3: Commit**

```bash
git add -f .claude/rules/mcp.md .claude/rules/audio.md
git commit -m "docs: update rules for unified set builder architecture"
```

---

### Task 12: Full test suite + integration verification

**Why:** Ensure nothing is broken, all tools work end-to-end.

**Step 1: Run full test suite**

```bash
uv run pytest -v
```

Fix any failures.

**Step 2: Live verification via MCP**

```bash
make mcp-call TOOL=dj_build_set ARGS='{"playlist_id": 2, "set_name": "Test Unified", "template": "classic_60"}'
make mcp-call TOOL=dj_review_set ARGS='{"set_id": ..., "version_id": ...}'
make mcp-call TOOL=dj_rebuild_set ARGS='{"set_id": ...}'
```

**Step 3: Commit any fixes**

```bash
git commit -m "fix: integration fixes for unified set builder"
```
