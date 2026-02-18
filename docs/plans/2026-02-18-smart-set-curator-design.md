# Smart Set Curator — Design Document

**Date:** 2026-02-18
**Author:** Claude Opus 4.6
**Status:** Approved
**Approach:** A — "Smart Curator" (audio-based clustering + slot system + improved GA + iterative MCP workflow)

## Overview

Comprehensive improvement to the DJ set generation system addressing 5 critical problems:
1. No subgenre/mood awareness (genres table = 0 rows)
2. Energy arc uses normalized `energy_mean` [0,1] instead of actual LUFS
3. GA takes ALL tracks without intelligent selection
4. No "breathing" moments — can chain 20 peak-time tracks
5. Discovery tools are stubs (`find_similar_tracks` = 0 results)

Target: **djay Pro AI** (Algoriddim). Both short sets (1-2h, 15-30 tracks) and full library ordering (200+ tracks).

## Current State (Database Stats)

| Metric | Value |
|--------|-------|
| Tracks total | 1457 |
| With audio features | 773 (53%) |
| Without features | 684 |
| Track sections | 42,839 |
| Library items (with files) | 1,017 |
| Artists | 986 |
| Genres | 0 |
| BPM distribution | 125-129 dominant (404 tracks) |
| Key distribution | 6A (73), 4A (72), 7A (60) |
| Energy distribution | Loud -11..-8 LUFS (476), Very loud >-8 (256), Moderate (41) |

## Section 1 — Track Mood Clustering

### Problem
No genre/subgenre data. 0 rows in `genres` table, 0 in `track_genres`. Classification purely from audio features.

### Solution: 6 Rule-Based Mood Categories

Classify each track into one of 6 mood categories using existing audio features (`TrackAudioFeaturesComputed`):

