---
paths:
  - "app/utils/audio/**"
  - "app/services/transition_scoring.py"
  - "app/services/track_analysis.py"
  - "app/services/set_generation.py"
  - "app/services/camelot_lookup.py"
---

# Audio Analysis & Set Generation

## Audio utils

`app/utils/audio/` — pure-function layer (no DB/ORM deps), 17 modules:

| Module | Function | Output | Description |
|--------|----------|--------|-------------|
| `loader` | `load_audio()` | `AudioData` | Load audio file, resample to mono 44.1kHz |
| `bpm` | `detect_bpm()` | `BpmResult` | BPM detection with confidence score |
| `key_detect` | `detect_key()` | `KeyResult` | Musical key detection (24 keys) |
| `loudness` | `measure_loudness()` | `LoudnessResult` | Integrated LUFS, loudness range, peak |
| `energy` | `compute_energy()` | `EnergyResult` | RMS energy, low/mid/high band ratios |
| `spectral` | `compute_spectral()` | `SpectralResult` | Centroid, bandwidth, rolloff, flatness |
| `beats` | `detect_beats()` | `BeatsResult` | Beat positions and onset rate |
| `groove` | `compute_groove()` | `GrooveResult` | Rhythmic complexity and swing |
| `structure` | `segment_structure()` | `StructureResult` | Section boundaries (intro, drop, outro) |
| `stems` | `separate_stems()` | `StemsResult` | Source separation via Demucs (ML) |
| `camelot` | `key_code_to_camelot()` | `str` | Convert key code to Camelot notation |
| `transition_score` | `score_transition()` | `TransitionResult` | Compatibility score between tracks |
| `set_generator` | `generate_set()` | `SetResult` | GA for optimal track ordering |
| `mfcc` | `extract_mfcc()` | `MfccResult` | 13 mean MFCC coefficients (librosa) |
| `pipeline` | `extract_all_features()` | `AllFeatures` | Orchestrator — runs all analyses |

**Pattern**: Each module exports one pure function returning a frozen `@dataclass(frozen=True, slots=True)`. All types defined in `_types.py`.

**Error hierarchy** (`_errors.py`):
- `AudioError` (base)
  - `AudioValidationError` — bad input (known, bubbles up)
  - `AudioAnalysisError` — unexpected failure (wrapped by pipeline)

**Pipeline** wraps unexpected errors in `AudioAnalysisError`, letting known errors (`AudioValidationError`, `FileNotFoundError`) bubble up unchanged.

## Dependencies

Audio analysis requires the `audio` extra: `uv sync --extra audio` (essentia, soundfile, scipy, numpy, librosa). Stem separation requires the `ml` extra: `uv sync --extra ml` (demucs, torch).

## Transition scoring

`TransitionScoringService` (`app/services/transition_scoring.py`) — **pure service** (no DB):

5-component weighted formula (Phase 2 enriched):

| Component | Weight | Method | Phase 2 enrichment |
|-----------|--------|--------|--------------------|
| BPM | 0.30 | `score_bpm()` | Gaussian (sigma=8) + double/half-time |
| Harmonic | 0.25 | `score_harmonic()` | Camelot * (60% chroma entropy + 40% HNR) |
| Energy | 0.20 | `score_energy()` | Sigmoid on LUFS diff |
| Spectral | 0.15 | `score_spectral()` | 40% MFCC cosine + 30% centroid + 30% band balance (fallback: 50/50 without MFCC) |
| Groove | 0.10 | `score_groove()` | 70% onset density + 30% kick prominence |

Hard constraints (filter-then-rank): BPM diff >10, Camelot dist >=5, energy >6 LUFS → score=0.0.

Input: `TrackFeatures` — frozen dataclass with `slots=True`:
```python
@dataclass(frozen=True, slots=True)
class TrackFeatures:
    bpm: float
    energy_lufs: float
    key_code: int
    harmonic_density: float  # from chroma entropy
    centroid_hz: float
    band_ratios: list[float]  # [low, mid, high]
    onset_rate: float
    # Phase 2 (optional, backward-compat defaults)
    mfcc_vector: list[float] | None = None  # 13 MFCC coefficients
    kick_prominence: float = 0.5
    hnr_db: float = 0.0
    spectral_slope: float = 0.0
```

**ORM→TrackFeatures conversion**: `app/utils/audio/feature_conversion.py` — single source of truth.

## Set generation

`SetGenerationService` (`app/services/set_generation.py`) — **multi-repo service**:
- Uses 4 repositories: DjSetRepository, DjSetVersionRepository, DjSetItemRepository, AudioFeaturesRepository
- Calls `GeneticSetGenerator` from `app/utils/audio/set_generator.py`
- GA with 2-opt local search for track ordering optimization
- Fitness = sum of transition scores + energy arc adherence
- Energy arcs: `classic`, `progressive`, `roller`, `wave`

## TrackAnalysisService

`app/services/track_analysis.py` — **multi-repo service** bridging utils and repositories:
- Constructor takes TrackRepository, AudioFeaturesRepository, SectionsRepository
- Calls pure utils functions for computation, then persists results via repositories
- Wraps analysis errors and records pipeline run status

## CamelotLookupService

`app/services/camelot_lookup.py` — builds 24-key Camelot wheel lookup table:
- `build_lookup_table()` — populates `_lookup: dict[int, dict[int, float]]`
- Used by TransitionScoringService for harmonic scoring
- Maps key codes to compatibility scores based on Camelot wheel adjacency
