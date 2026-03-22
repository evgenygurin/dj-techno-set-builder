# Phase 2: Scoring Enrichment — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich existing 5-component transition scoring with MFCC timbral similarity, real chroma entropy, kick prominence, and HNR — without changing weight structure.

**Architecture:** Two sub-phases: 2A adds infrastructure (librosa dep, MFCC extraction module, DB migration for 2 new columns, persistence updates) and 2B wires new data into existing score_spectral, score_harmonic, and score_groove methods.

**Tech Stack:** Python 3.12, librosa>=0.10, essentia, SQLAlchemy 2.0, Alembic, pytest

**Design doc:** `docs/plans/2026-02-16-phase2-scoring-enrichment-design.md`

---

## Phase 2A: Infrastructure

### Task 1: Add librosa dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add librosa to audio extra**

In `pyproject.toml`, under `[project.optional-dependencies]`, add `librosa>=0.10` to the `audio` list:

```toml
[project.optional-dependencies]
audio = [
    "essentia>=2.1b6.dev1389",
    "soundfile>=0.13",
    "scipy>=1.12",
    "numpy>=1.26",
    "librosa>=0.10",
]
```

**Step 2: Install**

Run: `uv sync --extra audio`
Expected: librosa installs successfully alongside essentia.

**Step 3: Verify import**

Run: `uv run python -c "import librosa; print(librosa.__version__)"`
Expected: Version >= 0.10.x

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add librosa to audio extra deps for MFCC extraction"
```

---

### Task 2: Add `chroma_entropy` to `KeyResult` dataclass

**Files:**
- Modify: `app/utils/audio/_types.py:27-33`
- Modify: `app/utils/audio/key_detect.py:96-108`
- Test: `tests/utils/test_key_detect.py`

**Step 1: Write the failing test**

Add to `tests/utils/test_key_detect.py` inside `class TestDetectKey`:

```python
def test_chroma_entropy_returned(self, long_sine_440hz: AudioSignal) -> None:
    result = detect_key(long_sine_440hz)
    assert hasattr(result, "chroma_entropy")
    assert 0.0 <= result.chroma_entropy <= 1.0

def test_chroma_entropy_pure_tone_low(self, long_sine_440hz: AudioSignal) -> None:
    """A pure sine (single pitch) should have low chroma entropy."""
    result = detect_key(long_sine_440hz)
    assert result.chroma_entropy < 0.5  # concentrated energy = low entropy

def test_chroma_entropy_chord_higher(self, a_major_chord: AudioSignal) -> None:
    """A chord (3 pitches) should have higher chroma entropy than a pure tone."""
    from app.utils.audio.key_detect import detect_key as dk

    pure = dk(AudioSignal(
        samples=long_sine_440hz_samples(3.0),
        sample_rate=44100,
        duration_s=3.0,
    ))
    chord = detect_key(a_major_chord)
    # Chord has more spread across pitch classes
    assert chord.chroma_entropy >= pure.chroma_entropy
```

Wait — the last test requires a helper. Simplify: just test the field exists and is in range.

Actually, keep it simpler:

```python
def test_chroma_entropy_returned(self, long_sine_440hz: AudioSignal) -> None:
    """KeyResult must include normalized chroma entropy [0, 1]."""
    result = detect_key(long_sine_440hz)
    assert hasattr(result, "chroma_entropy")
    assert 0.0 <= result.chroma_entropy <= 1.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/utils/test_key_detect.py::TestDetectKey::test_chroma_entropy_returned -v`
Expected: FAIL — `KeyResult` has no `chroma_entropy` field.

**Step 3: Add field to KeyResult**

In `app/utils/audio/_types.py`, update `KeyResult`:

```python
@dataclass(frozen=True, slots=True)
class KeyResult:
    key: str  # e.g. "A"
    scale: str  # "minor" or "major"
    key_code: int  # 0-23 (pitch_class * 2 + mode)
    confidence: float  # 0-1
    is_atonal: bool
    chroma: NDArray[np.float32]  # 12-dim mean HPCP vector
    chroma_entropy: float  # Shannon entropy / log2(12), normalized [0, 1]
```

**Step 4: Return chroma_entropy from detect_key()**

In `app/utils/audio/key_detect.py`, around line 96-108, change:

```python
# Before:
entropy = _chroma_entropy(mean_chroma)
is_atonal = entropy > _ATONAL_ENTROPY_THRESHOLD * _MAX_CHROMA_ENTROPY

key_code = _key_to_key_code(key, scale)

return KeyResult(
    key=key,
    scale=scale,
    key_code=key_code,
    confidence=float(np.clip(strength, 0.0, 1.0)),
    is_atonal=is_atonal,
    chroma=mean_chroma,
)

# After:
entropy = _chroma_entropy(mean_chroma)
is_atonal = entropy > _ATONAL_ENTROPY_THRESHOLD * _MAX_CHROMA_ENTROPY
normalized_entropy = float(np.clip(entropy / _MAX_CHROMA_ENTROPY, 0.0, 1.0))

key_code = _key_to_key_code(key, scale)