| Category | Rules | Typical % |
|----------|-------|-----------|
| `AMBIENT_DUB` | bpm < 128 AND lufs_i < -11 | ~5% |
| `MELODIC_DEEP` | hp_ratio > 0.6 AND spectral_centroid_mean < 2000 | ~15% |
| `DRIVING` | (default category — doesn't match others) | ~35% |
| `PEAK_TIME` | kick_prominence > 0.6 AND lufs_i > -8 | ~25% |
| `INDUSTRIAL` | spectral_centroid_mean > 4000 AND onset_rate > 8 | ~10% |
| `HARD_TECHNO` | bpm >= 140 AND kick_prominence > 0.6 | ~10% |

**Priority order** (first match wins): HARD_TECHNO → INDUSTRIAL → AMBIENT_DUB → PEAK_TIME → MELODIC_DEEP → DRIVING.

### Implementation

New module: `app/utils/audio/mood_classifier.py`

```python
class TrackMood(str, Enum):
    AMBIENT_DUB = "ambient_dub"
    MELODIC_DEEP = "melodic_deep"
    DRIVING = "driving"
    PEAK_TIME = "peak_time"
    INDUSTRIAL = "industrial"
    HARD_TECHNO = "hard_techno"

@dataclass(frozen=True)
class MoodClassification:
    mood: TrackMood
    confidence: float       # 0.0-1.0
    features_used: tuple[str, ...]  # which features triggered
```

Populate `track_genres` table with mood as genre (reuse existing schema). Classifier is pure function — no DB, no side effects.

### Energy Ordering

For energy arc purposes, moods have natural intensity ordering:

```text
AMBIENT_DUB(1) → MELODIC_DEEP(2) → DRIVING(3) → PEAK_TIME(4) → INDUSTRIAL(5) → HARD_TECHNO(6)
```

## Section 2 — Slot System & Smart Track Selection

### Problem
GA currently takes ALL tracks (773 with features). For a 60-min set it should pick ~20 best-fitting tracks, not order all 773.

### Solution: Slot-Based Templates

Each slot defines: mood category, energy level, approximate BPM range, and duration.

#### Template Library (8 templates)

**Short sets (1-2h):**

| Template | Duration | Tracks | Description |
|----------|----------|--------|-------------|
| `WARM_UP_30` | 30 min | 8-10 | Ambient/melodic opener for warm-up slot |
| `CLASSIC_60` | 60 min | 18-22 | Standard arc: warm-up → build → peak → cooldown |
| `PEAK_HOUR_60` | 60 min | 18-22 | High energy throughout, minimal cooldown |
| `ROLLER_90` | 90 min | 25-30 | Extended rolling techno with 2 peaks |
| `PROGRESSIVE_120` | 120 min | 35-40 | Slow 2-hour build to a single massive peak |
| `WAVE_120` | 120 min | 35-40 | Oscillating energy — multiple peaks and valleys |
| `CLOSING_60` | 60 min | 18-22 | Peak → gradual cooldown → ambient close |

**Full library:**

| Template | Duration | Tracks | Description |
|----------|----------|--------|-------------|
| `FULL_LIBRARY` | Variable | All | Order entire library with breathe constraint |

#### Slot Definition

```python
@dataclass(frozen=True)
class SetSlot:
    position: float          # 0.0-1.0 (position in set)
    mood: TrackMood          # required mood category
    energy_target: float     # LUFS target (e.g. -10.0)
    bpm_range: tuple[float, float]  # allowed BPM range
    duration_target_s: int   # target duration in seconds
    flexibility: float       # 0.0-1.0, how strict the constraints are
```

#### Smart Selection Algorithm

1. Classify all candidate tracks by mood
2. For each slot, score candidates:
   - Mood match (40%): exact=1.0, adjacent=0.5, other=0.0
   - Energy fit (30%): how close LUFS to energy_target
   - BPM fit (20%): how well BPM fits slot range
   - Variety bonus (10%): penalize same artist, same key as neighbors
3. Pick top candidate per slot (greedy, no track reuse)
4. Pass selected tracks + slot order to GA for fine optimization

### CLASSIC_60 Template Example

```text
Position  Mood             Energy    BPM
0.00-0.10 AMBIENT_DUB      -12 LUFS  122-126
0.10-0.25 MELODIC_DEEP     -10 LUFS  124-128
0.25-0.50 DRIVING          -9 LUFS   126-130
0.50-0.70 PEAK_TIME        -7 LUFS   128-134
0.70-0.80 DRIVING          -9 LUFS   128-130  ← breathing moment
0.80-0.95 PEAK_TIME        -7 LUFS   130-136
0.95-1.00 MELODIC_DEEP     -10 LUFS  126-130
```

## Section 3 — Improved GA

### Problem 1: Energy Proxy
Current GA uses `energy_mean` (normalized 0-1 from essentia) for energy arc. This correlates poorly with perceived loudness.

**Fix**: Switch to `lufs_i` (integrated LUFS). Already in `TrackAudioFeaturesComputed` for 773 tracks.

### Problem 2: No Breathing
GA optimizes average transition quality → chains 20 peak-time tracks if their transitions score well.

**Fix**: Add `variety_penalty` to fitness function.

### Problem 3: Takes All Tracks
For target_count=20, GA still builds matrix for ALL tracks and tries to order them all.

**Fix**: Slot-based pre-selection (Section 2) feeds only 20-40 candidates to GA.

### New Fitness Function

Current weights:
```python
w_transition=0.50, w_energy_arc=0.30, w_bpm_smooth=0.20
```

New weights (4 objectives):
```python
w_transition=0.40    # average transition quality (unchanged scoring)
w_energy_arc=0.25    # LUFS-based energy arc adherence
w_bpm_smooth=0.15    # BPM smoothness
w_variety=0.20       # NEW: mood/key/artist variety penalty
```

### Variety Penalty

Penalize sequences that lack diversity:

```python
def variety_penalty(sequence: list[TrackFeatures]) -> float:
    penalties = 0.0
    for i in range(1, len(sequence)):
        # Same mood category for 3+ consecutive tracks
        if i >= 2 and all(s.mood == sequence[i].mood for s in sequence[i-2:i+1]):
            penalties += 0.3
        # Same Camelot key for 3+ consecutive tracks
        if i >= 2 and all(s.key_code == sequence[i].key_code for s in sequence[i-2:i+1]):
            penalties += 0.2
        # Same artist in 5-track window
        if sequence[i].artist_id in {s.artist_id for s in sequence[max(0,i-4):i]}:
            penalties += 0.1
    return max(0.0, 1.0 - penalties / len(sequence))
```

### LUFS-Based Energy Arc

Replace `energy_mean` with `lufs_i` in `_energy_arc_adherence()`:

```python
# Before: normalized 0-1
energy = features.energy_mean

# After: LUFS mapped to 0-1 range
# Typical techno range: -14 LUFS (ambient) to -6 LUFS (hard)
energy = (features.lufs_i - (-14)) / ((-6) - (-14))  # clamp to [0, 1]
```

### Breathe Constraint (FULL_LIBRARY mode)

For 200+ track sets, enforce a breathing moment every N tracks:

```python
BREATHE_INTERVAL = 7  # every 7 tracks, at least 1 must be lower energy
BREATHE_ENERGY_DROP = 0.15  # minimum 15% energy drop from local average
```

GA mutation operator: if breathe constraint violated, swap a peak track with a lower-energy alternative.

## Section 4 — Iterative MCP Workflow

### Problem
Current workflow is one-shot: `build_set` → done. No way to review, tweak, regenerate.

### Solution: Review → Adjust → Re-Generate Cycle

```text
┌──────────────────────────────────────────────────────┐
│  1. CURATE                                            │
│  ┌─────────────┐   ┌──────────────┐                  │
│  │ classify     │ → │ select by    │ → candidates     │
│  │ all tracks   │   │ template     │   (20-40 tracks) │
│  └─────────────┘   └──────────────┘                  │
├──────────────────────────────────────────────────────┤
│  2. BUILD                                             │
│  ┌─────────────┐   ┌──────────────┐                  │
│  │ GA optimize  │ → │ score all    │ → set v1         │
│  │ (new fitness)│   │ transitions  │                  │
│  └─────────────┘   └──────────────┘                  │
├──────────────────────────────────────────────────────┤
│  3. REVIEW (MCP tool)                                 │
│  ┌─────────────┐   ┌──────────────┐                  │
│  │ score_set    │ → │ identify     │ → weak spots     │
│  │ (detailed)   │   │ weak spots   │   + suggestions  │
│  └─────────────┘   └──────────────┘                  │
├──────────────────────────────────────────────────────┤
│  4. ADJUST (MCP tool)                                 │
│  ┌─────────────────────────────────┐                  │
│  │ swap_tracks / reorder / replace │ → set v2         │
│  └─────────────────────────────────┘                  │
│                    ↑                                  │
│                    └──── repeat 3-4 until satisfied   │
├──────────────────────────────────────────────────────┤
│  5. EXPORT                                            │
│  ┌─────────────┐   ┌──────────────┐                  │
│  │ M3U8 for     │   │ JSON guide   │                  │
│  │ djay Pro     │   │ for practice │                  │
│  └─────────────┘   └──────────────┘                  │
└──────────────────────────────────────────────────────┘
```

### New/Modified MCP Tools

| Tool | Action | Status |
|------|--------|--------|
| `classify_tracks` | Classify all tracks by mood, return distribution | NEW |
| `curate_set` | Select tracks by template + mood, return candidates | NEW |
| `build_set` | Run GA with new fitness (variety + LUFS) | MODIFY |
| `review_set` | Detailed analysis with weak spots + suggestions | NEW |
| `swap_tracks` | Replace specific track(s) in a set version | NEW |
| `score_transitions` | Score all transitions (fix title bug) | FIX |
| `search_by_criteria` | Filter tracks by BPM/key/energy/mood | FIX |
| `export_set_m3u` | Export M3U8 for djay Pro | EXISTS |
| `export_set_json` | Export JSON transition guide | EXISTS |

### `review_set` Output

```python
@dataclass
class SetReview:
    overall_score: float           # 0-1
    energy_arc_adherence: float    # 0-1
    variety_score: float           # 0-1
    weak_transitions: list[WeakTransition]  # score < 0.4
    energy_plateaus: list[EnergyPlateau]    # 3+ same-energy tracks
    mood_monotony: list[MoodRun]            # 3+ same-mood tracks
    suggestions: list[str]         # human-readable suggestions
```

### `curate_set` Parameters

```python
async def curate_set(
    playlist_id: int,              # source playlist
    template: str = "CLASSIC_60",  # template name
    target_count: int | None = None,  # override template default
    exclude_track_ids: list[int] = [],  # already used / rejected
    mood_weights: dict[str, float] | None = None,  # override mood distribution
) -> CurateResult:
```

## Section 5 — Library Gap Analysis & Expansion

### Problem
Library has gaps: only 41 "moderate" energy tracks (LUFS -14..-11), very few ambient tracks. Sets can't have proper warm-up sections.

### Solution: Gap Analysis Tool

New MCP tool `analyze_library_gaps`:

```python
async def analyze_library_gaps(
    playlist_id: int | None = None,
    template: str = "CLASSIC_60",
) -> LibraryGapAnalysis:
```

Returns:
```python
@dataclass
class LibraryGapAnalysis:
    total_tracks: int
    tracks_with_features: int
    mood_distribution: dict[TrackMood, int]
    template_requirements: dict[str, int]    # what template needs per mood
    gaps: list[GapDescription]               # what's missing
    recommendations: list[str]               # e.g. "Add 5 ambient tracks <128 BPM"
```

### Recommendations Feed into Discovery

`find_similar_tracks` (currently stub) can use gap analysis to search YM for tracks matching:
- Specific BPM range
- Energy level (LUFS proxy from YM metadata)
- Artists similar to existing library

This is Phase 2 work — for now, `analyze_library_gaps` provides human-readable recommendations.

## Data Flow

```text
TrackAudioFeaturesComputed
         │
    ┌────┴────┐
    │ Mood    │ → track_genres (reuse existing table)
    │ Classify│
    └────┬────┘
         │
    ┌────┴────┐
    │ Template│ → SetSlot[] → candidate_tracks (20-40)
    │ Select  │
    └────┬────┘
         │
    ┌────┴────┐
    │ GA      │ → DjSetVersion + DjSetItems (ordered)
    │ Optimize│
    └────┬────┘
         │
    ┌────┴────┐
    │ Review  │ → SetReview (weak spots, suggestions)
    │ + Score │
    └────┬────┘
         │
    ┌────┴────┐
    │ Export  │ → .m3u8 (djay Pro) + .json (guide)
    └─────────┘
```

## Files Changed Summary

### New Files
| File | Purpose |
|------|---------|
| `app/utils/audio/mood_classifier.py` | 6-mood rule-based classifier |
| `app/services/set_curation.py` | Template + slot + selection logic |
| `app/schemas/set_curation.py` | Pydantic schemas for curation |
| `app/mcp/workflows/curation_tools.py` | 4 new MCP tools |
| `app/mcp/types_curation.py` | Pydantic models for MCP output |
| `tests/utils/test_mood_classifier.py` | Mood classifier tests |
| `tests/services/test_set_curation.py` | Curation service tests |
| `tests/mcp/test_curation_tools.py` | MCP tool registration + integration |

### Modified Files
| File | Changes |
|------|---------|
| `app/utils/audio/set_generator.py` | LUFS energy, variety penalty, breathe constraint |
| `app/services/set_generation.py` | Accept pre-selected candidates from curation |
| `app/services/transition_scoring.py` | Fix title bug in score output |
| `app/mcp/workflows/setbuilder_tools.py` | Wire up new curation, fix score_transitions title |
| `app/mcp/workflows/discovery_tools.py` | Fix search_by_criteria empty titles |
| `app/mcp/workflows/server.py` | Register curation tools |
| `app/mcp/dependencies.py` | New DI providers for curation |
| `app/mcp/types.py` | New output types |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Mood classifier too coarse | Wrong tracks in slots | Adjustable thresholds, easy to add 7th/8th category later |
| GA slower with variety penalty | Longer generation time | Penalty is O(n), not O(n^2); pre-selection keeps n<40 |
| 53% tracks lack features | Incomplete classification | Classify only tracks with features; recommend re-analysis |
| LUFS distribution skewed loud | Poor warm-up selection | Gap analysis highlights this; user adds ambient tracks |
| Template doesn't match library | Too few candidates per slot | Flexibility parameter + fallback to adjacent mood |

## Success Criteria

- [ ] Every track with features gets a mood classification
- [ ] `curate_set("CLASSIC_60")` returns 18-22 tracks with proper mood distribution
- [ ] GA with variety penalty produces no 3+ consecutive same-mood sequences
- [ ] Energy arc uses LUFS, not energy_mean
- [ ] `review_set` identifies weak transitions and suggests replacements
- [ ] Full library ordering has breathing moments every ~7 tracks
- [ ] Existing MCP bugs fixed (score_transitions titles, search_by_criteria titles)
- [ ] All new code has tests (>80% coverage)
- [ ] Export works with djay Pro AI
