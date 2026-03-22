# Set Generation Bug Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two bugs — playlist scoping (`build_set` ignores `playlist_id`) and structure scoring always returning 0.5 due to missing section data.

**Architecture:** Approach B (Comprehensive) — fix both bugs in all entry points: GA matrix building (`SetGenerationService`) and live scoring (`UnifiedTransitionScoringService`). New dependencies injected via optional constructor params (backward compatible).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), FastMCP 3.0, pytest-asyncio (auto mode)

**Design doc:** `docs/plans/2026-02-17-set-generation-bugs-design.md`

---

## Task 1: Add `playlist_id` to `SetGenerationRequest` schema

**Files:**
- Modify: `app/schemas/set_generation.py`

**Step 1: Add `playlist_id` field**

In `app/schemas/set_generation.py`, after `seed: int | None`, add:

```python
playlist_id: int | None = Field(default=None, description="Filter tracks to this playlist (None = all tracks)")
```

**Step 2: Verify no existing tests break**

```bash
uv run pytest tests/ -k "set_generation" -v
```

Expected: all pass (new field has default `None` — backward compatible).

**Step 3: Commit**

```bash
git add app/schemas/set_generation.py
git commit -m "feat(BPM-XX): add playlist_id field to SetGenerationRequest"
```

---

## Task 2: Update `orm_features_to_track_features()` to accept sections

**Files:**
- Modify: `app/utils/audio/feature_conversion.py`
- Create: `tests/utils/test_feature_conversion.py`

**Step 1: Write failing tests**

Create `tests/utils/test_feature_conversion.py`:

```python
"""Tests for orm_features_to_track_features() with sections parameter."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.utils.audio.feature_conversion import orm_features_to_track_features

def _make_feat(**overrides: object) -> MagicMock:
    """Create a minimal TrackAudioFeaturesComputed mock."""
    feat = MagicMock()
    feat.bpm = 128.0
    feat.lufs_i = -14.0
    feat.key_code = 0
    feat.chroma_entropy = 0.7
    feat.key_confidence = None
    feat.low_energy = 0.3
    feat.mid_energy = 0.5
    feat.high_energy = 0.2
    feat.mfcc_vector = None
    feat.centroid_mean_hz = 2000.0
    feat.onset_rate_mean = 5.0
    feat.kick_prominence = 0.5
    feat.hnr_mean_db = 0.0
    feat.slope_db_per_oct = 0.0
    feat.hp_ratio = 0.5
    for k, v in overrides.items():
        setattr(feat, k, v)
    return feat

def _make_section(section_type: int, start_ms: int, end_ms: int) -> MagicMock:
    """Create a minimal TrackSection mock."""
    sec = MagicMock()
    sec.section_type = section_type
    sec.start_ms = start_ms
    sec.end_ms = end_ms
    return sec

# SectionType int values: 0=intro, 1=buildup, 2=drop, 3=breakdown, 4=outro
INTRO_TYPE = 0
OUTRO_TYPE = 4
BUILDUP_TYPE = 1

def test_no_sections_gives_none_fields() -> None:
    """Regression: without sections, first/last remain None."""
    feat = _make_feat()
    tf = orm_features_to_track_features(feat, sections=None)
    assert tf.first_section is None
    assert tf.last_section is None

def test_sections_populated_intro_outro() -> None:
    """intro→outro pair maps to correct first/last section names."""
    feat = _make_feat()
    intro = _make_section(INTRO_TYPE, start_ms=0, end_ms=32000)
    outro = _make_section(OUTRO_TYPE, start_ms=180000, end_ms=210000)
    tf = orm_features_to_track_features(feat, sections=[outro, intro])  # deliberately reversed order
    assert tf.first_section == "intro"
    assert tf.last_section == "outro"

def test_sections_sorted_by_start_ms() -> None:
    """Sections should be sorted by start_ms regardless of input order."""
    feat = _make_feat()
    buildup = _make_section(BUILDUP_TYPE, start_ms=30000, end_ms=60000)
    intro = _make_section(INTRO_TYPE, start_ms=0, end_ms=30000)
    tf = orm_features_to_track_features(feat, sections=[buildup, intro])
    assert tf.first_section == "intro"
    assert tf.last_section == "buildup"

def test_invalid_section_type_silently_ignored() -> None:
    """Unknown section_type int (e.g. 99) should not raise — fields stay None."""
    feat = _make_feat()
    invalid = _make_section(99, start_ms=0, end_ms=30000)
    tf = orm_features_to_track_features(feat, sections=[invalid])
    assert tf.first_section is None
    assert tf.last_section is None

def test_empty_sections_list_gives_none() -> None:
    """Empty list should behave like None."""
    feat = _make_feat()
    tf = orm_features_to_track_features(feat, sections=[])
    assert tf.first_section is None
    assert tf.last_section is None
```

**Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/utils/test_feature_conversion.py -v
```

Expected: `TypeError: orm_features_to_track_features() got an unexpected keyword argument 'sections'`

**Step 3: Implement the sections parameter**

Edit `app/utils/audio/feature_conversion.py`. Replace the current function signature and body:

```python
"""Convert ORM audio features to TransitionScoringService TrackFeatures.

Single source of truth — every call-site that needs ORM → TrackFeatures
must go through this function to prevent drift between scoring paths.
"""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING

from app.models.enums import SectionType
from app.services.transition_scoring import TrackFeatures

if TYPE_CHECKING:
    from app.models.features import TrackAudioFeaturesComputed
    from app.models.sections import TrackSection

def orm_features_to_track_features(
    feat: TrackAudioFeaturesComputed,
    sections: list[TrackSection] | None = None,
) -> TrackFeatures:
    """Convert ``TrackAudioFeaturesComputed`` ORM row to ``TrackFeatures``.

    Mapping rules:
    * ``harmonic_density`` ← ``chroma_entropy`` (fallback: ``key_confidence``)
    * ``band_ratios`` ← normalised ``[low_energy, mid_energy, high_energy]``
    * ``onset_rate`` ← ``onset_rate_mean`` (Phase-2 field, fallback = 5.0)
    * ``mfcc_vector`` ← JSON-parsed ``mfcc_vector`` (Phase-2, nullable)
    * ``kick_prominence`` ← ``kick_prominence`` (Phase-2, fallback = 0.5)
    * ``hnr_db`` ← ``hnr_mean_db`` (Phase-2, fallback = 0.0)
    * ``spectral_slope`` ← ``slope_db_per_oct`` (Phase-2, fallback = 0.0)
    * ``first_section`` / ``last_section`` ← sorted ``sections`` list (optional)
    """
    # Harmonic density: prefer chroma_entropy, fallback to key_confidence
    harmonic_density: float
    if feat.chroma_entropy is not None:
        harmonic_density = feat.chroma_entropy
    else:
        harmonic_density = feat.key_confidence or 0.5

    low = feat.low_energy or 0.33
    mid = feat.mid_energy or 0.33
    high = feat.high_energy or 0.34
    total = low + mid + high
    band_ratios = [low / total, mid / total, high / total] if total > 0 else [0.33, 0.33, 0.34]

    # MFCC: parse JSON string if available
    mfcc_vector: list[float] | None = None
    if feat.mfcc_vector:
        mfcc_vector = _json.loads(feat.mfcc_vector)

    # Section data: derive first/last section type names for structure scoring
    first_section: str | None = None
    last_section: str | None = None
    if sections:
        sorted_secs = sorted(sections, key=lambda s: s.start_ms)
        try:
            first_section = SectionType(sorted_secs[0].section_type).name.lower()
        except ValueError:
            pass
        try:
            last_section = SectionType(sorted_secs[-1].section_type).name.lower()
        except ValueError:
            pass

    return TrackFeatures(
        bpm=feat.bpm,
        energy_lufs=feat.lufs_i,
        key_code=feat.key_code if feat.key_code is not None else 0,
        harmonic_density=harmonic_density,
        centroid_hz=feat.centroid_mean_hz or 2000.0,
        band_ratios=band_ratios,
        onset_rate=feat.onset_rate_mean or 5.0,
        mfcc_vector=mfcc_vector,
        kick_prominence=feat.kick_prominence if feat.kick_prominence is not None else 0.5,
        hnr_db=feat.hnr_mean_db if feat.hnr_mean_db is not None else 0.0,
        spectral_slope=feat.slope_db_per_oct if feat.slope_db_per_oct is not None else 0.0,
        hp_ratio=feat.hp_ratio if feat.hp_ratio is not None else 0.5,
        first_section=first_section,
        last_section=last_section,
    )
