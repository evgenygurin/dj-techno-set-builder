# Phase 2: Scoring Enrichment — Design Document

**Date**: 2026-02-16
**Branch**: `feature/BPM-1-unified-transition-scoring`
**Status**: Design

## Context

Phase 1 implemented the core 5-component scoring formula (BPM Gaussian decay,
Camelot with harmonic density modulation, LUFS energy, spectral centroid + band
balance, groove onset density). All quick wins from the research report are in
place.

However, the system computes several audio features that **aren't used in
scoring**: `kick_prominence`, `hnr_mean_db`, `slope_db_per_oct`, `hp_ratio`.
Additionally, `chroma_entropy` is computed in `detect_key()` but discarded
before persistence, and MFCC vectors (the #1 timbral similarity predictor per
Kell & Tzanetakis ISMIR 2013) are absent entirely.

## Goal

Enrich existing 5 scoring components with unused/new features **without changing
the weight structure** (BPM 30%, Harmonic 25%, Energy 20%, Spectral 15%,
Groove 10%). Each component becomes internally richer while maintaining the same
external interface.

## Architecture: Two Sub-Phases

### Phase 2A — Infrastructure (extraction + persistence)

Add new data to the pipeline. No scoring changes.

### Phase 2B — Scoring Integration

Wire new data into existing score components. Scoring improves; API unchanged.

---

## Phase 2A: Infrastructure

### A1. Add `chroma_entropy` to `KeyResult`

**File**: `app/utils/audio/_types.py`

Add field to `KeyResult`:
```python
@dataclass(frozen=True, slots=True)
class KeyResult:
    key: str
    scale: str
    key_code: int
    confidence: float
    is_atonal: bool
    chroma: NDArray[np.float32]
    chroma_entropy: float  # NEW — Shannon entropy / log2(12), range [0, 1]
```

**File**: `app/utils/audio/key_detect.py`

Return normalized entropy (already computed but discarded):
```python
entropy = _chroma_entropy(mean_chroma)
normalized_entropy = entropy / _MAX_CHROMA_ENTROPY  # [0, 1]

return KeyResult(
    ...,
    chroma_entropy=normalized_entropy,  # NEW
)
```

**Rationale**: `chroma_entropy / log2(12)` gives [0, 1] range where 0 = single
pitch class dominates (very tonal) and 1 = uniform distribution (atonal/noisy).
This is the correct `harmonic_density` proxy — replaces `key_confidence` fallback.

### A2. New MFCC extraction module

**File**: `app/utils/audio/mfcc.py` (NEW)

```python
@dataclass(frozen=True, slots=True)
class MfccResult:
    coefficients: list[float]  # 13 mean MFCC coefficients
    n_mfcc: int = 13

def extract_mfcc(signal: AudioSignal) -> MfccResult:
    """Extract mean MFCC vector using librosa."""
```

**Algorithm**: librosa.feature.mfcc(n_mfcc=13) → mean across time frames → 13-dim
vector. Coefficients 1-13 (skip c0 which is just energy).

**Dependency**: Add `librosa>=0.10` to `[audio]` extra in `pyproject.toml`.

**Note**: librosa is ~20MB with numba. Since it's in the `[audio]` extra
alongside essentia/scipy/numpy, this is acceptable.

### A3. Extend `TrackFeatures` (audio types)

**File**: `app/utils/audio/_types.py`

```python
@dataclass(frozen=True, slots=True)
class TrackFeatures:
    bpm: BpmResult
    key: KeyResult
    loudness: LoudnessResult
    band_energy: BandEnergyResult
    spectral: SpectralResult
    beats: BeatsResult | None = None
    mfcc: MfccResult | None = None  # NEW — Phase 2
```

### A4. DB migration

**File**: Alembic migration `add_chroma_entropy_and_mfcc_vector`

Add to `TrackAudioFeaturesComputed`:

| Column | Type | Constraint | Nullable |
|--------|------|-----------|----------|
| `chroma_entropy` | Float | `BETWEEN 0 AND 1` | Yes |
| `mfcc_vector` | String(500) | — | Yes |