return KeyResult(
    key=key,
    scale=scale,
    key_code=key_code,
    confidence=float(np.clip(strength, 0.0, 1.0)),
    is_atonal=is_atonal,
    chroma=mean_chroma,
    chroma_entropy=normalized_entropy,
)
```

**Step 5: Fix any callers that construct KeyResult manually**

Check `app/services/transition_persistence.py:154` — it constructs `KeyResult`
manually. Add `chroma_entropy=0.5` as a default there.

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/utils/test_key_detect.py -v`
Expected: All tests PASS, including new `test_chroma_entropy_returned`.

**Step 7: Run full test suite**

Run: `uv run pytest -x -q`
Expected: No regressions. If any test fails due to `KeyResult` missing
`chroma_entropy` kwarg, fix the construction site.

**Step 8: Commit**

```bash
git add app/utils/audio/_types.py app/utils/audio/key_detect.py \
       app/services/transition_persistence.py \
       tests/utils/test_key_detect.py
git commit -m "feat: add chroma_entropy to KeyResult (normalized Shannon entropy)"
```

---

### Task 3: Create MFCC extraction module

**Files:**
- Create: `app/utils/audio/mfcc.py`
- Modify: `app/utils/audio/_types.py` (add `MfccResult`)
- Modify: `app/utils/audio/__init__.py` (export)
- Test: `tests/utils/test_mfcc.py` (NEW)

**Step 1: Add MfccResult dataclass**

In `app/utils/audio/_types.py`, add after `SpectralResult`:

```python
@dataclass(frozen=True, slots=True)
class MfccResult:
    """Mean MFCC coefficients for timbral fingerprinting."""

    coefficients: list[float]  # 13 mean MFCC coefficients (c1-c13, skip c0)
    n_mfcc: int = 13
```

**Step 2: Write the failing test**

Create `tests/utils/test_mfcc.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

librosa = pytest.importorskip("librosa")

from app.utils.audio import AudioSignal  # noqa: E402
from app.utils.audio.mfcc import extract_mfcc  # noqa: E402

SR = 44100

@pytest.fixture
def tone_5s() -> AudioSignal:
    """5-second 440 Hz sine wave."""
    duration = 5.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (0.8 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

@pytest.fixture
def noise_5s() -> AudioSignal:
    """5-second white noise."""
    rng = np.random.default_rng(42)
    duration = 5.0
    samples = (0.3 * rng.standard_normal(int(SR * duration))).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

class TestExtractMfcc:
    def test_returns_mfcc_result(self, tone_5s: AudioSignal) -> None:
        result = extract_mfcc(tone_5s)
        assert hasattr(result, "coefficients")
        assert len(result.coefficients) == 13
        assert result.n_mfcc == 13

    def test_coefficients_are_finite(self, tone_5s: AudioSignal) -> None:
        result = extract_mfcc(tone_5s)
        for c in result.coefficients:
            assert np.isfinite(c), f"Non-finite MFCC coefficient: {c}"

    def test_different_signals_different_mfcc(
        self, tone_5s: AudioSignal, noise_5s: AudioSignal
    ) -> None:
        """Sine tone and white noise must produce different MFCC vectors."""
        mfcc_tone = extract_mfcc(tone_5s)
        mfcc_noise = extract_mfcc(noise_5s)

        vec_a = np.array(mfcc_tone.coefficients)
        vec_b = np.array(mfcc_noise.coefficients)

        # Cosine similarity should be noticeably less than 1.0
        cos_sim = np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-10)
        assert cos_sim < 0.95, f"Expected different MFCCs, got cosine similarity {cos_sim:.3f}"

    def test_same_signal_identical_mfcc(self, tone_5s: AudioSignal) -> None:
        """Deterministic: same input → same output."""
        a = extract_mfcc(tone_5s)
        b = extract_mfcc(tone_5s)
        assert a.coefficients == b.coefficients
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/utils/test_mfcc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.audio.mfcc'`

**Step 4: Implement extract_mfcc**

Create `app/utils/audio/mfcc.py`:

```python
"""MFCC extraction for timbral similarity scoring.

Uses librosa to compute mean MFCC coefficients (c1-c13) across all frames.
These 13 coefficients capture the spectral envelope — the #1 predictor of
"sounds right together" per Kell & Tzanetakis (ISMIR 2013).
"""

from __future__ import annotations

from app.utils.audio._types import AudioSignal, MfccResult

def extract_mfcc(
    signal: AudioSignal,
    *,
    n_mfcc: int = 14,
    n_fft: int = 2048,
    hop_length: int = 512,
) -> MfccResult:
    """Extract mean MFCC vector from audio signal.

    Args:
        signal: Mono audio signal.
        n_mfcc: Number of MFCCs to compute (14, then skip c0 → 13 used).
        n_fft: FFT window size.
        hop_length: Hop between frames.

    Returns:
        MfccResult with 13 mean coefficients (c1-c13).
    """
    import librosa
    import numpy as np

    # librosa expects float32 numpy array
    mfcc_matrix = librosa.feature.mfcc(
        y=signal.samples,
        sr=signal.sample_rate,
        n_mfcc=n_mfcc,
        n_fft=n_fft,
        hop_length=hop_length,
    )

    # Skip c0 (energy), take c1-c13
    mfcc_no_c0 = mfcc_matrix[1:]  # shape: (n_mfcc-1, n_frames)

    # Mean across time frames
    mean_mfcc = np.mean(mfcc_no_c0, axis=1)  # shape: (13,)

    return MfccResult(
        coefficients=[float(v) for v in mean_mfcc],
        n_mfcc=len(mean_mfcc),
    )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/utils/test_mfcc.py -v`