```

**Step 4: Check `SectionType` exists in `app/models/enums.py`**

```bash
uv run python -c "from app.models.enums import SectionType; print(list(SectionType))"
```

Expected: list of enum members including `INTRO`, `OUTRO`, etc. If `SectionType` is not in `app.models.enums`, search with:
```bash
grep -r "class SectionType" app/
```
and adjust the import accordingly.

**Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/utils/test_feature_conversion.py -v
```

Expected: 5 tests pass.

**Step 6: Run full lint + type check**

```bash
uv run ruff check app/utils/audio/feature_conversion.py
uv run mypy app/utils/audio/feature_conversion.py
```

Expected: no errors.

**Step 7: Commit**

```bash
git add app/utils/audio/feature_conversion.py tests/utils/test_feature_conversion.py
git commit -m "feat(BPM-XX): add sections param to orm_features_to_track_features"
```

---

## Task 3: Fix `SetGenerationService` — playlist filtering + section loading

**Files:**
- Modify: `app/services/set_generation.py`
- Create: `tests/services/test_set_generation.py`

**Step 1: Write failing tests**

Create `tests/services/test_set_generation.py`:

```python
"""Tests for SetGenerationService playlist filtering and sections batch loading."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.errors import ValidationError
from app.services.set_generation import SetGenerationService

def _make_features_mock(track_id: int, bpm: float = 128.0) -> MagicMock:
    """Create a minimal TrackAudioFeaturesComputed mock."""
    f = MagicMock()
    f.track_id = track_id
    f.bpm = bpm
    f.energy_mean = 0.5
    f.key_code = 0
    return f

def _make_playlist_item(track_id: int) -> MagicMock:
    item = MagicMock()
    item.track_id = track_id
    return item

def _make_service(
    *,
    all_features: list,
    playlist_items: list | None = None,
    sections_map: dict | None = None,
) -> SetGenerationService:
    """Build a SetGenerationService with mocked repositories."""
    set_repo = AsyncMock()
    set_repo.get_by_id.return_value = MagicMock(set_id=1)

    version_repo = AsyncMock()
    version_repo.create.return_value = MagicMock(set_version_id=99)

    item_repo = AsyncMock()
    item_repo.create_bulk = AsyncMock()

    features_repo = AsyncMock()
    features_repo.list_all.return_value = all_features

    sections_repo: AsyncMock | None = None
    if sections_map is not None:
        sections_repo = AsyncMock()
        sections_repo.get_latest_by_track_ids.return_value = sections_map

    playlist_repo: AsyncMock | None = None
    if playlist_items is not None:
        playlist_repo = AsyncMock()
        playlist_repo.list_by_playlist.return_value = (playlist_items, len(playlist_items))

    return SetGenerationService(
        set_repo=set_repo,
        version_repo=version_repo,
        item_repo=item_repo,
        features_repo=features_repo,
        sections_repo=sections_repo,
        playlist_repo=playlist_repo,
    )

@pytest.mark.asyncio
async def test_playlist_filter_limits_tracks() -> None:
    """When playlist_id given, only playlist tracks should enter the GA."""
    all_features = [_make_features_mock(i) for i in range(1, 6)]  # tracks 1-5
    playlist_items = [_make_playlist_item(1), _make_playlist_item(3)]  # only 1, 3

    svc = _make_service(all_features=all_features, playlist_items=playlist_items)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(
        playlist_id=42,
        population_size=10,
        generations=10,
        track_count=2,
    )

    with patch(
        "app.services.set_generation.GeneticSetGenerator"
    ) as mock_gen_cls:
        mock_gen = MagicMock()
        mock_result = MagicMock()
        mock_result.best_order = [0, 1]
        mock_result.best_fitness = 0.8
        mock_result.fitness_history = [0.5, 0.8]
        mock_result.generations_run = 10
        mock_gen.run.return_value = mock_result
        mock_gen_cls.return_value = mock_gen

        with patch("app.services.set_generation._build_transition_matrix_scored") as mock_matrix:
            import numpy as np
            mock_matrix.return_value = np.array([[0.0, 0.9], [0.8, 0.0]])

            with patch("app.services.set_generation.CamelotLookupService") as mock_lookup_cls:
                mock_lookup = AsyncMock()
                mock_lookup.build_lookup_table.return_value = {}
                mock_lookup_cls.return_value = mock_lookup

                await svc.generate(1, req)

    # playlist_repo.list_by_playlist must have been called with playlist_id=42
    svc.playlist_repo.list_by_playlist.assert_called_once_with(42, limit=1000)  # type: ignore[union-attr]

@pytest.mark.asyncio
async def test_empty_playlist_raises_validation_error() -> None:
    """Empty playlist (no tracks with features) should raise ValidationError."""
    all_features = [_make_features_mock(1), _make_features_mock(2)]
    # playlist contains track 99 which has no features
    playlist_items = [_make_playlist_item(99)]

    svc = _make_service(all_features=all_features, playlist_items=playlist_items)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(playlist_id=5, population_size=10, generations=10)

    with pytest.raises(ValidationError, match="No tracks with audio features in playlist 5"):
        await svc.generate(1, req)

@pytest.mark.asyncio
async def test_no_playlist_id_uses_all_tracks() -> None:
    """Without playlist_id, all tracks should be used (backward compat)."""
    all_features = [_make_features_mock(i) for i in range(1, 4)]
    svc = _make_service(all_features=all_features)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(population_size=10, generations=10, track_count=3)

    with patch("app.services.set_generation.GeneticSetGenerator") as mock_gen_cls:
        mock_gen = MagicMock()
        mock_result = MagicMock()
        mock_result.best_order = [0, 1, 2]
        mock_result.best_fitness = 0.7
        mock_result.fitness_history = [0.7]
        mock_result.generations_run = 10
        mock_gen.run.return_value = mock_result
        mock_gen_cls.return_value = mock_gen

        with patch("app.services.set_generation._build_transition_matrix_scored") as mock_matrix:
            import numpy as np
            mock_matrix.return_value = np.ones((3, 3)) - np.eye(3)

            with patch("app.services.set_generation.CamelotLookupService") as mock_lookup_cls:
                mock_lookup = AsyncMock()
                mock_lookup.build_lookup_table.return_value = {}
                mock_lookup_cls.return_value = mock_lookup

                await svc.generate(1, req)

    # playlist_repo is None → list_by_playlist was never called
    assert svc.playlist_repo is None

@pytest.mark.asyncio
async def test_sections_repo_called_with_track_ids() -> None:
    """sections_repo.get_latest_by_track_ids should be called with all track IDs."""
    all_features = [_make_features_mock(10), _make_features_mock(20)]
    sections_map = {10: [], 20: []}

    svc = _make_service(all_features=all_features, sections_map=sections_map)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(population_size=10, generations=10, track_count=2)

    with patch("app.services.set_generation.GeneticSetGenerator") as mock_gen_cls:
        mock_gen = MagicMock()
        mock_result = MagicMock()
        mock_result.best_order = [0, 1]
        mock_result.best_fitness = 0.8
        mock_result.fitness_history = [0.8]
        mock_result.generations_run = 10
        mock_gen.run.return_value = mock_result
        mock_gen_cls.return_value = mock_gen

        with patch("app.services.set_generation._build_transition_matrix_scored") as mock_matrix:
            import numpy as np
            mock_matrix.return_value = np.array([[0.0, 0.9], [0.8, 0.0]])

            with patch("app.services.set_generation.CamelotLookupService") as mock_lookup_cls:
                mock_lookup = AsyncMock()
                mock_lookup.build_lookup_table.return_value = {}
                mock_lookup_cls.return_value = mock_lookup

                await svc.generate(1, req)

    svc.sections_repo.get_latest_by_track_ids.assert_called_once()  # type: ignore[union-attr]
    call_args = svc.sections_repo.get_latest_by_track_ids.call_args[0][0]  # type: ignore[union-attr]
    assert set(call_args) == {10, 20}
```

**Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/services/test_set_generation.py -v
```

Expected: `TypeError: SetGenerationService.__init__() got an unexpected keyword argument 'sections_repo'`

**Step 3: Implement the changes in `SetGenerationService`**

Edit `app/services/set_generation.py`:

**3a. Add new imports** (after existing imports, around line 10):

```python
from app.repositories.playlists import DjPlaylistItemRepository
from app.repositories.sections import SectionsRepository
from app.services.camelot_lookup import CamelotLookupService
from app.utils.audio.feature_conversion import orm_features_to_track_features
```

**3b. Update `__init__`** (lines 63-74):

```python
def __init__(
    self,
    set_repo: DjSetRepository,
    version_repo: DjSetVersionRepository,
    item_repo: DjSetItemRepository,
    features_repo: AudioFeaturesRepository,
    sections_repo: SectionsRepository | None = None,
    playlist_repo: DjPlaylistItemRepository | None = None,
) -> None:
    super().__init__()
    self.set_repo = set_repo
    self.version_repo = version_repo
    self.item_repo = item_repo
    self.features_repo = features_repo
    self.sections_repo = sections_repo
    self.playlist_repo = playlist_repo
```

**3c. Update `generate()`** — add playlist filtering after `features_list` is loaded (after line 98 `if not features_list`):

```python
# Filter to playlist tracks if specified
if data.playlist_id is not None and self.playlist_repo is not None:
    items, _ = await self.playlist_repo.list_by_playlist(
        data.playlist_id, limit=1000
    )
    allowed_ids = {item.track_id for item in items}
    features_list = [f for f in features_list if f.track_id in allowed_ids]
    if not features_list:
        raise ValidationError(
            f"No tracks with audio features in playlist {data.playlist_id}"
        )