`mfcc_vector` stores JSON: `"[0.12, -0.34, 0.56, ...]"` (13 floats). String
type for SQLite compatibility (PostgreSQL could use ARRAY, but String works
everywhere).

Both nullable — existing rows without these features remain valid.

### A5. Update persistence

**File**: `app/repositories/audio_features.py` — `save_features()`

Add to the `create()` call:
```python
chroma_entropy=features.key.chroma_entropy,
mfcc_vector=json.dumps(features.mfcc.coefficients) if features.mfcc else None,
```

### A6. Update analysis pipeline

**File**: `app/services/track_analysis.py` — `_extract_full_sync()`

Add MFCC extraction (graceful failure like beats):
```python
mfcc_result: MfccResult | None = None
try:
    from app.utils.audio.mfcc import extract_mfcc
    mfcc_result = extract_mfcc(signal)
except Exception:
    self.logger.warning("MFCC extraction failed for track %d", track_id, exc_info=True)

return TrackFeatures(..., mfcc=mfcc_result)
```

**File**: `app/utils/audio/pipeline.py` — `extract_all_features()`

Same pattern: add MFCC extraction with graceful fallback.

### A7. librosa dependency

**File**: `pyproject.toml`

Add `librosa>=0.10` to `audio` extra group alongside essentia, soundfile, etc.

---

## Phase 2B: Scoring Integration

### B1. Expand scoring `TrackFeatures`

**File**: `app/services/transition_scoring.py`

```python
@dataclass(frozen=True, slots=True)
class TrackFeatures:
    bpm: float
    energy_lufs: float
    key_code: int
    harmonic_density: float    # NOW: chroma_entropy (was key_confidence)
    centroid_hz: float
    band_ratios: list[float]
    onset_rate: float
    # NEW Phase 2 fields
    mfcc_vector: list[float] | None = None   # 13 coefficients
    kick_prominence: float = 0.5             # 0-1
    hnr_db: float = 0.0                      # harmonics-to-noise (dB)
    spectral_slope: float = 0.0              # dB/oct
```

All new fields have defaults → backward compatible with Phase 1 callers.

### B2. Update feature conversion

**File**: `app/utils/audio/feature_conversion.py`

```python
def orm_features_to_track_features(feat: TrackAudioFeaturesComputed) -> TrackFeatures:
    # harmonic_density: prefer chroma_entropy, fallback to key_confidence
    harmonic_density = feat.chroma_entropy if feat.chroma_entropy is not None else (feat.key_confidence or 0.5)

    # MFCC: parse JSON if available
    mfcc_vector = None
    if feat.mfcc_vector:
        import json
        mfcc_vector = json.loads(feat.mfcc_vector)

    return TrackFeatures(
        ...,
        harmonic_density=harmonic_density,
        mfcc_vector=mfcc_vector,
        kick_prominence=feat.kick_prominence or 0.5,
        hnr_db=feat.hnr_mean_db or 0.0,
        spectral_slope=feat.slope_db_per_oct or 0.0,
    )
```

### B3. Enrich `score_spectral()` — add MFCC cosine similarity

**Current**: 50% centroid + 50% band balance
**New**: 3 sub-components, weighted dynamically based on MFCC availability:

```python
def score_spectral(self, track_a: TrackFeatures, track_b: TrackFeatures) -> float:
    centroid_score = max(0, 1 - abs(a.centroid_hz - b.centroid_hz) / 7500)
    balance_score = cosine_sim(a.band_ratios, b.band_ratios)

    if a.mfcc_vector and b.mfcc_vector:
        mfcc_score = cosine_sim(a.mfcc_vector, b.mfcc_vector)
        # With MFCC: 40% MFCC + 30% centroid + 30% balance
        return 0.40 * mfcc_score + 0.30 * centroid_score + 0.30 * balance_score
    else:
        # Fallback: original weights
        return 0.50 * centroid_score + 0.50 * balance_score
```

**Rationale**: MFCC is the strongest timbral predictor (Kell & Tzanetakis). When
available, it gets 40% weight. When missing (old data), graceful fallback to
Phase 1 formula.

