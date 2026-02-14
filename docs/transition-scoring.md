# Transition Scoring System

## Overview

Система оценки качества переходов между треками использует исследовательски-обоснованную мульти-компонентную формулу. Заменяет примитивный линейный скоринг (BPM + key difference) на сложную взвешенную композицию, использующую 9 аудио-фичей.

## Scoring Components

### 1. BPM Matching (30% weight)

**Formula:** Gaussian decay с σ=8 BPM

```python
score_bpm = exp(-(bpm_diff² / (2 * 8²)))
```

**Features:**
- Поддержка double-time (2x BPM) и half-time (0.5x BPM)
- Основано на Kim et al. (ISMIR 2020): 86.1% tempo adjustments <5%

**Примеры:**
- 128 → 128 BPM: score = 1.0
- 128 → 136 BPM (+8): score ≈ 0.61
- 128 → 144 BPM (+16): score ≈ 0.14

### 2. Harmonic Compatibility (25% weight)

**Formula:** Camelot wheel modulated by harmonic density

```python
raw_camelot = LOOKUP[(key_a, key_b)]
density_factor = 0.3 + 0.7 * avg_harmonic_density
score_harmonic = raw_camelot * factor + 0.8 * (1 - factor)
```

**Features:**
- Использует pre-computed Camelot wheel из `key_edges` table
- Адаптивное взвешивание: percussive techno (low density) снижает вес Camelot
- Melodic techno (high density) усиливает strict harmonic matching

### 3. Energy Matching (20% weight)

**Formula:** Sigmoid decay на LUFS difference

```python
score_energy = 1 / (1 + (lufs_diff / 4)²)
```

- Использует integrated LUFS (ITU-R BS.1770) — gold standard для perceived loudness
- LUFS diff = 0: score = 1.0
- LUFS diff = 4: score = 0.5

### 4. Spectral Similarity (15% weight)

**Formula:** 50% centroid + 50% band balance cosine

```python
centroid_score = 1 - abs(centroid_a - centroid_b) / 7500
band_balance_score = cosine_similarity(band_ratios_a, band_ratios_b)
score_spectral = 0.5 * centroid_score + 0.5 * band_balance_score
```

- Proxy для timbral similarity (Kell & Tzanetakis ISMIR 2013)
- Spectral centroid = perceived "brightness"

### 5. Groove Compatibility (10% weight)

**Formula:** Onset rate relative difference

```python
score_groove = 1 - abs(onset_a - onset_b) / max(onset_a, onset_b)
```

- Captures rhythmic texture beyond simple tempo
- Onset rate = percussive attacks per second

## Feature Utilization

| Component | DB Features Used | Type |
|-----------|------------------|------|
| BPM | `bpm` | Float |
| Harmonic | `key_code`, `key_confidence` (density proxy) | Int, Float |
| Energy | `lufs_i` | Float |
| Spectral | `centroid_mean_hz`, `low_energy`, `mid_energy`, `high_energy` | Float (4) |
| Groove | `onset_rate_mean` | Float |

**Total:** 9 features (up from 3)
**Utilization:** ~60% (up from 5%)

## Implementation

### TransitionScoringService

```python
from app.services.transition_scoring import TransitionScoringService, TrackFeatures

scorer = TransitionScoringService()
scorer.camelot_lookup = camelot_table

features_a = TrackFeatures(
    bpm=128.0, energy_lufs=-14.0, key_code=0,
    harmonic_density=0.8, centroid_hz=2000.0,
    band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0
)

score = scorer.score_transition(features_a, features_b)
```

### CamelotLookupService

```python
from app.services.camelot_lookup import CamelotLookupService

service = CamelotLookupService(session)
lookup = await service.build_lookup_table()
score = service.get_score(from_key=0, to_key=1)
```

### Integration with GA

Transition matrix pre-computed в `SetGenerationService._build_transition_matrix_scored()` перед передачей в `GeneticSetGenerator`.

## Performance

- Matrix computation: O(n²) for n tracks
- 118 tracks → 13,924 pairwise scores
- Computation time: ~50-100ms (vectorized NumPy)
- GA runtime: 2-10 seconds (unchanged, matrix precomputed)

## Expected Metrics

- Camelot compliance: 0% → **80%+**
- Energy arc adherence: MSE reduction **30-50%**
- BPM smoothness: Mean delta <3 BPM для **85%+** transitions
- Transition quality: Overall score **0.7-0.9** (vs 0.3-0.5 primitive)

## Future Enhancements

### Implemented ✅
- 5-component scoring formula
- Camelot lookup from key_edges
- 2-opt local search for GA
- LUFS-based energy matching

### Planned 🔄
- Harmonic density from chroma entropy (replace key_confidence proxy)
- MFCC-based timbral similarity (full 13 coefficients)
- Section-aware mix points (intro/outro detection)

## References

1. Kim et al. (ISMIR 2020): Analysis of 1,557 real DJ mixes
2. Kell & Tzanetakis (ISMIR 2013): Timbral dominance in track ordering
3. Zehren et al. (CMJ 2022): Rule-based vs ML scoring (96% quality)
4. Vande Veire & De Bie (EURASIP 2018): Open-source auto-DJ
