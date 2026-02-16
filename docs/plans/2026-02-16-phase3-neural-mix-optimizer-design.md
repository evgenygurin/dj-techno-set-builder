# Phase 3: Neural Mix Transition Intelligence + Optimizer Enhancements

**Date**: 2026-02-16
**Branch**: `feature/BPM-1-unified-transition-scoring`
**Linear**: BPM-1
**Status**: Approved

## Context

Phase 2B completed MFCC, HNR, and kick prominence enrichment of the 5-component
transition scoring formula. Phase 3 adds two complementary improvements:

- **Phase 3a**: Transition type recommendations for djay Pro Neural Mix + M3U/JSON export
- **Phase 3b**: GA optimizer enhancements (full-fitness 2-opt, NN init, section-aware scoring)

Target workflow: system generates optimized track order + per-transition recommendations.
User mixes manually in djay Pro AI using Neural Mix (Drum Cut / Drum Swap).

## Phase 3a: Neural Mix Transition Intelligence

### Transition Types

10 types covering all djay Pro Crossfader FX relevant to techno:

```python
class TransitionType(StrEnum):
    # Neural Mix (stem-based)
    DRUM_CUT = "drum_cut"
    DRUM_SWAP = "drum_swap"
    HARMONIC_SUSTAIN = "harmonic_sustain"
    VOCAL_SUSTAIN = "vocal_sustain"
    NEURAL_ECHO_OUT = "neural_echo_out"
    NEURAL_FADE = "neural_fade"
    # Classic (non-stem)
    EQ = "eq"
    FILTER = "filter"
    ECHO = "echo"
    FADE = "fade"
```

### Selection Logic (priority order)

| Priority | Condition | Type | Reason |
|----------|-----------|------|--------|
| 1 | Both drum-heavy (kick > 0.6) | DRUM_CUT | Remove kick clash |
| 2 | Track B drum-heavy, A melodic | DRUM_SWAP | New groove + old melody |
| 3 | Both melodic + Camelot match | HARMONIC_SUSTAIN | Layer harmonics |
| 4 | Track A has vocal (hp_ratio < 0.4) | VOCAL_SUSTAIN | Sustain vocal phrase |
| 5 | BPM diff > 4 | FILTER | Mask tempo mismatch |
| 6 | High energy_delta (> 2 LUFS) | NEURAL_ECHO_OUT | Smooth exit with echo |
| 7 | Energy drops (A > B) | NEURAL_FADE | Delicate stem fadeout |
| 8 | Both high-energy | EQ | Classic fast bass-swap |
| 9 | Energy rises (B > A) | ECHO | Quick entry with echo |
| 10 | Default | FADE | Simple crossfade |

### Output Types

```python
@dataclass(frozen=True)
class TransitionRecommendation:
    transition_type: TransitionType
    confidence: float           # [0, 1]
    reason: str                 # Human-readable
    alt_type: TransitionType | None
```

### File: `app/services/transition_type.py`

Pure function, no DB dependencies. Takes `TrackFeatures` pair + Camelot compatibility bool.

### Export

**M3U8** for djay Pro import:
```text
#EXTM3U
#EXTINF:432,Artist A - Track Title A
/path/to/track_a.mp3
```

**JSON transition guide** (companion file for DJ reference):
```json
{
  "set_name": "...",
  "energy_arc": "classic",
  "quality_score": 0.84,
  "transitions": [{
    "position": 1,
    "from": "Artist A - Track A",
    "to": "Artist B - Track B",
    "score": 0.87,
    "type": "drum_swap",
    "type_confidence": 0.82,
    "reason": "Track B has stronger kick (0.8 vs 0.4)",
    "alt_type": "eq",
    "bpm_delta": 1.2,
    "energy_delta": 0.5,
    "camelot": "5A -> 5A (same key)"
  }]
}
```

### File: `app/services/set_export.py`

M3U + JSON generation. Takes GAResult + track metadata.

### MCP Enhancements

| Tool | Change |
|------|--------|
| `build_set` | Returns `transitions[].type`, `.reason` |
| `score_transitions` | Returns `recommended_type`, `type_confidence`, `reason` |
| NEW `export_set_m3u` | Generates M3U file + JSON guide |
| NEW `export_set_json` | Full JSON with tracks, transitions, metrics |

## Phase 3b: Optimizer Enhancements

### 3b.1 Full-Fitness 2-opt

Current `_two_opt()` optimizes only transition matrix. Change to use composite
fitness (transition + arc + bpm) for segment reversal decisions.

Trade-off: slower (~50ms per offspring for 40 tracks) but significantly better
energy arc adherence.

### 3b.2 Nearest-Neighbor Initialization

50% of population seeded with greedy nearest-neighbor paths (start from random
track, each next = best neighbor by transition matrix), polished with 2-opt.
50% random for diversity.

### 3b.3 Track Replacement Mutation

5% chance per mutation to replace one track in chromosome with a random unused
track from pool. Only when `track_count < len(all_tracks)`.

### 3b.4 Section-Aware Scoring

New 6th component in `TransitionScoringService`:

```python
MIX_OUT_QUALITY = {
    'outro': 1.0, 'breakdown': 0.85, 'bridge': 0.7,
    'drop': 0.5, 'buildup': 0.3, 'intro': 0.1
}
MIX_IN_QUALITY = {
    'intro': 1.0, 'drop': 0.8, 'buildup': 0.7,
    'breakdown': 0.6, 'bridge': 0.4, 'outro': 0.1
}
```

Updated weights:
```python
WEIGHTS = {
    "bpm": 0.25, "harmonic": 0.20, "energy": 0.20,
    "spectral": 0.15, "groove": 0.10, "structure": 0.10
}
```

Requires loading `track_sections` data for last/first sections of each track.

## File Changes Summary

### New files (Phase 3a)
- `app/services/transition_type.py` — TransitionTypeRecommender
- `app/services/set_export.py` — M3U + JSON export
- `tests/services/test_transition_type.py`
- `tests/services/test_set_export.py`

### Modified files
- `app/utils/audio/_types.py` — TransitionType enum, TransitionRecommendation dataclass
- `app/utils/audio/set_generator.py` — Full-fitness 2-opt, NN init, track replacement
- `app/services/transition_scoring.py` — score_structure() component, updated weights
- `app/mcp/workflows/setbuilder_tools.py` — Enhanced tools + new export tools
- `app/mcp/types.py` — Updated Pydantic models

### Not in scope (YAGNI)
- Audio rendering / stem processing
- ML-based transition classification
- RL-based set generation
- FAD-CLAP quality metrics
- Genre-specific weight presets (deferred)

## Testing Strategy

| Component | Strategy |
|-----------|----------|
| TransitionTypeRecommender | Unit: various TrackFeatures combos -> verify type |
| M3U export | Unit: verify EXTM3U format |
| JSON export | Unit: verify schema + transition metadata |
| Full-fitness 2-opt | Regression: new 2-opt fitness >= old |
| NN init | Regression: initial population fitness > random |
| Section-aware scoring | Unit: outro->intro > drop->drop |

## Research References

- Kim et al. (ISMIR 2020): 1,557 DJ mixes, 86.1% tempo adj <5%
- Zehren et al. (CMJ 2022): expert rule-based at 96% quality
- Algoriddim djay Pro 5: Neural Mix Crossfader FX documentation
- Kell & Tzanetakis (ISMIR 2013): timbral similarity as top predictor