Expected: All 4 tests PASS.

**Step 6: Export from __init__.py**

In `app/utils/audio/__init__.py`, add imports and `__all__` entries:

- Import: `from app.utils.audio._types import MfccResult`
- Import: `from app.utils.audio.mfcc import extract_mfcc` (only if needed externally)
- Add `"MfccResult"` to `__all__` (alphabetically after `LoudnessResult`)

**Step 7: Lint check**

Run: `uv run ruff check app/utils/audio/mfcc.py app/utils/audio/_types.py app/utils/audio/__init__.py`
Expected: Clean or fixable.

**Step 8: Commit**

```bash
git add app/utils/audio/mfcc.py app/utils/audio/_types.py \
       app/utils/audio/__init__.py tests/utils/test_mfcc.py
git commit -m "feat: add MFCC extraction module (librosa, 13 mean coefficients)"
```

---

### Task 4: Add `mfcc` field to audio `TrackFeatures`

**Files:**
- Modify: `app/utils/audio/_types.py:136-145`

**Step 1: Add mfcc field**

In `app/utils/audio/_types.py`, update `TrackFeatures`:

```python
@dataclass(frozen=True, slots=True)
class TrackFeatures:
    """Complete feature set for one track."""

    bpm: BpmResult
    key: KeyResult
    loudness: LoudnessResult
    band_energy: BandEnergyResult
    spectral: SpectralResult
    beats: BeatsResult | None = None  # Phase 2: optional
    mfcc: MfccResult | None = None  # Phase 2: optional
```

**Step 2: Run existing tests**

Run: `uv run pytest -x -q`
Expected: PASS — new field is optional with default None.

**Step 3: Commit**

```bash
git add app/utils/audio/_types.py
git commit -m "feat: add mfcc field to audio TrackFeatures dataclass"
```

---

### Task 5: DB migration — add `chroma_entropy` and `mfcc_vector` columns

**Files:**
- Modify: `app/models/features.py`
- Create: `migrations/versions/` directory + migration file

**Step 1: Add columns to ORM model**

In `app/models/features.py`, add after `hnr_mean_db` (line ~135):

```python
    hnr_mean_db: Mapped[float | None] = mapped_column(Float)
    chroma_entropy: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("chroma_entropy BETWEEN 0 AND 1", name="ck_taf_chroma_entropy"),
    )

    # -- MFCC (Phase 2) --
    mfcc_vector: Mapped[str | None] = mapped_column(String(500))
```

**Step 2: Create Alembic migration**

Run:
```bash
mkdir -p /Users/laptop/dev/dj-techno-set-builder/migrations/versions
uv run alembic revision --autogenerate -m "add chroma_entropy and mfcc_vector to track_audio_features_computed"
```

If autogenerate doesn't work (no existing migration history), create manually:

```python
"""add chroma_entropy and mfcc_vector to track_audio_features_computed

Revision ID: <auto>
"""

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.add_column(
        "track_audio_features_computed",
        sa.Column("chroma_entropy", sa.Float(), nullable=True),
    )
    op.add_column(
        "track_audio_features_computed",
        sa.Column("mfcc_vector", sa.String(500), nullable=True),
    )
    # Add check constraint (PostgreSQL only, SQLite ignores)
    op.create_check_constraint(
        "ck_taf_chroma_entropy",
        "track_audio_features_computed",
        "chroma_entropy BETWEEN 0 AND 1",
    )

def downgrade() -> None:
    op.drop_constraint("ck_taf_chroma_entropy", "track_audio_features_computed")
    op.drop_column("track_audio_features_computed", "mfcc_vector")
    op.drop_column("track_audio_features_computed", "chroma_entropy")
```

**Step 3: Verify migration applies**

Run: `uv run alembic upgrade head`
Expected: Migration applies without errors.

**Step 4: Commit**

```bash
git add app/models/features.py migrations/
git commit -m "feat: add chroma_entropy and mfcc_vector columns (Alembic migration)"
```

---

### Task 6: Update persistence — save new fields

**Files:**
- Modify: `app/repositories/audio_features.py:60-127`
- Test: Verify via existing integration tests

**Step 1: Update save_features()**

In `app/repositories/audio_features.py`, inside `save_features()`, add to the
`create()` call (after line 120, the `chroma=` line):

```python
            chroma=json.dumps([float(v) for v in features.key.chroma]),
            chroma_entropy=features.key.chroma_entropy,  # NEW
            # Phase 2: MFCC (optional)
            mfcc_vector=json.dumps(features.mfcc.coefficients) if features.mfcc else None,
            # Phase 2: beats (optional)
            onset_rate_mean=beats.onset_rate_mean if beats else None,
```