**Spectral slope** is intentionally NOT added to `score_spectral` — its
discriminative power within techno is low (most tracks have similar slope).
It's available for future subgenre classification.

### B4. Enrich `score_harmonic()` — real chroma entropy + HNR modulation

**Current**: Camelot lookup * density modulation (density = key_confidence)
**New**: Density from chroma_entropy + HNR-based refinement:

```python
def score_harmonic(self, cam_a, cam_b, density_a, density_b,
                   hnr_a=0.0, hnr_b=0.0) -> float:
    raw_camelot = self.camelot_lookup.get((cam_a, cam_b), 0.5)
    avg_density = (density_a + density_b) / 2

    # HNR refinement: high HNR = more harmonic content = Camelot matters more
    # Normalize HNR from typical range [0, 30] dB to [0, 1]
    avg_hnr = (hnr_a + hnr_b) / 2
    hnr_factor = min(max(avg_hnr / 20.0, 0.0), 1.0)

    # Combined factor: density (chroma entropy) + HNR
    # Both low → percussive techno → Camelot barely matters
    # Both high → melodic techno → Camelot critical
    combined = 0.6 * avg_density + 0.4 * hnr_factor
    factor = 0.3 + 0.7 * combined  # [0.3, 1.0]

    return raw_camelot * factor + 0.8 * (1 - factor)
```

**Rationale**: `chroma_entropy` captures tonal complexity from pitch
distribution. HNR captures how "pitched" vs "noisy" the signal is. Together
they give a more accurate picture of whether Camelot matching matters.

### B5. Enrich `score_groove()` — add kick prominence

**Current**: Onset density relative difference only
**New**: 70% onset density + 30% kick prominence similarity:

```python
def score_groove(self, onset_a, onset_b, kick_a=0.5, kick_b=0.5) -> float:
    # Onset density component (original)
    if onset_a <= 0 and onset_b <= 0:
        onset_score = 1.0
    else:
        max_onset = max(onset_a, onset_b, 1e-6)
        onset_score = 1 - abs(onset_a - onset_b) / max_onset

    # Kick prominence component (new)
    kick_score = 1 - abs(kick_a - kick_b)  # both [0,1]

    return 0.70 * onset_score + 0.30 * kick_score
```

**Rationale**: Kick prominence captures whether the beat is driven by heavy kicks
(peak-time) or subtle percussion (minimal). Mixing heavy-kick with light-kick
tracks feels jarring.

### B6. Update `score_transition()` — pass new fields

```python
def score_transition(self, track_a: TrackFeatures, track_b: TrackFeatures) -> float:
    if self.check_hard_constraints(track_a, track_b):
        return 0.0

    bpm_s = self.score_bpm(track_a.bpm, track_b.bpm)
    harm_s = self.score_harmonic(
        track_a.key_code, track_b.key_code,
        track_a.harmonic_density, track_b.harmonic_density,
        track_a.hnr_db, track_b.hnr_db,  # NEW
    )
    energy_s = self.score_energy(track_a.energy_lufs, track_b.energy_lufs)
    spectral_s = self.score_spectral(track_a, track_b)  # uses mfcc_vector
    groove_s = self.score_groove(
        track_a.onset_rate, track_b.onset_rate,
        track_a.kick_prominence, track_b.kick_prominence,  # NEW
    )

    w = self.WEIGHTS  # UNCHANGED: bpm=0.30, harmonic=0.25, energy=0.20, spectral=0.15, groove=0.10
    return (w["bpm"]*bpm_s + w["harmonic"]*harm_s + w["energy"]*energy_s
            + w["spectral"]*spectral_s + w["groove"]*groove_s)
```

### B7. Update `score_components_by_features()`

**File**: `app/services/transition_scoring_unified.py`

The unified service passes ORM → `TrackFeatures` → scorer. Since
`feature_conversion.py` populates the new fields (B2), and the scorer consumes
them (B3-B6), no changes needed in the unified service itself. The conversion
is the single touchpoint.

---

## Testing Strategy