```

**3d. Find `_build_transition_matrix_scored` method** — it builds `TrackFeatures` list. Find the call to `orm_features_to_track_features` (or `features_map` usage) and add sections batch loading.

Look for the method signature: it currently has `tracks: list[TrackData]` and loads features from DB. The method needs to:
1. Batch-load sections from `sections_repo` for all track IDs
2. Pass sections to `orm_features_to_track_features`

Find the method with:
```bash
grep -n "_build_transition_matrix_scored\|orm_features_to_track_features" app/services/set_generation.py
```

Then update the relevant section. The pattern to implement:

```python
# Batch-load sections for structure scoring
sections_map: dict[int, list] = {}
if self.sections_repo is not None:
    track_ids = [t.track_id for t in tracks]
    sections_map = await self.sections_repo.get_latest_by_track_ids(track_ids)

# Build TrackFeatures with section data
for track in tracks:
    feat_db = features_map.get(track.track_id)
    if feat_db is None:
        track_features.append(None)
        continue
    secs = sections_map.get(track.track_id)
    track_features.append(orm_features_to_track_features(feat_db, secs))
```

**Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/services/test_set_generation.py -v
```

Expected: 4 tests pass.

**Step 5: Run full test suite to check no regressions**

```bash
uv run pytest tests/ -v --tb=short
```

**Step 6: Lint + type check**

```bash
uv run ruff check app/services/set_generation.py
uv run mypy app/services/set_generation.py
```

**Step 7: Commit**

```bash
git add app/services/set_generation.py tests/services/test_set_generation.py
git commit -m "fix(BPM-XX): filter set generation by playlist_id + batch load sections"
```

---

## Task 4: Fix `UnifiedTransitionScoringService.score_components_by_ids()` — load sections

**Files:**
- Modify: `app/services/transition_scoring_unified.py`
- Create: `tests/services/test_transition_scoring_unified.py`