**Step 2: Run existing tests**

Run: `uv run pytest tests/ -x -q`
Expected: PASS — `mfcc` is None by default, `chroma_entropy` now populated.

**Step 3: Commit**

```bash
git add app/repositories/audio_features.py
git commit -m "feat: persist chroma_entropy and mfcc_vector to DB"
```

---

### Task 7: Update analysis pipeline — extract MFCC

**Files:**
- Modify: `app/utils/audio/pipeline.py`
- Modify: `app/services/track_analysis.py`

**Step 1: Update pipeline.py**

In `app/utils/audio/pipeline.py`, add MFCC extraction with graceful fallback:

```python
# Add import at top:
# (no top-level import — lazy for optional dep)

def extract_all_features(
    path: str | Path,
    *,
    target_sr: int = 44100,
) -> TrackFeatures:
    # ... existing code ...

    spectral_result = _run_stage("spectral", path_str, extract_spectral_features, signal)

    # Phase 2: MFCC extraction (optional, graceful failure)
    mfcc_result = None
    try:
        from app.utils.audio.mfcc import extract_mfcc
        mfcc_result = _run_stage("mfcc", path_str, extract_mfcc, signal)
    except ImportError:
        logger.debug("librosa not installed — skipping MFCC extraction")
    except Exception:
        logger.warning("MFCC extraction failed for %s", path, exc_info=True)

    return TrackFeatures(
        bpm=bpm_result,
        key=key_result,
        loudness=loudness_result,
        band_energy=band_energy_result,
        spectral=spectral_result,
        mfcc=mfcc_result,
    )
```

**Step 2: Update track_analysis.py**

In `app/services/track_analysis.py`, inside `_extract_full_sync()`, add MFCC
extraction (same pattern as beats — graceful failure):

```python
        # Phase 2: MFCC extraction (optional, graceful failure)
        mfcc_result = None
        try:
            from app.utils.audio.mfcc import extract_mfcc
            mfcc_result = extract_mfcc(signal)
        except Exception:
            self.logger.warning("MFCC extraction failed for track %d", track_id, exc_info=True)

        return TrackFeatures(
            bpm=bpm_result,
            key=key_result,
            loudness=loudness_result,
            band_energy=band_energy_result,
            spectral=spectral_result,
            beats=beats_result,
            mfcc=mfcc_result,
        )
```

**Step 3: Run tests**

Run: `uv run pytest -x -q`
Expected: PASS.

**Step 4: Commit**

```bash
git add app/utils/audio/pipeline.py app/services/track_analysis.py
git commit -m "feat: integrate MFCC extraction into analysis pipeline"
```

---

### Task 8: Phase 2A checkpoint — full lint + test

**Step 1: Lint**

Run: `uv run ruff check && uv run ruff format --check`
Expected: Clean. Fix any issues.

**Step 2: Type check**

Run: `uv run mypy app/`
Expected: Clean. Add `librosa` to mypy `ignore_missing_imports` in
`pyproject.toml` if needed.

**Step 3: Full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

**Step 4: Commit any lint fixes**

```bash
git add -u
git commit -m "chore: lint fixes for Phase 2A"
```

---

## Phase 2B: Scoring Integration

### Task 9: Expand scoring `TrackFeatures` with new fields

**Files:**
- Modify: `app/services/transition_scoring.py:26-37`
- Test: `tests/services/test_transition_scoring.py`

**Step 1: Write failing test — new fields exist**

Add to `tests/services/test_transition_scoring.py`:

```python
def test_track_features_new_fields_have_defaults():
    """Phase 2 fields should be optional with defaults."""
    tf = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0,
        harmonic_density=0.5, centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
    )
    assert tf.mfcc_vector is None
    assert tf.kick_prominence == 0.5
    assert tf.hnr_db == 0.0
    assert tf.spectral_slope == 0.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/services/test_transition_scoring.py::test_track_features_new_fields_have_defaults -v`
Expected: FAIL — no such attributes.

**Step 3: Add fields to scoring TrackFeatures**

In `app/services/transition_scoring.py`, update `TrackFeatures`:

```python
@dataclass(frozen=True, slots=True)
class TrackFeatures:
    """Minimal feature set for transition scoring."""

    bpm: float
    energy_lufs: float  # Integrated LUFS (ITU-R BS.1770)
    key_code: int  # 0-23
    harmonic_density: float  # Chroma entropy / log(12), range [0, 1]
    centroid_hz: float  # Spectral centroid mean
    band_ratios: list[float]  # [low, mid, high] energy ratios, sum=1.0
    onset_rate: float  # Onsets per second
    # Phase 2 enrichment fields (all optional with backward-compat defaults)
    mfcc_vector: list[float] | None = None  # 13 mean MFCC coefficients
    kick_prominence: float = 0.5  # 0-1, kick energy at beat positions
    hnr_db: float = 0.0  # Harmonics-to-noise ratio (dB)
    spectral_slope: float = 0.0  # Spectral slope (dB/octave)
```

**Step 4: Run test**