### Phase 2A tests
- **Unit**: `tests/utils/test_mfcc.py` — MFCC extraction on synthetic audio
- **Unit**: `tests/utils/test_key_detect.py` — verify `chroma_entropy` returned
- **Integration**: `tests/test_features_persistence.py` — new fields round-trip DB

### Phase 2B tests
- **Unit**: `tests/services/test_transition_scoring.py` — each enriched component
  - `score_spectral` with and without MFCC (fallback behavior)
  - `score_harmonic` with HNR modulation
  - `score_groove` with kick prominence
- **Parity**: `tests/test_transition_scoring_parity.py` — GA/API/MCP consistency
- **Regression**: Overall score range validation (ensure enrichment doesn't
  skew distribution)

---

## Feature Integration Matrix

| Feature | Computed in | Stored in DB | Used in Scoring (Phase 1) | Used in Scoring (Phase 2) |
|---------|------------|-------------|--------------------------|--------------------------|
| `chroma_entropy` | `key_detect.py` | **NEW** | No (key_confidence fallback) | `score_harmonic` density |
| `mfcc_vector` | **NEW** `mfcc.py` | **NEW** | No | `score_spectral` (40%) |
| `kick_prominence` | `beats.py` | Yes | No | `score_groove` (30%) |
| `hnr_mean_db` | `spectral.py` | Yes | No | `score_harmonic` modulation |
| `slope_db_per_oct` | `spectral.py` | Yes | No | Reserved (subgenre classifier) |
| `hp_ratio` | `beats.py` | Yes | No | Reserved (future percussion scoring) |

---

## Files Changed

### Phase 2A (Infrastructure)
| File | Change |
|------|--------|
| `pyproject.toml` | Add `librosa>=0.10` to `[audio]` extra |
| `app/utils/audio/_types.py` | Add `chroma_entropy` to `KeyResult`, `MfccResult` dataclass, `mfcc` to `TrackFeatures` |
| `app/utils/audio/key_detect.py` | Return `chroma_entropy` in `KeyResult` |
| `app/utils/audio/mfcc.py` | **NEW** — MFCC extraction via librosa |
| `app/utils/audio/__init__.py` | Export `MfccResult` |
| `app/models/features.py` | Add `chroma_entropy`, `mfcc_vector` columns |
| `migrations/versions/xxx_add_chroma_entropy_mfcc.py` | **NEW** — Alembic migration |
| `app/repositories/audio_features.py` | Persist `chroma_entropy`, `mfcc_vector` |
| `app/services/track_analysis.py` | Call MFCC extraction in `_extract_full_sync()` |
| `app/utils/audio/pipeline.py` | Call MFCC extraction in `extract_all_features()` |
| `tests/utils/test_mfcc.py` | **NEW** — MFCC unit tests |
| `tests/utils/test_key_detect.py` | Verify chroma_entropy field |

### Phase 2B (Scoring Integration)
| File | Change |
|------|--------|
| `app/services/transition_scoring.py` | Expand `TrackFeatures`, enrich 3 score methods |
| `app/utils/audio/feature_conversion.py` | Map new ORM fields → scoring TrackFeatures |
| `tests/services/test_transition_scoring.py` | Tests for enriched components |
| `tests/test_transition_scoring_parity.py` | Parity regression |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| librosa import adds ~2s to cold start | Low | Lazy import inside `extract_mfcc()` |
| MFCC unavailable for existing tracks | Low | Graceful fallback in `score_spectral()` |
| Score distribution shift after enrichment | Medium | Regression tests on score ranges |
| HNR normalization wrong range | Low | Clamp to [0, 1], document expected range |

## Decision Log

- **MFCC storage as JSON String**: SQLite compatibility; PostgreSQL ARRAY later
- **Spectral slope NOT in scoring**: Low discriminative power within techno
- **hp_ratio reserved**: Future percussion-focused scoring component
- **MFCC weight 40%**: Research says strongest predictor; balanced against graceful fallback
- **HNR in harmonic (not spectral)**: HNR modulates how much Camelot matters, not timbral similarity