**Step 1: Write failing tests**

Create `tests/services/test_transition_scoring_unified.py`:

```python
"""Tests for UnifiedTransitionScoringService — sections loading in score_components_by_ids."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

def _make_feat_mock(track_id: int, key_code: int = 0) -> MagicMock:
    """Create a minimal TrackAudioFeaturesComputed mock."""
    f = MagicMock()
    f.track_id = track_id
    f.bpm = 128.0
    f.lufs_i = -14.0
    f.key_code = key_code
    f.chroma_entropy = 0.7
    f.key_confidence = None
    f.low_energy = 0.3
    f.mid_energy = 0.5
    f.high_energy = 0.2
    f.mfcc_vector = None
    f.centroid_mean_hz = 2000.0
    f.onset_rate_mean = 5.0
    f.kick_prominence = 0.5
    f.hnr_mean_db = 0.0
    f.slope_db_per_oct = 0.0
    f.hp_ratio = 0.5
    return f

def _make_section(section_type: int, start_ms: int = 0, end_ms: int = 30000) -> MagicMock:
    sec = MagicMock()
    sec.section_type = section_type
    sec.start_ms = start_ms
    sec.end_ms = end_ms
    return sec

@pytest.mark.asyncio
async def test_score_components_by_ids_calls_sections_repo() -> None:
    """score_components_by_ids should call sections_repo.get_latest_by_track_ids."""
    session = AsyncMock()

    feat_a = _make_feat_mock(track_id=1)
    feat_b = _make_feat_mock(track_id=2)

    sections_map = {1: [], 2: []}

    with (
        patch("app.services.transition_scoring_unified.AudioFeaturesRepository") as mock_feat_repo_cls,
        patch("app.services.transition_scoring_unified.SectionsRepository") as mock_sec_repo_cls,
        patch("app.services.transition_scoring_unified.CamelotLookupService") as mock_lookup_cls,
    ):
        mock_feat_repo = AsyncMock()
        mock_feat_repo.get_by_track.side_effect = [feat_a, feat_b]
        mock_feat_repo_cls.return_value = mock_feat_repo

        mock_sec_repo = AsyncMock()
        mock_sec_repo.get_latest_by_track_ids.return_value = sections_map
        mock_sec_repo_cls.return_value = mock_sec_repo

        mock_lookup = AsyncMock()
        mock_lookup.build_lookup_table.return_value = {}
        mock_lookup_cls.return_value = mock_lookup

        from app.services.transition_scoring_unified import UnifiedTransitionScoringService

        svc = UnifiedTransitionScoringService(session)
        result = await svc.score_components_by_ids(1, 2)

    mock_sec_repo.get_latest_by_track_ids.assert_called_once_with([1, 2])
    assert "total" in result
    assert "structure" in result

@pytest.mark.asyncio
async def test_structure_score_nonzero_with_outro_intro_sections() -> None:
    """Structure component should be non-neutral when outro→intro sections present."""
    session = AsyncMock()

    feat_a = _make_feat_mock(track_id=10)  # outro track
    feat_b = _make_feat_mock(track_id=20)  # intro track

    # SectionType: 0=intro, 4=outro
    outro_section = _make_section(section_type=4, start_ms=180000, end_ms=210000)
    intro_section = _make_section(section_type=0, start_ms=0, end_ms=32000)

    sections_map = {10: [outro_section], 20: [intro_section]}

    with (
        patch("app.services.transition_scoring_unified.AudioFeaturesRepository") as mock_feat_repo_cls,
        patch("app.services.transition_scoring_unified.SectionsRepository") as mock_sec_repo_cls,
        patch("app.services.transition_scoring_unified.CamelotLookupService") as mock_lookup_cls,
    ):
        mock_feat_repo = AsyncMock()
        mock_feat_repo.get_by_track.side_effect = [feat_a, feat_b]
        mock_feat_repo_cls.return_value = mock_feat_repo

        mock_sec_repo = AsyncMock()
        mock_sec_repo.get_latest_by_track_ids.return_value = sections_map
        mock_sec_repo_cls.return_value = mock_sec_repo

        mock_lookup = AsyncMock()
        mock_lookup.build_lookup_table.return_value = {}
        mock_lookup_cls.return_value = mock_lookup

        from app.services.transition_scoring_unified import UnifiedTransitionScoringService

        svc = UnifiedTransitionScoringService(session)
        result = await svc.score_components_by_ids(10, 20)

    # outro→intro is the best pairing (1.0 * 1.0), score_structure should be > 0.5 (neutral)
    assert result["structure"] > 0.5, f"Expected structure > 0.5, got {result['structure']}"
```

**Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/services/test_transition_scoring_unified.py -v
```

Expected: `ImportError` or `AssertionError` — `SectionsRepository` not imported, sections not loaded.

**Step 3: Implement the fix in `UnifiedTransitionScoringService`**

Edit `app/services/transition_scoring_unified.py`:

**3a. Add imports** (after existing imports around line 12):

```python
from app.repositories.sections import SectionsRepository
```

**3b. Update `__init__`** to instantiate `SectionsRepository`:

```python
def __init__(self, session: AsyncSession) -> None:
    self._session = session
    self._features_repo = AudioFeaturesRepository(session)
    self._sections_repo = SectionsRepository(session)
    self._scorer: TransitionScoringService | None = None
```

**3c. Update `score_components_by_ids`** (currently lines 52-55):

```python
async def score_components_by_ids(self, from_id: int, to_id: int) -> dict[str, float]:
    """Return per-component breakdown ``{total, bpm, harmonic, …}``."""
    feat_a, feat_b = await self._load_pair(from_id, to_id)
    sections = await self._sections_repo.get_latest_by_track_ids([from_id, to_id])
    tf_a = orm_features_to_track_features(feat_a, sections.get(from_id))
    tf_b = orm_features_to_track_features(feat_b, sections.get(to_id))
    return _score_components(await self._get_scorer(), tf_a, tf_b)
```

Note: `score_by_ids` and `score_by_features` / `score_components_by_features` are **intentionally left without sections** per the design decision.

**Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/services/test_transition_scoring_unified.py -v
```

Expected: 2 tests pass.

**Step 5: Lint + type check**

```bash
uv run ruff check app/services/transition_scoring_unified.py
uv run mypy app/services/transition_scoring_unified.py
```

**Step 6: Commit**

```bash
git add app/services/transition_scoring_unified.py tests/services/test_transition_scoring_unified.py
git commit -m "fix(BPM-XX): load sections in score_components_by_ids for accurate structure scoring"
```

---

## Task 5: Update DI in `mcp/dependencies.py` and `routers/v1/sets.py`

**Files:**
- Modify: `app/mcp/dependencies.py:98-107`
- Modify: `app/routers/v1/sets.py:122-128`

**Step 1: Update `get_set_generation_service()` in `mcp/dependencies.py`**

`SectionsRepository` and `DjPlaylistItemRepository` are already imported at the top of the file. Update the function at lines 98-107:

```python
def get_set_generation_service(
    session: AsyncSession = Depends(get_session),
) -> SetGenerationService:
    """Build a SetGenerationService with all required repositories."""
    return SetGenerationService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),           # new: section data for structure scoring
        DjPlaylistItemRepository(session),     # new: playlist filtering
    )
```

**Step 2: Update `_generation_service()` in `routers/v1/sets.py`**

First add imports at the top of `routers/v1/sets.py` (after existing imports):

```python
from app.repositories.playlists import DjPlaylistItemRepository
from app.repositories.sections import SectionsRepository
```

Then update `_generation_service()` at lines 122-128:

```python
def _generation_service(db: DbSession) -> SetGenerationService:
    return SetGenerationService(
        DjSetRepository(db),
        DjSetVersionRepository(db),
        DjSetItemRepository(db),
        AudioFeaturesRepository(db),
        SectionsRepository(db),               # new
        DjPlaylistItemRepository(db),         # new
    )
```

**Step 3: Run tests**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all pass.

**Step 4: Lint + type check both files**

