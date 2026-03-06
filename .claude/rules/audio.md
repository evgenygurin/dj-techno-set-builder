---
paths:
  - "app/utils/audio/**"
  - "app/services/transition_scoring.py"
  - "app/services/track_analysis.py"
  - "app/services/set_generation.py"
  - "app/services/camelot_lookup.py"
  - "app/services/set_export.py"
  - "app/services/set_curation.py"
---

# Audio Analysis & Set Generation

## Audio utils

`app/utils/audio/` — pure-function layer (no DB/ORM deps), 19 modules:

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
| `mood_classifier` | `classify_track()` | `MoodClassification` | Rule-based 6-mood classification (ambient_dub → hard_techno) |
| `set_templates` | `get_template()` | `SetTemplate` | 8 DJ set templates with slot-based energy arcs |

**Pattern**: Each module exports one pure function returning a frozen `@dataclass(frozen=True, slots=True)`. All types defined in `_types.py`.

**Error hierarchy** (`_errors.py`):
- `AudioError` (base)
  - `AudioValidationError` — bad input (known, bubbles up)
  - `AudioAnalysisError` — unexpected failure (wrapped by pipeline)

**Pipeline** wraps unexpected errors in `AudioAnalysisError`, letting known errors (`AudioValidationError`, `FileNotFoundError`) bubble up unchanged.

### Phase 2 optional modules (beats, mfcc)

`beats` and `mfcc` in `pipeline.py` are wrapped in `try/except ImportError` — graceful failure:
- If essentia/scipy not installed → `beats = None`, all rhythm features unavailable
- If librosa not installed → `mfcc = None`
- **Gotcha**: `hp_ratio` from `BeatsResult` is **UNBOUNDED** (harmonic_rms / percussive_rms). NOT 0-1! Techno average = 2.2, range 0.66-17.25. Filter threshold: 8.0
- **Gotcha**: `kick_prominence`, `pulse_clarity`, `onset_rate_mean` also from `beats` — will be None without essentia

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
- Uses 6 repositories: DjSetRepository, DjSetVersionRepository, DjSetItemRepository, AudioFeaturesRepository, SectionsRepository, DjPlaylistItemRepository
- Calls `GeneticSetGenerator` from `app/utils/audio/set_generator.py`
- GA with 2-opt local search for track ordering optimization
- Populates `TrackData.mood` via `classify_track()` for template-aware fitness
- Fitness = weighted sum of: transition scores, energy arc, BPM smoothness, variety, template_slot_fit
- Energy arcs: `classic`, `progressive`, `roller`, `wave`

**Template-aware fitness** (`template_slot_fit`):
- Compares each track against its template slot: mood (50%), energy (30%), BPM (20%)
- When template active, weights rebalance: transition=0.35, template=0.25, arc=0.20, bpm=0.10, variety=0.10

**GAConstraints** (for `rebuild_set`):
- `pinned_ids: frozenset[int]` — must remain in every chromosome
- `excluded_ids: frozenset[int]` — banned from mutations
- Used by `_init_population()` and `_mutate_replace()`

## Set delivery (ОБЯЗАТЕЛЬНО при построении сета)

При каждом построении DJ-сета (`build_set`) ВСЕГДА выполняй полный цикл доставки:

1. **Build** — `dj_build_set(playlist_id, set_name, energy_arc)`
2. **Score** — `dj_score_transitions(set_id, version_id)` — проверить качество
3. **Export** — скопировать MP3 файлы в отдельную директорию:
   ```text
   generated-sets/{set_name}/
   ├── 01. Track Title.mp3
   ├── 02. Track Title.mp3
   ├── ...
   ├── {set_name}.m3u8          # M3U с абсолютными путями к локальным копиям
   └── cheat_sheet.txt          # DJ-подсказка
   ```

4. **Cheat sheet** (`cheat_sheet.txt`) — для каждого трека:
   - Номер, название
   - BPM, тональность (Camelot), LUFS
   - Тип перехода к следующему треку + оценка + причина
   - Проблемные переходы (< 0.85) помечены `!!!`
   - Легенда типов переходов внизу

**Файлы нумеруются** в порядке сета: `01. Title.mp3`, `02. Title.mp3`, ...

**iCloud-стабы**: если файл ещё не скачан из iCloud (blocks < 90% size), пропустить копирование, в M3U указать путь к исходному файлу в `library/`.

**Директория**: `~/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/generated-sets/{sanitized_set_name}/`

## Techno audio criteria (reference)

Used in `scripts/fill_and_verify.py` and `mood_classifier`:

| Parameter | Min | Max | Source |
|-----------|-----|-----|--------|
| BPM | 120 | 155 | `bpm.bpm` |
| LUFS | -20 | -4 | `loudness.lufs_i` |
| Energy mean | 0.05 | — | `band_energy.mid` |
| Onset rate | 1.0 | — | `beats.onset_rate_mean` |
| Kick prominence | 0.05 | — | `beats.kick_prominence` |
| Pulse clarity | 0.02 | — | `beats.pulse_clarity` |
| HP ratio | — | 8.0 | `beats.hp_ratio` (unbounded!) |
| Centroid | 300 Hz | 10000 Hz | `spectral.centroid_mean_hz` |
| Flatness | — | 0.5 | `spectral.flatness_mean` |
| Tempo confidence | 0.3 | — | `bpm.confidence` |
| BPM stability | 0.3 | — | `bpm.stability` |
| Crest factor | — | 30 dB | `loudness.crest_factor_db` |
| LRA | — | 25 LU | `loudness.lra_lu` |
| HNR | -30 dB | — | `spectral.hnr_mean_db` |

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

## Set export

`app/services/set_export.py` — **pure functions** (no DB deps) for M3U and JSON export:

### Extended M3U8 (`export_m3u`)

Generates an M3U8 playlist with standard + custom DJ extensions:

| Tag | Purpose |
|-----|---------|
| `#EXTM3U` | M3U header |
| `#PLAYLIST:` | Set name |
| `#EXTINF:` | Duration + display title |
| `#EXTART:` | Artist name(s) |
| `#EXTGENRE:` | Genre |
| `#EXTVLCOPT:start-time=` | Mix-in point (VLC compatible) |
| `#EXTVLCOPT:stop-time=` | Mix-out point (VLC compatible) |
| `#EXTDJ-BPM:` | Track BPM |
| `#EXTDJ-KEY:` | Musical key (Camelot notation) |
| `#EXTDJ-ENERGY:` | Energy level (LUFS) |
| `#EXTDJ-CUE:` | Cue points: `time=,type=hot\|memory,name=,color=` |
| `#EXTDJ-LOOP:` | Loops: `in=,out=,name=` |
| `#EXTDJ-SECTION:` | Structural sections: `type=intro\|drop\|outro,start=,end=,energy=` |
| `#EXTDJ-EQ:` | Planned EQ: `low=,mid=,high=` |
| `#EXTDJ-TRANSITION:` | Transition to next: `type=,score=,confidence=,bpm_delta=,energy_delta=,camelot=,reason=,alt_type=,mix_out=,mix_in=` |
| `#EXTDJ-NOTE:` | DJ notes |

Custom `#EXTDJ-*` lines are backward compatible: players that don't recognise them simply skip them.

### JSON guide (`export_json_guide`)

Produces a DJ cheat sheet with:
- Set metadata (name, energy arc, quality score, track count)
- Per-track details (title, artists, BPM, key, energy, duration, cue points, loops, sections, EQ, notes)
- Per-transition recommendations (type, confidence, reason, alt_type, score, BPM/energy deltas, Camelot)
- Set-level analytics (BPM range, energy range, avg transition score, total duration)