Run: `uv run pytest tests/services/test_transition_scoring.py -v`
Expected: All PASS including new test.

**Step 5: Commit**

```bash
git add app/services/transition_scoring.py tests/services/test_transition_scoring.py
git commit -m "feat: add Phase 2 fields to scoring TrackFeatures (backward compatible)"
```

---

### Task 10: Update feature_conversion.py — map new ORM fields

**Files:**
- Modify: `app/utils/audio/feature_conversion.py`
- Test: `tests/test_transition_scoring_parity.py` (existing tests)

**Step 1: Write failing test**

Add to `tests/test_transition_scoring_parity.py`, in `class TestOrmConversion`:

```python
def test_chroma_entropy_preferred_over_key_confidence(self) -> None:
    """When chroma_entropy is set, it should be used for harmonic_density."""
    feat = self._mock_feat()
    feat.chroma_entropy = 0.42
    feat.key_confidence = 0.85
    tf = orm_features_to_track_features(feat)
    assert tf.harmonic_density == 0.42

def test_chroma_entropy_fallback_to_key_confidence(self) -> None:
    """When chroma_entropy is None, fall back to key_confidence."""
    feat = self._mock_feat()
    feat.chroma_entropy = None
    feat.key_confidence = 0.85
    tf = orm_features_to_track_features(feat)
    assert tf.harmonic_density == 0.85

def test_new_phase2_fields_mapped(self) -> None:
    """kick_prominence, hnr_mean_db, slope_db_per_oct should be mapped."""
    feat = self._mock_feat()
    feat.kick_prominence = 0.7
    feat.hnr_mean_db = 12.5
    feat.slope_db_per_oct = -3.2
    feat.mfcc_vector = "[1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0, 9.0, -10.0, 11.0, -12.0, 13.0]"
    tf = orm_features_to_track_features(feat)
    assert tf.kick_prominence == 0.7
    assert tf.hnr_db == 12.5
    assert tf.spectral_slope == -3.2
    assert tf.mfcc_vector is not None
    assert len(tf.mfcc_vector) == 13

def test_new_phase2_fields_fallbacks(self) -> None:
    """None values should use safe defaults."""
    feat = self._mock_feat()
    feat.kick_prominence = None
    feat.hnr_mean_db = None
    feat.slope_db_per_oct = None
    feat.mfcc_vector = None
    feat.chroma_entropy = None
    tf = orm_features_to_track_features(feat)
    assert tf.kick_prominence == 0.5
    assert tf.hnr_db == 0.0
    assert tf.spectral_slope == 0.0
    assert tf.mfcc_vector is None
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_transition_scoring_parity.py::TestOrmConversion -v`
Expected: FAIL — new attributes not returned.

**Step 3: Update feature_conversion.py**

Replace the full function in `app/utils/audio/feature_conversion.py`:

```python
def orm_features_to_track_features(feat: TrackAudioFeaturesComputed) -> TrackFeatures:
    """Convert ``TrackAudioFeaturesComputed`` ORM row to ``TrackFeatures``.

    Mapping rules:
    * ``harmonic_density`` ← ``chroma_entropy`` (fallback: ``key_confidence``)
    * ``band_ratios`` ← normalised ``[low_energy, mid_energy, high_energy]``
    * ``onset_rate`` ← ``onset_rate_mean`` (Phase-2 field, fallback = 5.0)
    * ``mfcc_vector`` ← JSON-parsed ``mfcc_vector`` (Phase-2, nullable)
    * ``kick_prominence`` ← ``kick_prominence`` (Phase-2, fallback = 0.5)
    * ``hnr_db`` ← ``hnr_mean_db`` (Phase-2, fallback = 0.0)
    * ``spectral_slope`` ← ``slope_db_per_oct`` (Phase-2, fallback = 0.0)
    """
    import json as _json

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

    return TrackFeatures(
        bpm=feat.bpm,
        energy_lufs=feat.lufs_i,
        key_code=feat.key_code if feat.key_code is not None else 0,
        harmonic_density=harmonic_density,
        centroid_hz=feat.centroid_mean_hz or 2000.0,
        band_ratios=band_ratios,
        onset_rate=feat.onset_rate_mean or 5.0,
        mfcc_vector=mfcc_vector,
        kick_prominence=feat.kick_prominence or 0.5,
        hnr_db=feat.hnr_mean_db or 0.0,
        spectral_slope=feat.slope_db_per_oct or 0.0,
    )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_transition_scoring_parity.py::TestOrmConversion -v`
Expected: All PASS.

**Step 5: Run full parity suite**

Run: `uv run pytest tests/test_transition_scoring_parity.py -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add app/utils/audio/feature_conversion.py tests/test_transition_scoring_parity.py
git commit -m "feat: map Phase 2 fields in ORM→TrackFeatures conversion"
```

---

### Task 11: Enrich `score_spectral()` — add MFCC cosine similarity

**Files:**
- Modify: `app/services/transition_scoring.py:159-186`
- Test: `tests/services/test_transition_scoring.py`

**Step 1: Write failing tests**

Add to `tests/services/test_transition_scoring.py`:

```python
def test_score_spectral_with_mfcc():
    """When MFCC vectors are present, they should contribute to spectral score."""
    service = TransitionScoringService()

    # Identical MFCC vectors → high score
    features_a = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=[1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0, 9.0, -10.0, 11.0, -12.0, 13.0],
    )
    features_b = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=[1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0, 9.0, -10.0, 11.0, -12.0, 13.0],
    )

    score = service.score_spectral(features_a, features_b)
    assert score > 0.95  # Identical everything

def test_score_spectral_mfcc_different():
    """Different MFCC vectors should lower spectral score."""
    service = TransitionScoringService()

    features_a = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=[10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
    )
    features_b = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=[-10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0],
    )

    score = service.score_spectral(features_a, features_b)
    assert score < 0.5  # Opposite MFCC vectors = very different timbre

def test_score_spectral_fallback_without_mfcc():
    """Without MFCC, should use Phase 1 formula (50/50 centroid+balance)."""
    service = TransitionScoringService()

    features_a = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=None,
    )
    features_b = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=None,
    )

    score = service.score_spectral(features_a, features_b)
    assert score > 0.9  # Identical centroid + balance
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/services/test_transition_scoring.py::test_score_spectral_with_mfcc -v`
Expected: FAIL — current code ignores `mfcc_vector`.

**Step 3: Implement enriched score_spectral()**

Replace `score_spectral()` in `app/services/transition_scoring.py`:

```python
    def score_spectral(self, track_a: TrackFeatures, track_b: TrackFeatures) -> float:
        """Timbral similarity: centroid + band balance + MFCC cosine.

        When MFCC vectors are available: 40% MFCC + 30% centroid + 30% balance.
        Without MFCC (Phase 1 fallback): 50% centroid + 50% balance.

        References:
        - Kell & Tzanetakis (ISMIR 2013): MFCC is the strongest timbral predictor
        - Spectral contrast has lowest RMSE (2.783) for similarity prediction
        """
        # Centroid component (normalized by 7500 Hz typical range)
        centroid_diff = abs(track_a.centroid_hz - track_b.centroid_hz)
        centroid_score = max(0.0, 1.0 - centroid_diff / 7500.0)

        # Band balance component (cosine similarity)
        vec_a = np.array(track_a.band_ratios)
        vec_b = np.array(track_b.band_ratios)
        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        balance_score = float(dot / (norm_a * norm_b)) if norm_a > 0 and norm_b > 0 else 0.0

        # MFCC component (when available)
        if track_a.mfcc_vector and track_b.mfcc_vector:
            mfcc_a = np.array(track_a.mfcc_vector)
            mfcc_b = np.array(track_b.mfcc_vector)
            mfcc_dot = np.dot(mfcc_a, mfcc_b)
            mfcc_norm_a = np.linalg.norm(mfcc_a)
            mfcc_norm_b = np.linalg.norm(mfcc_b)
            if mfcc_norm_a > 0 and mfcc_norm_b > 0:
                # Cosine similarity: [-1, 1] → rescale to [0, 1]
                cos_sim = float(mfcc_dot / (mfcc_norm_a * mfcc_norm_b))
                mfcc_score = (cos_sim + 1.0) / 2.0  # [-1,1] → [0,1]
            else:
                mfcc_score = 0.5  # Neutral if zero vectors

            # With MFCC: 40% MFCC + 30% centroid + 30% balance
            return 0.40 * mfcc_score + 0.30 * centroid_score + 0.30 * balance_score

        # Fallback: Phase 1 formula
        return 0.50 * centroid_score + 0.50 * balance_score
```

**Step 4: Run tests**

Run: `uv run pytest tests/services/test_transition_scoring.py -v`
Expected: All PASS.

**Step 5: Commit**

```bash
git add app/services/transition_scoring.py tests/services/test_transition_scoring.py
git commit -m "feat: enrich score_spectral with MFCC cosine similarity (40/30/30)"
```

---

### Task 12: Enrich `score_harmonic()` — chroma entropy + HNR modulation

**Files:**
- Modify: `app/services/transition_scoring.py:114-140`
- Test: `tests/services/test_transition_scoring.py`

**Step 1: Write failing tests**

Add to `tests/services/test_transition_scoring.py`:

```python
def test_score_harmonic_hnr_modulation():
    """High HNR (more harmonic content) should increase Camelot weight."""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 6): 0.5}  # Mid-distance key pair

    # High HNR = melodic = Camelot matters more
    score_high_hnr = service.score_harmonic(
        cam_a=0, cam_b=6, density_a=0.5, density_b=0.5,
        hnr_a=20.0, hnr_b=20.0,
    )

    # Low HNR = noisy/percussive = Camelot matters less
    score_low_hnr = service.score_harmonic(
        cam_a=0, cam_b=6, density_a=0.5, density_b=0.5,
        hnr_a=2.0, hnr_b=2.0,
    )

    # With bad Camelot (0.5), high HNR should produce LOWER score
    # because it weights the bad Camelot more heavily
    assert score_low_hnr > score_high_hnr

def test_score_harmonic_backward_compatible():
    """Without hnr kwargs, should produce same result as Phase 1."""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 0): 1.0}

    score = service.score_harmonic(cam_a=0, cam_b=0, density_a=0.8, density_b=0.8)
    assert score == pytest.approx(1.0, abs=0.05)
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/services/test_transition_scoring.py::test_score_harmonic_hnr_modulation -v`
Expected: FAIL — `score_harmonic()` doesn't accept `hnr_a`/`hnr_b`.