```bash
uv run ruff check app/mcp/dependencies.py app/routers/v1/sets.py
uv run mypy app/mcp/dependencies.py app/routers/v1/sets.py
```

**Step 5: Commit**

```bash
git add app/mcp/dependencies.py app/routers/v1/sets.py
git commit -m "fix(BPM-XX): inject SectionsRepository and DjPlaylistItemRepository into SetGenerationService"
```

---

## Task 6: Pass `playlist_id` through `build_set` MCP tool

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py:63`

**Step 1: Update `SetGenerationRequest` construction**

In `setbuilder_tools.py`, line 63, change:

```python
# Before:
request = SetGenerationRequest(energy_arc_type=energy_arc)

# After:
request = SetGenerationRequest(energy_arc_type=energy_arc, playlist_id=playlist_id)
```

**Step 2: Run tests**

```bash
uv run pytest tests/ -v --tb=short
```

**Step 3: Manual smoke test via MCP CLI (optional)**

```bash
make mcp-call TOOL=dj_build_set ARGS='{"playlist_id": 1, "set_name": "Test Set", "energy_arc": "classic"}'
```

**Step 4: Lint + type check**

```bash
uv run ruff check app/mcp/workflows/setbuilder_tools.py
uv run mypy app/mcp/workflows/setbuilder_tools.py
```

**Step 5: Commit**

```bash
git add app/mcp/workflows/setbuilder_tools.py
git commit -m "fix(BPM-XX): forward playlist_id to SetGenerationRequest in build_set tool"
```

---

## Task 7: Full CI check + cleanup

**Step 1: Run full test suite with coverage**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all pass.

**Step 2: Run full lint + type check**

```bash
make lint
```

Expected: exit 0.

**Step 3: Quick sanity check on `_build_transition_matrix_scored`**

Verify sections are being passed to `orm_features_to_track_features`:

```bash
grep -n "sections_map\|orm_features_to_track_features" app/services/set_generation.py
```

Expected: both appear in `_build_transition_matrix_scored` method.

**Step 4: Verify `score_structure` now gets non-None section data**

The scoring chain: `score_components_by_ids` → `sections_repo.get_latest_by_track_ids` → `orm_features_to_track_features(feat, sections)` → `TrackFeatures(first_section=..., last_section=...)` → `score_structure()` in `TransitionScoringService`.

Check the `score_structure` lookup keys match enum names:

```bash
uv run python -c "
from app.models.enums import SectionType
from app.services.transition_scoring import TransitionScoringService
svc = TransitionScoringService()
print('MIX_OUT:', list(svc.MIX_OUT_QUALITY.keys()))
print('SectionType names:', [e.name.lower() for e in SectionType])
"
```

Expected: all keys in `MIX_OUT_QUALITY` and `MIX_IN_QUALITY` appear in `SectionType` names.

**Step 5: Commit final cleanup if any**

```bash
git add -p  # review any remaining changes
git commit -m "chore(BPM-XX): final cleanup and full CI pass"
```

---

## Summary of changes

| File | Change |
|------|--------|
| `app/schemas/set_generation.py` | +`playlist_id: int \| None = None` |
| `app/utils/audio/feature_conversion.py` | +`sections` param, map `SectionType` to `first/last_section` |
| `app/services/set_generation.py` | +`sections_repo`, +`playlist_repo`, filtering, batch section loading |
| `app/services/transition_scoring_unified.py` | +`SectionsRepository`, load sections in `score_components_by_ids()` |
| `app/mcp/dependencies.py` | +2 repos in `get_set_generation_service()` |
| `app/routers/v1/sets.py` | +2 repos in `_generation_service()` |
| `app/mcp/workflows/setbuilder_tools.py` | Forward `playlist_id` to `SetGenerationRequest` |
| `tests/utils/test_feature_conversion.py` | **NEW** — 5 tests for sections mapping |
| `tests/services/test_set_generation.py` | **NEW** — 4 tests for playlist filtering + sections |
| `tests/services/test_transition_scoring_unified.py` | **NEW** — 2 tests for sections in scoring |
