# Design: Fix playlist scoping and section loading in set generation

**Date:** 2026-02-17
**Status:** Approved
**Scope:** Bug fix + feature completion (Approach B — comprehensive)

## Problem

Two bugs in the DJ set generation pipeline:

### Bug 1 — `build_set` ignores `playlist_id`

`SetGenerationService.generate()` calls `features_repo.list_all()` and uses **all tracks in the DB**, regardless of which playlist was selected. The `playlist_id` parameter in `build_set` MCP tool is effectively ignored.

### Bug 2 — Structure scoring always returns 0.5 (neutral)

`TransitionScoringService.score_structure()` uses `last_section` / `first_section` fields on `TrackFeatures`, but `orm_features_to_track_features()` never populates them (they stay `None`). Section data exists in the `track_sections` table but is never loaded in the scoring path.

## Solution — Approach B (Comprehensive)

Fix both bugs in all entry points: GA matrix building (`build_set`) and live scoring (`score_transitions`).

## Architecture

### Files changed

```bash
schemas/set_generation.py              +playlist_id: int | None = None
utils/audio/feature_conversion.py     +sections: list[TrackSection] | None parameter
services/set_generation.py            +sections_repo, +playlist_repo, batch section loading, playlist filtering
services/transition_scoring_unified.py +sections_repo, load sections in score_components_by_ids()
mcp/dependencies.py                   +SectionsRepository, +DjPlaylistItemRepository in get_set_generation_service()
routers/v1/sets.py                    +SectionsRepository, +DjPlaylistItemRepository in _generation_service()
mcp/workflows/setbuilder_tools.py     pass playlist_id into SetGenerationRequest
```

### New test files / updates

```bash
tests/services/test_set_generation.py         playlist filtering + sections batch loading
tests/utils/test_feature_conversion.py        sections parameter
tests/services/test_transition_scoring_unified.py  sections in score_components_by_ids
```

## Detailed component design

### 1. `schemas/set_generation.py`

Add optional field (backward-compatible):

```python
playlist_id: int | None = None  # filter tracks to this playlist
```

### 2. `utils/audio/feature_conversion.py`

```python
from app.models.enums import SectionType
from app.models.sections import TrackSection

def orm_features_to_track_features(
    feat: TrackAudioFeaturesComputed,
    sections: list[TrackSection] | None = None,
) -> TrackFeatures:
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
        ...  # existing fields unchanged
        last_section=last_section,
        first_section=first_section,
    )
```

Key mapping: `SectionType.OUTRO.name.lower()` → `"outro"` — matches keys in `MIX_OUT_QUALITY` and `MIX_IN_QUALITY` exactly.

### 3. `services/set_generation.py`

```python
class SetGenerationService(BaseService):
    def __init__(
        self,
        set_repo: DjSetRepository,
        version_repo: DjSetVersionRepository,
        item_repo: DjSetItemRepository,
        features_repo: AudioFeaturesRepository,
        sections_repo: SectionsRepository | None = None,
        playlist_repo: DjPlaylistItemRepository | None = None,
    ) -> None:
```

In `generate()`, after loading `features_list`:

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

In `_build_transition_matrix_scored()`, batch-load sections and enrich features:

```python
# Batch-load sections for structure scoring
sections_map: dict[int, list] = {}
if self.sections_repo is not None:
    track_ids = [t.track_id for t in tracks]
    sections_map = await self.sections_repo.get_latest_by_track_ids(track_ids)

# Build feature objects with section data
for track in tracks:
    feat_db = features_map.get(track.track_id)
    if feat_db is None:
        track_features.append(None)
        continue
    secs = sections_map.get(track.track_id)
    track_features.append(orm_features_to_track_features(feat_db, secs))
```

### 4. `services/transition_scoring_unified.py`

Add `SectionsRepository` and use it in `score_components_by_ids()`:

```python
class UnifiedTransitionScoringService:
    def __init__(self, session: AsyncSession) -> None:
        ...
        self._sections_repo = SectionsRepository(session)

    async def score_components_by_ids(
        self, from_id: int, to_id: int
    ) -> dict[str, float]:
        feat_a, feat_b = await self._load_pair(from_id, to_id)
        sections = await self._sections_repo.get_latest_by_track_ids([from_id, to_id])
        tf_a = orm_features_to_track_features(feat_a, sections.get(from_id))
        tf_b = orm_features_to_track_features(feat_b, sections.get(to_id))
        return _score_components(await self._get_scorer(), tf_a, tf_b)
```

Note: `score_by_features()` / `score_components_by_features()` are not used in production paths — leave them without sections for now.

### 5. DI updates — `mcp/dependencies.py` + `routers/v1/sets.py`

Both `get_set_generation_service()` (MCP) and `_generation_service()` (REST) get two new repos:

```python
return SetGenerationService(
    DjSetRepository(session),
    DjSetVersionRepository(session),
    DjSetItemRepository(session),
    AudioFeaturesRepository(session),
    SectionsRepository(session),           # new
    DjPlaylistItemRepository(session),     # new
)
```

### 6. `mcp/workflows/setbuilder_tools.py`

Pass `playlist_id` through to `SetGenerationRequest`:

```python
request = SetGenerationRequest(energy_arc_type=energy_arc, playlist_id=playlist_id)
```

## Error handling

| Situation | Behavior |
|-----------|----------|
| `playlist_id` given, no tracks with features | `ValidationError: No tracks with features in playlist N` |
| `playlist_id` not given | All tracks used (backward compat) |
| No sections found for track | `first_section = last_section = None` → `score_structure()` returns 0.5 |
| `SectionType` int out of range | `ValueError` caught, sections ignored |
| `sections_repo=None` | No section loading, backward compat |

## Testing plan

1. `test_feature_conversion.py`:
   - `orm_features_to_track_features(feat, sections=[intro_sec, outro_sec])` → `first_section="intro"`, `last_section="outro"`
   - `orm_features_to_track_features(feat, sections=None)` → both `None` (regression)

2. `test_set_generation.py`:
   - Playlist filter: `playlist_id=5` → only playlist tracks in matrix
   - Empty playlist → `ValidationError`
   - `sections_repo.get_latest_by_track_ids()` called with correct track IDs

3. `test_transition_scoring_unified.py`:
   - `score_components_by_ids()` → `sections_repo.get_latest_by_track_ids([from_id, to_id])` called
   - `structure` component is non-neutral when outro→intro sections present

## Out of scope

- `score_by_features()` / `score_components_by_features()` — leave without sections
- Subgenre weight presets
- Composite set quality metric
- Adaptive energy curves