**Step 3: Implement enriched score_harmonic()**

Replace `score_harmonic()`:

```python
    def score_harmonic(
        self,
        cam_a: int,
        cam_b: int,
        density_a: float,
        density_b: float,
        hnr_a: float = 0.0,
        hnr_b: float = 0.0,
    ) -> float:
        """Camelot score modulated by harmonic density and HNR.

        For percussive techno (low density + low HNR), Camelot matters less.
        For melodic techno (high density + high HNR), Camelot is critical.

        Args:
            cam_a: Key code of track A (0-23)
            cam_b: Key code of track B (0-23)
            density_a: Harmonic density of A [0, 1] (from chroma entropy)
            density_b: Harmonic density of B [0, 1]
            hnr_a: Harmonics-to-noise ratio of A (dB, typically 0-30)
            hnr_b: Harmonics-to-noise ratio of B (dB)

        Returns:
            Modulated harmonic compatibility [0, 1]
        """
        raw_camelot = self.camelot_lookup.get((cam_a, cam_b), 0.5)

        # Average harmonic density (from chroma entropy)
        avg_density = (density_a + density_b) / 2.0

        # HNR factor: normalize from typical [0, 20+] dB range to [0, 1]
        avg_hnr = (hnr_a + hnr_b) / 2.0
        hnr_factor = min(max(avg_hnr / 20.0, 0.0), 1.0)

        # Combined: 60% chroma entropy + 40% HNR
        combined = 0.6 * avg_density + 0.4 * hnr_factor

        # Modulation factor: [0.3, 1.0]
        factor = 0.3 + 0.7 * combined

        # Blend: modulated Camelot + fallback for low-density
        return raw_camelot * factor + 0.8 * (1.0 - factor)
```

**Step 4: Update score_transition() to pass HNR**

In `score_transition()`, update the `score_harmonic` call:

```python
        harm_s = self.score_harmonic(
            track_a.key_code,
            track_b.key_code,
            track_a.harmonic_density,
            track_b.harmonic_density,
            track_a.hnr_db,
            track_b.hnr_db,
        )
```

**Step 5: Run tests**

Run: `uv run pytest tests/services/test_transition_scoring.py -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add app/services/transition_scoring.py tests/services/test_transition_scoring.py
git commit -m "feat: enrich score_harmonic with HNR modulation (60% entropy + 40% HNR)"
```

---

### Task 13: Enrich `score_groove()` — add kick prominence

**Files:**
- Modify: `app/services/transition_scoring.py:188-204`
- Test: `tests/services/test_transition_scoring.py`

**Step 1: Write failing tests**

Add to `tests/services/test_transition_scoring.py`:

```python
def test_score_groove_with_kick_prominence():
    """Kick prominence difference should lower groove score."""
    service = TransitionScoringService()

    # Same onset rate but very different kick prominence
    score = service.score_groove(
        onset_a=5.0, onset_b=5.0,
        kick_a=0.9, kick_b=0.1,
    )
    # onset_score=1.0, kick_score=1-0.8=0.2 → 0.7*1.0 + 0.3*0.2 = 0.76
    assert 0.70 < score < 0.82

def test_score_groove_kick_identical():
    """Identical kick prominence should maximize groove score."""
    service = TransitionScoringService()
    score = service.score_groove(onset_a=5.0, onset_b=5.0, kick_a=0.8, kick_b=0.8)
    assert score > 0.95

def test_score_groove_backward_compatible():
    """Without kick kwargs, should use default 0.5 → kick_score=1.0."""
    service = TransitionScoringService()
    score = service.score_groove(onset_a=5.0, onset_b=5.0)
    # kick default 0.5 vs 0.5 → kick_score = 1.0
    # onset_score = 1.0 → total = 0.7*1.0 + 0.3*1.0 = 1.0
    assert score == pytest.approx(1.0)
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/services/test_transition_scoring.py::test_score_groove_with_kick_prominence -v`
Expected: FAIL — `score_groove()` doesn't accept `kick_a`/`kick_b`.

**Step 3: Implement enriched score_groove()**

Replace `score_groove()`:

```python
    def score_groove(
        self,
        onset_a: float,
        onset_b: float,
        kick_a: float = 0.5,
        kick_b: float = 0.5,
    ) -> float:
        """70% onset density + 30% kick prominence similarity.

        Onset density captures rhythmic texture compatibility.
        Kick prominence captures whether both tracks are driven by heavy kicks
        (peak-time) or subtle percussion (minimal).

        Args:
            onset_a: Onset rate (onsets/sec) of track A
            onset_b: Onset rate of track B
            kick_a: Kick prominence of A [0, 1]
            kick_b: Kick prominence of B [0, 1]

        Returns:
            Groove compatibility [0, 1]
        """
        # Onset density component
        if onset_a <= 0 and onset_b <= 0:
            onset_score = 1.0
        else:
            max_onset = max(onset_a, onset_b, 1e-6)
            onset_score = 1.0 - abs(onset_a - onset_b) / max_onset

        # Kick prominence component
        kick_score = 1.0 - abs(kick_a - kick_b)

        return 0.70 * onset_score + 0.30 * kick_score
```

**Step 4: Update score_transition() to pass kick**

In `score_transition()`, update the `score_groove` call:

```python
        groove_s = self.score_groove(
            track_a.onset_rate,
            track_b.onset_rate,
            track_a.kick_prominence,
            track_b.kick_prominence,
        )
```

**Step 5: Run tests**

Run: `uv run pytest tests/services/test_transition_scoring.py -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add app/services/transition_scoring.py tests/services/test_transition_scoring.py
git commit -m "feat: enrich score_groove with kick prominence (70/30 onset+kick)"
```

---

### Task 14: Phase 2B checkpoint — full parity + lint + test

**Step 1: Full parity test**

Run: `uv run pytest tests/test_transition_scoring_parity.py -v`
Expected: All parity tests PASS — GA, API, and MCP paths produce same scores.

**Step 2: Lint**

Run: `make lint`
Expected: Clean.

**Step 3: Full test suite**

Run: `make test-v`
Expected: All tests PASS.

**Step 4: Score range regression**

Verify scores are still well-distributed (not all bunched near 0 or 1):

```bash
uv run python -c "
from app.services.transition_scoring import TransitionScoringService, TrackFeatures
s = TransitionScoringService()
# Test with typical techno values
a = TrackFeatures(bpm=128, energy_lufs=-10, key_code=0, harmonic_density=0.5,
    centroid_hz=2000, band_ratios=[0.4, 0.4, 0.2], onset_rate=5.0,
    mfcc_vector=[1,2,3,4,5,6,7,8,9,10,11,12,13], kick_prominence=0.7, hnr_db=10.0)
b = TrackFeatures(bpm=130, energy_lufs=-11, key_code=2, harmonic_density=0.6,
    centroid_hz=2200, band_ratios=[0.35, 0.45, 0.2], onset_rate=5.5,
    mfcc_vector=[1,2,3,5,5,7,7,8,10,10,11,13,13], kick_prominence=0.6, hnr_db=8.0)
print(f'Score: {s.score_transition(a, b):.3f}')
print(f'Expected: 0.6-0.9 range for similar-ish tracks')
"
```

**Step 5: Commit any fixes**

```bash
git add -u
git commit -m "chore: Phase 2B parity and lint fixes"
```

---

### Task 15: Update docstrings and CLAUDE.md rules

**Files:**
- Modify: `app/services/transition_scoring.py` (module docstring)
- Modify: `.claude/rules/audio.md` (if exists)

**Step 1: Update module docstring**

At top of `app/services/transition_scoring.py`, update docstring to reflect Phase 2:

```python
"""Multi-component transition quality scoring for DJ set generation.

Implements a *filter-then-rank* pipeline:
1. **Hard constraints** — reject transitions that are musically unacceptable
   (BPM diff >10, Camelot distance >=5, energy delta >6 LUFS).
2. **Multi-component scoring** — weighted composite of BPM, harmonic,
   energy, spectral, and groove sub-scores.

Phase 2 enrichments:
- Spectral: MFCC cosine similarity (40%) + centroid (30%) + band balance (30%)
- Harmonic: Camelot modulated by chroma entropy (60%) + HNR (40%)
- Groove: Onset density (70%) + kick prominence (30%)

Pure computation — no DB or ORM dependencies.
"""
```

**Step 2: Commit**

```bash
git add app/services/transition_scoring.py
git commit -m "docs: update transition scoring docstring for Phase 2 enrichment"
```

---

## Summary of commits (expected ~12)

| # | Message | Phase |
|---|---------|-------|
| 1 | `build: add librosa to audio extra deps` | 2A |
| 2 | `feat: add chroma_entropy to KeyResult` | 2A |
| 3 | `feat: add MFCC extraction module` | 2A |
| 4 | `feat: add mfcc field to audio TrackFeatures` | 2A |
| 5 | `feat: add chroma_entropy and mfcc_vector columns` | 2A |
| 6 | `feat: persist chroma_entropy and mfcc_vector` | 2A |
| 7 | `feat: integrate MFCC into analysis pipeline` | 2A |
| 8 | `chore: lint fixes for Phase 2A` | 2A |
| 9 | `feat: add Phase 2 fields to scoring TrackFeatures` | 2B |
| 10 | `feat: map Phase 2 fields in ORM→TrackFeatures` | 2B |
| 11 | `feat: enrich score_spectral with MFCC cosine` | 2B |
| 12 | `feat: enrich score_harmonic with HNR modulation` | 2B |
| 13 | `feat: enrich score_groove with kick prominence` | 2B |
| 14 | `chore: Phase 2B parity and lint fixes` | 2B |
| 15 | `docs: update scoring docstring` | 2B |
