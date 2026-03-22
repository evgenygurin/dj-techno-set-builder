# Audio Analysis Utils Layer — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Создать слой `app/utils/audio/` для интеграции аудио-анализ библиотек (essentia, scipy, soundfile), чтобы сервисы оперировали только репозиториями и утилитами.

**Architecture:** Новый слой `app/utils/audio/` содержит чистые функции без зависимостей от БД/ORM. Каждый модуль отвечает за одну категорию аудио-фичей (BPM, key, loudness, spectral, energy). Результаты — frozen dataclasses. Сервисный слой (`TrackAnalysisService`) использует утилиты для вычисления + репозитории для хранения. Граф: `Router → Service → [Repository + Utils] → [DB + Audio libs]`.

**Tech Stack:** essentia 2.1, scipy, soundfile, numpy, Python 3.12+

---

## Итоговая архитектура слоя utils

```text
app/utils/
├── __init__.py
└── audio/
    ├── __init__.py           # re-export public API
    ├── _types.py             # AudioSignal + result dataclasses
    ├── loader.py             # load_audio(), validate_audio()
    ├── camelot.py            # Camelot wheel: distance, compatibility (pure Python)
    ├── bpm.py                # estimate_bpm() → BpmResult
    ├── key_detect.py         # detect_key() → KeyResult
    ├── loudness.py           # measure_loudness() → LoudnessResult
    ├── energy.py             # compute_band_energies() → BandEnergyResult
    ├── spectral.py           # extract_spectral() → SpectralResult
    └── pipeline.py           # extract_all_features() — orchestrator
```

```text
tests/utils/
├── __init__.py
├── conftest.py              # Аудио-фикстуры (синтетические)
├── test_camelot.py
├── test_loader.py
├── test_bpm.py
├── test_key_detect.py
├── test_loudness.py
├── test_energy.py
├── test_spectral.py
└── test_pipeline.py
```

---

## Task 1: Dependencies + Package Structure + Result Types

**Files:**
- Modify: `pyproject.toml` (добавить optional-dependencies `audio`)
- Create: `app/utils/__init__.py`
- Create: `app/utils/audio/__init__.py`
- Create: `app/utils/audio/_types.py`
- Create: `tests/utils/__init__.py`
- Create: `tests/utils/conftest.py`

### Step 1: Добавить audio зависимости в pyproject.toml

В `pyproject.toml` добавить секцию `[project.optional-dependencies]` и mypy override:

```toml
[project.optional-dependencies]
audio = [
    "essentia>=2.1b6.post1",
    "soundfile>=0.13",
    "scipy>=1.12",
    "numpy>=1.26",
]
```

Также в `[[tool.mypy.overrides]]` добавить новый блок:

```toml
[[tool.mypy.overrides]]
module = ["essentia.*", "soundfile.*"]
ignore_missing_imports = true
```

### Step 2: Установить зависимости

Run: `uv sync --all-extras`
Expected: essentia, soundfile, scipy, numpy установлены без ошибок.

### Step 3: Создать пакет utils и типы

Файл `app/utils/__init__.py`:

```python
```

Файл `app/utils/audio/__init__.py`:

```python
from app.utils.audio._types import (
    AudioSignal,
    BandEnergyResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SpectralResult,
    TrackFeatures,
)

__all__ = [
    "AudioSignal",
    "BandEnergyResult",
    "BpmResult",
    "KeyResult",
    "LoudnessResult",
    "SpectralResult",
    "TrackFeatures",
]
```

Файл `app/utils/audio/_types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

@dataclass(frozen=True, slots=True)
class AudioSignal:
    """Raw audio data with metadata."""

    samples: NDArray[np.float32]
    sample_rate: int
    duration_s: float

@dataclass(frozen=True, slots=True)
class BpmResult:
    bpm: float
    confidence: float  # 0-1
    stability: float  # 0-1
    is_variable: bool

@dataclass(frozen=True, slots=True)
class KeyResult:
    key: str  # e.g. "A"
    scale: str  # "minor" or "major"
    key_code: int  # 0-23 (pitch_class * 2 + mode)
    confidence: float  # 0-1
    is_atonal: bool
    chroma: NDArray[np.float32]  # 12-dim mean HPCP vector

@dataclass(frozen=True, slots=True)
class LoudnessResult:
    lufs_i: float  # Integrated loudness (LUFS)
    lufs_s_mean: float  # Short-term mean (LUFS)
    lufs_m_max: float  # Momentary max (LUFS)
    rms_dbfs: float  # RMS level (dBFS)
    true_peak_db: float  # True peak (dBTP)
    crest_factor_db: float  # true_peak_db - rms_dbfs
    lra_lu: float  # Loudness range (LU)

@dataclass(frozen=True, slots=True)
class BandEnergyResult:
    sub: float  # 20-60 Hz, normalized 0-1
    low: float  # 60-200 Hz
    low_mid: float  # 200-800 Hz
    mid: float  # 800-3000 Hz
    high_mid: float  # 3000-6000 Hz
    high: float  # 6000-12000 Hz
    low_high_ratio: float  # low / high (или 0 если high ≈ 0)
    sub_lowmid_ratio: float  # sub / low_mid (или 0 если low_mid ≈ 0)

@dataclass(frozen=True, slots=True)
class SpectralResult:
    centroid_mean_hz: float
    rolloff_85_hz: float
    rolloff_95_hz: float
    flatness_mean: float  # 0-1
    flux_mean: float
    flux_std: float
    contrast_mean_db: float

@dataclass(frozen=True, slots=True)
class TrackFeatures:
    """Complete feature set for one track."""

    bpm: BpmResult
    key: KeyResult
    loudness: LoudnessResult
    band_energy: BandEnergyResult
    spectral: SpectralResult
```

### Step 4: Создать тестовые фикстуры

Файл `tests/utils/__init__.py`:

```python
```

Файл `tests/utils/conftest.py` — синтетические аудио-сигналы для тестирования без реальных файлов:

```python
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")
soundfile = pytest.importorskip("soundfile")

from app.utils.audio import AudioSignal  # noqa: E402

SR = 44100

def _sine(freq: float, duration: float, sr: int = SR) -> NDArray[np.float32]:
    """Generate a mono sine wave."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (0.8 * np.sin(2 * np.pi * freq * t)).astype(np.float32)

def _click_track(bpm: float, duration: float, sr: int = SR) -> NDArray[np.float32]:
    """Generate a click track at given BPM."""
    samples = int(sr * duration)
    audio = np.zeros(samples, dtype=np.float32)
    interval = int(60.0 / bpm * sr)
    click_len = int(0.005 * sr)  # 5ms click
    for i in range(0, samples, interval):
        end = min(i + click_len, samples)
        audio[i:end] = 0.9
    return audio

@pytest.fixture
def sine_440hz() -> AudioSignal:
    """1-second 440 Hz sine wave (A4)."""
    samples = _sine(440.0, 1.0)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=1.0)

@pytest.fixture
def click_140bpm() -> AudioSignal:
    """10-second click track at 140 BPM."""
    duration = 10.0
    samples = _click_track(140.0, duration)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

@pytest.fixture
def long_sine_440hz() -> AudioSignal:
    """30-second 440 Hz sine wave — for loudness / spectral tests."""
    duration = 30.0
    samples = _sine(440.0, duration)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

@pytest.fixture
def silence() -> AudioSignal:
    """1-second silence."""
    samples = np.zeros(SR, dtype=np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=1.0)

@pytest.fixture
def wav_file_path(long_sine_440hz: AudioSignal) -> Generator[Path, None, None]:
    """Temporary WAV file for loader tests."""
    with NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = Path(f.name)
    soundfile.write(str(path), long_sine_440hz.samples, long_sine_440hz.sample_rate)
    yield path
    path.unlink(missing_ok=True)
```

### Step 5: Проверить что пакет импортируется и линтер доволен

Run: `uv run python -c "from app.utils.audio import AudioSignal, BpmResult; print('OK')"`
Expected: `OK`

Run: `uv run ruff check app/utils/`
Expected: No errors.

Run: `uv run mypy app/utils/`
Expected: Success.

### Step 6: Commit

```bash
git add app/utils/ tests/utils/ pyproject.toml uv.lock
git commit -m "feat(utils): add audio utils package with result types and test fixtures

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Audio Loader

**Files:**
- Create: `app/utils/audio/loader.py`
- Create: `tests/utils/test_loader.py`
- Modify: `app/utils/audio/__init__.py` (добавить экспорт)

### Step 1: Написать failing test

Файл `tests/utils/test_loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")

from app.utils.audio import AudioSignal
from app.utils.audio.loader import load_audio, validate_audio

class TestLoadAudio:
    def test_loads_wav_mono(self, wav_file_path: Path) -> None:
        signal = load_audio(wav_file_path)
        assert isinstance(signal, AudioSignal)
        assert signal.sample_rate == 44100
        assert signal.samples.dtype == np.float32
        assert signal.samples.ndim == 1  # mono

    def test_loads_with_custom_sr(self, wav_file_path: Path) -> None:
        signal = load_audio(wav_file_path, target_sr=22050)
        assert signal.sample_rate == 22050

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_audio(Path("/nonexistent/audio.wav"))

class TestValidateAudio:
    def test_valid_signal_passes(self, long_sine_440hz: AudioSignal) -> None:
        validate_audio(long_sine_440hz)  # should not raise

    def test_rejects_silence(self, silence: AudioSignal) -> None:
        with pytest.raises(ValueError, match="silence"):
            validate_audio(silence)

    def test_rejects_too_short(self) -> None:
        short = AudioSignal(
            samples=np.zeros(100, dtype=np.float32),
            sample_rate=44100,
            duration_s=100 / 44100,
        )
        with pytest.raises(ValueError, match="short"):
            validate_audio(short)
```

### Step 2: Запустить тест — убедиться что падает

Run: `uv run pytest tests/utils/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.audio.loader'`

### Step 3: Реализовать loader

Файл `app/utils/audio/loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from app.utils.audio._types import AudioSignal

_MIN_DURATION_S = 1.0
_SILENCE_THRESHOLD = 1e-6

def load_audio(
    path: str | Path,
    *,
    target_sr: int = 44100,
    mono: bool = True,
) -> AudioSignal:
    """Load an audio file and return an AudioSignal.

    Resamples to *target_sr* if the file's native rate differs.
    Converts to mono (channel averaging) when *mono* is True.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Audio file not found: {path}"
        raise FileNotFoundError(msg)

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)

    # Mono mixdown
    if mono and data.shape[1] > 1:
        data = data.mean(axis=1)
    else:
        data = data[:, 0] if data.ndim == 2 else data

    # Resample if needed (simple linear interpolation — sufficient for analysis)
    if sr != target_sr:
        duration = len(data) / sr
        new_length = int(duration * target_sr)
        indices = np.linspace(0, len(data) - 1, new_length)
        data = np.interp(indices, np.arange(len(data)), data).astype(np.float32)
        sr = target_sr

    duration_s = len(data) / sr
    return AudioSignal(samples=data, sample_rate=sr, duration_s=duration_s)

def validate_audio(signal: AudioSignal) -> None:
    """Raise ValueError if the audio signal is silence or too short."""
    if signal.duration_s < _MIN_DURATION_S:
        msg = f"Audio too short ({signal.duration_s:.2f}s < {_MIN_DURATION_S}s)"
        raise ValueError(msg)

    if np.max(np.abs(signal.samples)) < _SILENCE_THRESHOLD:
        msg = "Audio is silence (max amplitude < threshold)"
        raise ValueError(msg)

    if np.any(np.isnan(signal.samples)) or np.any(np.isinf(signal.samples)):
        msg = "Audio contains NaN or Inf samples"
        raise ValueError(msg)
```

Добавить в `app/utils/audio/__init__.py` экспорт:

```python
from app.utils.audio._types import (
    AudioSignal,
    BandEnergyResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SpectralResult,
    TrackFeatures,
)
from app.utils.audio.loader import load_audio, validate_audio

__all__ = [
    "AudioSignal",
    "BandEnergyResult",
    "BpmResult",
    "KeyResult",
    "LoudnessResult",
    "SpectralResult",
    "TrackFeatures",
    "load_audio",
    "validate_audio",
]
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_loader.py -v`
Expected: All PASS.

Run: `uv run ruff check app/utils/ tests/utils/`
Expected: No errors.

### Step 5: Commit

```bash
git add app/utils/audio/loader.py app/utils/audio/__init__.py tests/utils/test_loader.py
git commit -m "feat(utils): add audio loader with validation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Camelot Wheel Utility

Чистый Python, без аудио-зависимостей. Реплицирует логику PostgreSQL-функции `camelot_distance()` без обращения к БД.

**Files:**
- Create: `app/utils/audio/camelot.py`
- Create: `tests/utils/test_camelot.py`
- Modify: `app/utils/audio/__init__.py` (добавить экспорт)

### Step 1: Написать failing test

Файл `tests/utils/test_camelot.py`:

```python
from __future__ import annotations

import pytest

from app.utils.audio.camelot import (
    camelot_distance,
    is_compatible,
    key_code_to_camelot,
)

class TestKeyCodeToCamelot:
    """Verify mapping matches the DDL seed data."""

    @pytest.mark.parametrize(
        ("key_code", "expected"),
        [
            (0, "5A"),  # Cm
            (1, "8B"),  # C
            (4, "7A"),  # Dm (not 2A!)
            (16, "1A"),  # G#m
            (18, "8A"),  # Am
            (23, "1B"),  # B
        ],
    )
    def test_mapping(self, key_code: int, expected: str) -> None:
        assert key_code_to_camelot(key_code) == expected

    def test_all_24_keys_unique(self) -> None:
        codes = [key_code_to_camelot(i) for i in range(24)]
        assert len(set(codes)) == 24

class TestCamelotDistance:
    def test_same_key_zero(self) -> None:
        assert camelot_distance(0, 0) == 0  # Cm → Cm

    def test_relative_major_minor(self) -> None:
        # Cm (5A) ↔ Eb (5B) — same number, different letter
        assert camelot_distance(0, 7) == 1

    def test_adjacent_same_letter(self) -> None:
        # Cm (5A) ↔ Fm (4A) — adjacent numbers, same letter
        assert camelot_distance(0, 10) == 1

    def test_distant_keys(self) -> None:
        # Cm (5A) ↔ F#m (11A) — 6 steps on the wheel
        assert camelot_distance(0, 12) == 6

    def test_symmetric(self) -> None:
        for a in range(24):
            for b in range(24):
                assert camelot_distance(a, b) == camelot_distance(b, a)

class TestIsCompatible:
    def test_same_key_compatible(self) -> None:
        assert is_compatible(0, 0)

    def test_relative_compatible(self) -> None:
        assert is_compatible(0, 7)  # 5A ↔ 5B

    def test_distant_not_compatible(self) -> None:
        assert not is_compatible(0, 12)  # 5A ↔ 11A
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_camelot.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать Camelot

Файл `app/utils/audio/camelot.py`:

```python
"""Camelot Wheel utility — pure Python, no DB access.

Key encoding: key_code = pitch_class * 2 + mode
  pitch_class: 0=C, 1=C#, 2=D, ... 11=B
  mode: 0=minor (A), 1=major (B)

Camelot notation: number (1-12) + letter (A=minor, B=major).
Mapping matches the seed data in data/schema_v6.sql.
"""

from __future__ import annotations

# key_code → (camelot_number, camelot_letter)
# Derived from DDL seed: INSERT INTO keys ... VALUES ...
_KEY_CODE_TO_CAMELOT: dict[int, tuple[int, str]] = {
    0: (5, "A"),  # Cm
    1: (8, "B"),  # C
    2: (12, "A"),  # C#m
    3: (3, "B"),  # Db
    4: (7, "A"),  # Dm
    5: (10, "B"),  # D
    6: (2, "A"),  # Ebm
    7: (5, "B"),  # Eb
    8: (9, "A"),  # Em
    9: (12, "B"),  # E
    10: (4, "A"),  # Fm
    11: (7, "B"),  # F
    12: (11, "A"),  # F#m
    13: (2, "B"),  # F#
    14: (6, "A"),  # Gm
    15: (9, "B"),  # G
    16: (1, "A"),  # G#m
    17: (4, "B"),  # Ab
    18: (8, "A"),  # Am
    19: (11, "B"),  # A
    20: (3, "A"),  # Bbm
    21: (6, "B"),  # Bb
    22: (10, "A"),  # Bm
    23: (1, "B"),  # B
}

def key_code_to_camelot(key_code: int) -> str:
    """Convert key_code (0-23) to Camelot notation (e.g. '5A')."""
    num, letter = _KEY_CODE_TO_CAMELOT[key_code]
    return f"{num}{letter}"

def camelot_distance(a_key_code: int, b_key_code: int) -> int:
    """Compute Camelot distance between two key_codes.

    Returns 0 for same key, 1 for compatible keys (adjacent on wheel
    or relative major/minor), up to 6 for maximally distant keys.
    """
    if a_key_code == b_key_code:
        return 0

    a_num, a_letter = _KEY_CODE_TO_CAMELOT[a_key_code]
    b_num, b_letter = _KEY_CODE_TO_CAMELOT[b_key_code]

    # Circular distance on the 1-12 wheel
    raw = abs(a_num - b_num)
    num_dist = min(raw, 12 - raw)

    if a_letter == b_letter:
        return num_dist

    # Different letter: relative major/minor at same number costs 1
    if num_dist == 0:
        return 1
    return num_dist + 1

def is_compatible(a_key_code: int, b_key_code: int, *, max_distance: int = 1) -> bool:
    """Check if two keys are harmonically compatible (Camelot distance ≤ max_distance)."""
    return camelot_distance(a_key_code, b_key_code) <= max_distance
```

Добавить экспорт в `app/utils/audio/__init__.py`:

```python
from app.utils.audio.camelot import camelot_distance, is_compatible, key_code_to_camelot
```

И в `__all__`:

```python
    "camelot_distance",
    "is_compatible",
    "key_code_to_camelot",
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_camelot.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add app/utils/audio/camelot.py tests/utils/test_camelot.py app/utils/audio/__init__.py
git commit -m "feat(utils): add Camelot wheel distance utility

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: BPM Estimation

Используем essentia `RhythmExtractor2013` с `method="multifeature"` — лучший вариант для EDM.

**Files:**
- Create: `app/utils/audio/bpm.py`
- Create: `tests/utils/test_bpm.py`

### Step 1: Написать failing test

Файл `tests/utils/test_bpm.py`:

```python
from __future__ import annotations

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, BpmResult
from app.utils.audio.bpm import estimate_bpm

class TestEstimateBpm:
    def test_returns_bpm_result(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        assert isinstance(result, BpmResult)

    def test_detects_140bpm(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        # Allow ±5 BPM tolerance for synthetic click track
        assert 135.0 <= result.bpm <= 145.0

    def test_confidence_range(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        assert 0.0 <= result.confidence <= 1.0
        assert 0.0 <= result.stability <= 1.0

    def test_stable_tempo_not_variable(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        assert not result.is_variable

    def test_clamps_to_range(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm, min_bpm=120, max_bpm=160)
        assert 120.0 <= result.bpm <= 160.0
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_bpm.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать

Файл `app/utils/audio/bpm.py`:

```python
from __future__ import annotations

import numpy as np

from app.utils.audio._types import AudioSignal, BpmResult

_DEFAULT_MIN_BPM = 80.0
_DEFAULT_MAX_BPM = 200.0
_VARIABLE_TEMPO_THRESHOLD = 5.0  # BPM std dev

def estimate_bpm(
    signal: AudioSignal,
    *,
    min_bpm: float = _DEFAULT_MIN_BPM,
    max_bpm: float = _DEFAULT_MAX_BPM,
) -> BpmResult:
    """Estimate BPM using essentia RhythmExtractor2013 (multifeature method)."""
    import essentia.standard as es

    extractor = es.RhythmExtractor2013(
        method="multifeature",
        minTempo=min_bpm,
        maxTempo=max_bpm,
    )
    bpm, beats, beats_confidence, _, beats_intervals = extractor(signal.samples)

    # Confidence: mean of per-beat confidence values
    confidence = float(np.mean(beats_confidence)) if len(beats_confidence) > 0 else 0.0
    confidence = float(np.clip(confidence, 0.0, 1.0))

    # Stability: inverse of tempo variation across beat intervals
    if len(beats_intervals) > 1:
        interval_bpms = 60.0 / beats_intervals
        bpm_std = float(np.std(interval_bpms))
        stability = float(np.clip(1.0 - bpm_std / max_bpm, 0.0, 1.0))
        is_variable = bpm_std > _VARIABLE_TEMPO_THRESHOLD
    else:
        stability = 0.0
        is_variable = False

    return BpmResult(
        bpm=float(np.clip(bpm, min_bpm, max_bpm)),
        confidence=confidence,
        stability=stability,
        is_variable=is_variable,
    )
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_bpm.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add app/utils/audio/bpm.py tests/utils/test_bpm.py
git commit -m "feat(utils): add BPM estimation via essentia RhythmExtractor2013

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Key Detection

Essentia `KeyExtractor` с EDM-профилями (`bgate` по умолчанию). Маппинг результата на key_code (0-23), совместимый с моделью `Key` и таблицей `keys`.

**Files:**
- Create: `app/utils/audio/key_detect.py`
- Create: `tests/utils/test_key_detect.py`

### Step 1: Написать failing test

Файл `tests/utils/test_key_detect.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, KeyResult
from app.utils.audio.key_detect import detect_key

SR = 44100

@pytest.fixture
def a_major_chord() -> AudioSignal:
    """3-second A major chord (A4 + C#5 + E5) — should detect A major."""
    duration = 3.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (
        0.4 * np.sin(2 * np.pi * 440.0 * t)  # A4
        + 0.3 * np.sin(2 * np.pi * 554.37 * t)  # C#5
        + 0.3 * np.sin(2 * np.pi * 659.25 * t)  # E5
    ).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

class TestDetectKey:
    def test_returns_key_result(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert isinstance(result, KeyResult)

    def test_key_code_range(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert 0 <= result.key_code <= 23

    def test_confidence_range(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert 0.0 <= result.confidence <= 1.0

    def test_chroma_shape(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert result.chroma.shape == (12,)

    def test_scale_is_valid(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert result.scale in ("minor", "major")

    def test_a_major_detection(self, a_major_chord: AudioSignal) -> None:
        result = detect_key(a_major_chord)
        # A major → key = "A", scale = "major", key_code = 19
        assert result.key == "A"
        assert result.scale == "major"
        assert result.key_code == 19
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_key_detect.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать

Файл `app/utils/audio/key_detect.py`:

```python
from __future__ import annotations

import math

import numpy as np

from app.utils.audio._types import AudioSignal, KeyResult

# Essentia key names → pitch_class mapping
_PITCH_CLASS: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

_MODE_MAP: dict[str, int] = {"minor": 0, "major": 1}

# Atonal detection: if chroma entropy is close to max (uniform), the track is atonal
_MAX_CHROMA_ENTROPY = math.log2(12)  # ≈ 3.585
_ATONAL_ENTROPY_THRESHOLD = 0.95  # fraction of max entropy

def _key_to_key_code(key: str, scale: str) -> int:
    """Convert essentia key name + scale to key_code (0-23)."""
    pitch = _PITCH_CLASS[key]
    mode = _MODE_MAP[scale]
    return pitch * 2 + mode

def _chroma_entropy(chroma: np.ndarray) -> float:
    """Compute Shannon entropy of a chroma vector (normalized)."""
    chroma = chroma / (chroma.sum() + 1e-10)
    chroma = chroma[chroma > 0]
    return float(-np.sum(chroma * np.log2(chroma)))

def detect_key(
    signal: AudioSignal,
    *,
    profile: str = "bgate",
) -> KeyResult:
    """Detect musical key using essentia KeyExtractor with EDM-specific profiles.

    Profiles: 'bgate' (default, Beatport-derived), 'edmm' (manual EDM),
    'edma' (auto EDM), 'braw' (raw Beatport medians).
    """
    import essentia.standard as es

    key_extractor = es.KeyExtractor(
        profileType=profile,
        sampleRate=signal.sample_rate,
    )
    key, scale, strength = key_extractor(signal.samples)

    # Compute mean chroma (HPCP) for the chroma vector field
    hpcp = es.HPCP(
        size=12,
        referenceFrequency=440.0,
        sampleRate=signal.sample_rate,
    )
    w = es.Windowing(type="blackmanharris62")
    spectrum = es.Spectrum()
    spectral_peaks = es.SpectralPeaks(
        sampleRate=signal.sample_rate,
        maxFrequency=3500.0,
    )

    chroma_frames = []
    for frame in es.FrameGenerator(signal.samples, frameSize=4096, hopSize=2048):
        windowed = w(frame)
        spec = spectrum(windowed)
        freqs, mags = spectral_peaks(spec)
        chroma_frame = hpcp(freqs, mags)
        chroma_frames.append(chroma_frame)

    if chroma_frames:
        mean_chroma = np.mean(chroma_frames, axis=0).astype(np.float32)
    else:
        mean_chroma = np.zeros(12, dtype=np.float32)

    # Atonal detection
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
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_key_detect.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add app/utils/audio/key_detect.py tests/utils/test_key_detect.py
git commit -m "feat(utils): add key detection via essentia KeyExtractor (EDM profiles)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Loudness Measurement

Essentia `LoudnessEBUR128` — единственная Python-библиотека с поддержкой всех 5 метрик (LUFS-I, LUFS-S, LUFS-M, True Peak, LRA).

**Files:**
- Create: `app/utils/audio/loudness.py`
- Create: `tests/utils/test_loudness.py`

### Step 1: Написать failing test

Файл `tests/utils/test_loudness.py`:

```python
from __future__ import annotations

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, LoudnessResult
from app.utils.audio.loudness import measure_loudness

class TestMeasureLoudness:
    def test_returns_loudness_result(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert isinstance(result, LoudnessResult)

    def test_lufs_i_is_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        # A sine wave at 0.8 amplitude should have negative LUFS
        assert result.lufs_i < 0

    def test_rms_is_negative_dbfs(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert result.rms_dbfs < 0

    def test_crest_factor_non_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert result.crest_factor_db >= 0

    def test_lra_non_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert result.lra_lu >= 0
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_loudness.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать

Файл `app/utils/audio/loudness.py`:

```python
from __future__ import annotations

import numpy as np

from app.utils.audio._types import AudioSignal, LoudnessResult

def measure_loudness(signal: AudioSignal) -> LoudnessResult:
    """Measure loudness using essentia LoudnessEBUR128 (all 5 EBU R128 metrics)."""
    import essentia.standard as es

    loudness = es.LoudnessEBUR128(sampleRate=signal.sample_rate)
    momentary, short_term, integrated, loudness_range = loudness(signal.samples)

    # Short-term mean and momentary max
    lufs_s_mean = float(np.mean(short_term)) if len(short_term) > 0 else integrated
    lufs_m_max = float(np.max(momentary)) if len(momentary) > 0 else integrated

    # RMS in dBFS
    rms_linear = float(np.sqrt(np.mean(signal.samples**2)))
    rms_dbfs = 20.0 * np.log10(rms_linear + 1e-10)

    # True peak (oversampled)
    true_peak_linear = es.TruePeak(sampleRate=signal.sample_rate)(signal.samples)
    true_peak_db = 20.0 * np.log10(float(true_peak_linear) + 1e-10)

    crest_factor_db = max(0.0, true_peak_db - rms_dbfs)

    return LoudnessResult(
        lufs_i=float(integrated),
        lufs_s_mean=lufs_s_mean,
        lufs_m_max=lufs_m_max,
        rms_dbfs=float(rms_dbfs),
        true_peak_db=float(true_peak_db),
        crest_factor_db=crest_factor_db,
        lra_lu=float(max(0.0, loudness_range)),
    )
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_loudness.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add app/utils/audio/loudness.py tests/utils/test_loudness.py
git commit -m "feat(utils): add loudness measurement via essentia LoudnessEBUR128

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Band Energies

scipy.signal Butterworth bandpass фильтры — 6 полос, нормализация 0-1.

**Files:**
- Create: `app/utils/audio/energy.py`
- Create: `tests/utils/test_energy.py`

### Step 1: Написать failing test

Файл `tests/utils/test_energy.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

scipy = pytest.importorskip("scipy")

from app.utils.audio import AudioSignal, BandEnergyResult
from app.utils.audio.energy import compute_band_energies

SR = 44100

@pytest.fixture
def low_freq_signal() -> AudioSignal:
    """5-second 100 Hz sine — energy should concentrate in 'low' band (60-200 Hz)."""
    duration = 5.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (0.8 * np.sin(2 * np.pi * 100.0 * t)).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

@pytest.fixture
def high_freq_signal() -> AudioSignal:
    """5-second 8000 Hz sine — energy should concentrate in 'high' band (6000-12000 Hz)."""
    duration = 5.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (0.8 * np.sin(2 * np.pi * 8000.0 * t)).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

class TestComputeBandEnergies:
    def test_returns_band_energy_result(self, long_sine_440hz: AudioSignal) -> None:
        result = compute_band_energies(long_sine_440hz)
        assert isinstance(result, BandEnergyResult)

    def test_values_between_0_and_1(self, long_sine_440hz: AudioSignal) -> None:
        result = compute_band_energies(long_sine_440hz)
        for field in ("sub", "low", "low_mid", "mid", "high_mid", "high"):
            val = getattr(result, field)
            assert 0.0 <= val <= 1.0, f"{field}={val} out of range"

    def test_low_freq_concentrated_in_low_band(
        self, low_freq_signal: AudioSignal
    ) -> None:
        result = compute_band_energies(low_freq_signal)
        assert result.low > result.high
        assert result.low > result.mid

    def test_high_freq_concentrated_in_high_band(
        self, high_freq_signal: AudioSignal
    ) -> None:
        result = compute_band_energies(high_freq_signal)
        assert result.high > result.low
        assert result.high > result.sub
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_energy.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать

Файл `app/utils/audio/energy.py`:

```python
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from app.utils.audio._types import AudioSignal, BandEnergyResult

# Frequency bands (Hz)
_BANDS: list[tuple[str, float, float]] = [
    ("sub", 20.0, 60.0),
    ("low", 60.0, 200.0),
    ("low_mid", 200.0, 800.0),
    ("mid", 800.0, 3000.0),
    ("high_mid", 3000.0, 6000.0),
    ("high", 6000.0, 12000.0),
]

_FILTER_ORDER = 4

def _bandpass_energy(
    samples: np.ndarray, sr: int, low_hz: float, high_hz: float
) -> float:
    """Compute RMS energy in a frequency band using Butterworth bandpass."""
    nyquist = sr / 2.0
    low = max(low_hz / nyquist, 0.001)
    high = min(high_hz / nyquist, 0.999)
    if low >= high:
        return 0.0
    sos = butter(_FILTER_ORDER, [low, high], btype="bandpass", output="sos")
    filtered = sosfiltfilt(sos, samples)
    return float(np.sqrt(np.mean(filtered**2)))

def compute_band_energies(signal: AudioSignal) -> BandEnergyResult:
    """Compute energy in 6 frequency bands, normalized to 0-1."""
    raw: dict[str, float] = {}
    for name, low_hz, high_hz in _BANDS:
        raw[name] = _bandpass_energy(signal.samples, signal.sample_rate, low_hz, high_hz)

    # Normalize: divide by max band energy (or 1.0 if all zero)
    max_energy = max(raw.values()) or 1.0
    normed = {k: v / max_energy for k, v in raw.items()}

    low_val = normed["low"]
    high_val = normed["high"]
    sub_val = normed["sub"]
    lowmid_val = normed["low_mid"]

    return BandEnergyResult(
        sub=normed["sub"],
        low=normed["low"],
        low_mid=normed["low_mid"],
        mid=normed["mid"],
        high_mid=normed["high_mid"],
        high=normed["high"],
        low_high_ratio=low_val / high_val if high_val > 1e-10 else 0.0,
        sub_lowmid_ratio=sub_val / lowmid_val if lowmid_val > 1e-10 else 0.0,
    )
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_energy.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add app/utils/audio/energy.py tests/utils/test_energy.py
git commit -m "feat(utils): add band energy computation via scipy Butterworth filters

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Spectral Features

Essentia frame-by-frame спектральный анализ: centroid, rolloff, flatness, flux, contrast.

**Files:**
- Create: `app/utils/audio/spectral.py`
- Create: `tests/utils/test_spectral.py`

### Step 1: Написать failing test

Файл `tests/utils/test_spectral.py`:

```python
from __future__ import annotations

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, SpectralResult
from app.utils.audio.spectral import extract_spectral_features

class TestExtractSpectralFeatures:
    def test_returns_spectral_result(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert isinstance(result, SpectralResult)

    def test_centroid_positive(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert result.centroid_mean_hz > 0

    def test_sine_centroid_near_440(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        # Centroid of a pure sine ≈ its frequency
        assert 400.0 <= result.centroid_mean_hz <= 500.0

    def test_rolloff_above_centroid(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert result.rolloff_85_hz >= result.centroid_mean_hz

    def test_flatness_range(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert 0.0 <= result.flatness_mean <= 1.0

    def test_flux_non_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert result.flux_mean >= 0
        assert result.flux_std >= 0
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_spectral.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать

Файл `app/utils/audio/spectral.py`:

```python
from __future__ import annotations

import numpy as np

from app.utils.audio._types import AudioSignal, SpectralResult

_FRAME_SIZE = 2048
_HOP_SIZE = 512

def extract_spectral_features(
    signal: AudioSignal,
    *,
    frame_size: int = _FRAME_SIZE,
    hop_size: int = _HOP_SIZE,
) -> SpectralResult:
    """Extract spectral descriptors using essentia frame-by-frame analysis."""
    import essentia.standard as es

    sr = signal.sample_rate
    half_sr = sr / 2.0

    w = es.Windowing(type="hann")
    spectrum = es.Spectrum(size=frame_size)
    centroid = es.Centroid(range=half_sr)
    rolloff85 = es.RollOff(cutoff=0.85, sampleRate=sr)
    rolloff95 = es.RollOff(cutoff=0.95, sampleRate=sr)
    flatness = es.Flatness()
    flux = es.Flux()
    contrast = es.SpectralContrast(
        sampleRate=sr,
        frameSize=frame_size,
    )

    centroids: list[float] = []
    rolloffs85: list[float] = []
    rolloffs95: list[float] = []
    flatnesses: list[float] = []
    fluxes: list[float] = []
    contrasts: list[float] = []

    for frame in es.FrameGenerator(signal.samples, frameSize=frame_size, hopSize=hop_size):
        windowed = w(frame)
        spec = spectrum(windowed)

        centroids.append(float(centroid(spec)))
        rolloffs85.append(float(rolloff85(spec)))
        rolloffs95.append(float(rolloff95(spec)))
        flatnesses.append(float(flatness(spec)))
        fluxes.append(float(flux(spec)))

        sc, sv = contrast(spec)
        contrasts.append(float(np.mean(sc)))

    return SpectralResult(
        centroid_mean_hz=float(np.mean(centroids)) if centroids else 0.0,
        rolloff_85_hz=float(np.mean(rolloffs85)) if rolloffs85 else 0.0,
        rolloff_95_hz=float(np.mean(rolloffs95)) if rolloffs95 else 0.0,
        flatness_mean=float(np.clip(np.mean(flatnesses), 0.0, 1.0)) if flatnesses else 0.0,
        flux_mean=float(np.mean(fluxes)) if fluxes else 0.0,
        flux_std=float(np.std(fluxes)) if fluxes else 0.0,
        contrast_mean_db=float(np.mean(contrasts)) if contrasts else 0.0,
    )
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_spectral.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add app/utils/audio/spectral.py tests/utils/test_spectral.py
git commit -m "feat(utils): add spectral feature extraction via essentia

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Feature Extraction Pipeline (Orchestrator)

Объединяет все утилиты в единый вызов `extract_all_features(path) → TrackFeatures`.

**Files:**
- Create: `app/utils/audio/pipeline.py`
- Create: `tests/utils/test_pipeline.py`
- Modify: `app/utils/audio/__init__.py` (финальный экспорт)

### Step 1: Написать failing test

Файл `tests/utils/test_pipeline.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import TrackFeatures
from app.utils.audio.pipeline import extract_all_features

class TestExtractAllFeatures:
    def test_returns_track_features(self, wav_file_path: Path) -> None:
        result = extract_all_features(wav_file_path)
        assert isinstance(result, TrackFeatures)

    def test_all_sub_results_present(self, wav_file_path: Path) -> None:
        result = extract_all_features(wav_file_path)
        assert result.bpm is not None
        assert result.key is not None
        assert result.loudness is not None
        assert result.band_energy is not None
        assert result.spectral is not None

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            extract_all_features(Path("/nonexistent/audio.wav"))

    def test_raises_on_silence(self, tmp_path: Path) -> None:
        import numpy as np
        import soundfile as sf

        silence_path = tmp_path / "silence.wav"
        sf.write(str(silence_path), np.zeros(44100, dtype="float32"), 44100)
        with pytest.raises(ValueError, match="silence"):
            extract_all_features(silence_path)
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать

Файл `app/utils/audio/pipeline.py`:

```python
from __future__ import annotations

import logging
from pathlib import Path

from app.utils.audio._types import TrackFeatures
from app.utils.audio.bpm import estimate_bpm
from app.utils.audio.energy import compute_band_energies
from app.utils.audio.key_detect import detect_key
from app.utils.audio.loader import load_audio, validate_audio
from app.utils.audio.loudness import measure_loudness
from app.utils.audio.spectral import extract_spectral_features

logger = logging.getLogger(__name__)

def extract_all_features(
    path: str | Path,
    *,
    target_sr: int = 44100,
) -> TrackFeatures:
    """Load audio file and extract all analysis features.

    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if the audio is silence or too short.
    """
    signal = load_audio(path, target_sr=target_sr)
    validate_audio(signal)

    logger.info("Extracting features from %s (%.1fs)", path, signal.duration_s)

    bpm_result = estimate_bpm(signal)
    key_result = detect_key(signal)
    loudness_result = measure_loudness(signal)
    band_energy_result = compute_band_energies(signal)
    spectral_result = extract_spectral_features(signal)

    logger.info(
        "Extraction complete: BPM=%.1f key=%s%s loudness=%.1f LUFS",
        bpm_result.bpm,
        key_result.key,
        key_result.scale[0],
        loudness_result.lufs_i,
    )

    return TrackFeatures(
        bpm=bpm_result,
        key=key_result,
        loudness=loudness_result,
        band_energy=band_energy_result,
        spectral=spectral_result,
    )
```

### Step 4: Финализировать `__init__.py`

Файл `app/utils/audio/__init__.py` — итоговая версия:

```python
from app.utils.audio._types import (
    AudioSignal,
    BandEnergyResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SpectralResult,
    TrackFeatures,
)
from app.utils.audio.camelot import camelot_distance, is_compatible, key_code_to_camelot
from app.utils.audio.loader import load_audio, validate_audio
from app.utils.audio.pipeline import extract_all_features

__all__ = [
    "AudioSignal",
    "BandEnergyResult",
    "BpmResult",
    "KeyResult",
    "LoudnessResult",
    "SpectralResult",
    "TrackFeatures",
    "camelot_distance",
    "extract_all_features",
    "is_compatible",
    "key_code_to_camelot",
    "load_audio",
    "validate_audio",
]
```

### Step 5: Запустить все тесты

Run: `uv run pytest tests/utils/ -v`
Expected: All PASS.

Run: `uv run ruff check app/utils/ tests/utils/`
Expected: No errors.

### Step 6: Commit

```bash
git add app/utils/audio/pipeline.py app/utils/audio/__init__.py tests/utils/test_pipeline.py
git commit -m "feat(utils): add feature extraction pipeline orchestrator

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Wire Into Service Layer — TrackAnalysisService

Сервис, который использует `extract_all_features()` (utils) + `TrackRepository` / `TrackAudioFeaturesRepository` (repos) для вычисления и сохранения фичей.

> **NOTE:** Этот таск зависит от наличия `TrackAudioFeaturesRepository` и `FeatureExtractionRunRepository`. Если их ещё нет — нужно создать по паттерну `BaseRepository`.

**Files:**
- Create: `app/repositories/audio_features.py`
- Create: `app/services/track_analysis.py`
- Create: `tests/test_track_analysis.py`

### Step 1: Создать репозиторий для audio features

Файл `app/repositories/audio_features.py`:

```python
from app.models.features import TrackAudioFeaturesComputed
from app.repositories.base import BaseRepository

class AudioFeaturesRepository(BaseRepository[TrackAudioFeaturesComputed]):
    model = TrackAudioFeaturesComputed
```

### Step 2: Создать TrackAnalysisService

Файл `app/services/track_analysis.py`:

```python
from __future__ import annotations

from pathlib import Path

from app.errors import NotFoundError
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.services.base import BaseService
from app.utils.audio import TrackFeatures
from app.utils.audio.pipeline import extract_all_features

class TrackAnalysisService(BaseService):
    """Orchestrates audio analysis: extract features via utils, persist via repos."""

    def __init__(
        self,
        track_repo: TrackRepository,
        features_repo: AudioFeaturesRepository,
    ) -> None:
        super().__init__()
        self.track_repo = track_repo
        self.features_repo = features_repo

    async def analyze_track(
        self,
        track_id: int,
        audio_path: str | Path,
        run_id: int,
    ) -> TrackFeatures:
        """Extract all audio features and persist to DB.

        Returns the extracted TrackFeatures for immediate use.
        """
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)

        self.logger.info("Analyzing track %d from %s", track_id, audio_path)

        # Utils layer — pure computation, no DB
        features = extract_all_features(audio_path)

        # Persist via repository
        await self.features_repo.create(
            track_id=track_id,
            run_id=run_id,
            # Tempo
            bpm=features.bpm.bpm,
            tempo_confidence=features.bpm.confidence,
            bpm_stability=features.bpm.stability,
            is_variable_tempo=features.bpm.is_variable,
            # Loudness
            lufs_i=features.loudness.lufs_i,
            lufs_s_mean=features.loudness.lufs_s_mean,
            lufs_m_max=features.loudness.lufs_m_max,
            rms_dbfs=features.loudness.rms_dbfs,
            true_peak_db=features.loudness.true_peak_db,
            crest_factor_db=features.loudness.crest_factor_db,
            lra_lu=features.loudness.lra_lu,
            # Energy (global: use band_energy as proxy)
            energy_mean=features.band_energy.mid,
            energy_max=max(
                features.band_energy.sub,
                features.band_energy.low,
                features.band_energy.low_mid,
                features.band_energy.mid,
                features.band_energy.high_mid,
                features.band_energy.high,
            ),
            energy_std=0.0,  # TODO: compute from frame-level data
            # Band energies
            sub_energy=features.band_energy.sub,
            low_energy=features.band_energy.low,
            lowmid_energy=features.band_energy.low_mid,
            mid_energy=features.band_energy.mid,
            highmid_energy=features.band_energy.high_mid,
            high_energy=features.band_energy.high,
            low_high_ratio=features.band_energy.low_high_ratio,
            sub_lowmid_ratio=features.band_energy.sub_lowmid_ratio,
            # Spectral
            centroid_mean_hz=features.spectral.centroid_mean_hz,
            rolloff_85_hz=features.spectral.rolloff_85_hz,
            rolloff_95_hz=features.spectral.rolloff_95_hz,
            flatness_mean=features.spectral.flatness_mean,
            flux_mean=features.spectral.flux_mean,
            flux_std=features.spectral.flux_std,
            contrast_mean_db=features.spectral.contrast_mean_db,
            # Key
            key_code=features.key.key_code,
            key_confidence=features.key.confidence,
            is_atonal=features.key.is_atonal,
            chroma=",".join(f"{v:.6f}" for v in features.key.chroma),
        )

        self.logger.info("Features persisted for track %d, run %d", track_id, run_id)
        return features
```

### Step 3: Написать тест

Файл `tests/test_track_analysis.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.services.track_analysis import TrackAnalysisService
from app.utils.audio import (
    BandEnergyResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SpectralResult,
    TrackFeatures,
)

def _fake_features() -> TrackFeatures:
    return TrackFeatures(
        bpm=BpmResult(bpm=140.0, confidence=0.9, stability=0.95, is_variable=False),
        key=KeyResult(
            key="A", scale="minor", key_code=18, confidence=0.85,
            is_atonal=False, chroma=np.zeros(12, dtype=np.float32),
        ),
        loudness=LoudnessResult(
            lufs_i=-8.0, lufs_s_mean=-7.5, lufs_m_max=-5.0,
            rms_dbfs=-10.0, true_peak_db=-1.0, crest_factor_db=9.0, lra_lu=6.0,
        ),
        band_energy=BandEnergyResult(
            sub=0.3, low=0.7, low_mid=0.5, mid=0.4, high_mid=0.2, high=0.1,
            low_high_ratio=7.0, sub_lowmid_ratio=0.6,
        ),
        spectral=SpectralResult(
            centroid_mean_hz=1500.0, rolloff_85_hz=5000.0, rolloff_95_hz=8000.0,
            flatness_mean=0.3, flux_mean=0.5, flux_std=0.1, contrast_mean_db=20.0,
        ),
    )

class TestTrackAnalysisService:
    @pytest.fixture
    def service(self) -> TrackAnalysisService:
        track_repo = MagicMock()
        track_repo.get_by_id = AsyncMock(return_value=MagicMock(track_id=1))
        features_repo = MagicMock()
        features_repo.create = AsyncMock()
        return TrackAnalysisService(track_repo, features_repo)

    @patch("app.services.track_analysis.extract_all_features")
    async def test_analyze_track_returns_features(
        self, mock_extract: MagicMock, service: TrackAnalysisService
    ) -> None:
        mock_extract.return_value = _fake_features()
        result = await service.analyze_track(1, "/fake/path.wav", run_id=1)
        assert isinstance(result, TrackFeatures)
        assert result.bpm.bpm == 140.0

    @patch("app.services.track_analysis.extract_all_features")
    async def test_persists_to_repo(
        self, mock_extract: MagicMock, service: TrackAnalysisService
    ) -> None:
        mock_extract.return_value = _fake_features()
        await service.analyze_track(1, "/fake/path.wav", run_id=1)
        service.features_repo.create.assert_awaited_once()

    async def test_raises_not_found(self) -> None:
        track_repo = MagicMock()
        track_repo.get_by_id = AsyncMock(return_value=None)
        features_repo = MagicMock()
        svc = TrackAnalysisService(track_repo, features_repo)
        with pytest.raises(Exception, match="Track"):
            await svc.analyze_track(999, "/fake.wav", run_id=1)
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/test_track_analysis.py -v`
Expected: All PASS.

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

### Step 5: Commit

```bash
git add app/repositories/audio_features.py app/services/track_analysis.py tests/test_track_analysis.py
git commit -m "feat(services): add TrackAnalysisService wiring utils + repos

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 2: Beat & Rhythm Analysis, Source Separation, Structure

**Предусловие:** Phase 1 (Tasks 1-10) завершена, все тесты проходят.

**Новые зависимости Phase 2:**

```toml
# Добавить в pyproject.toml [project.optional-dependencies]
ml = [
    "demucs>=4.0",
    "torch>=2.0",
]
```

> **Ключевое решение по Python 3.12:** BeatNet и allin1 зависят от madmom (Python <3.10). Вместо них используем essentia (уже установлена) для битов/онсетов и собственную DSP-реализацию для сегментации. Demucs v4 работает на Python 3.12 без проблем.

---

## Task 11: Beat & Onset Features

Вычисляет ритмические фичи, которые маппятся на поля `TrackAudioFeaturesComputed`: `onset_rate_mean`, `onset_rate_max`, `pulse_clarity`, `kick_prominence`, `hp_ratio`.

**Files:**
- Modify: `app/utils/audio/_types.py` (добавить `BeatsResult`)
- Create: `app/utils/audio/beats.py`
- Create: `tests/utils/test_beats.py`
- Modify: `app/utils/audio/__init__.py` (добавить экспорт)

### Step 1: Добавить BeatsResult в _types.py

В `app/utils/audio/_types.py` добавить после `SpectralResult`:

```python
@dataclass(frozen=True, slots=True)
class BeatsResult:
    beat_times: NDArray[np.float32]  # seconds, sorted
    downbeat_times: NDArray[np.float32]  # every 4th beat (4/4 assumption)
    onset_rate_mean: float  # onsets per second, mean
    onset_rate_max: float  # onsets per second, max (windowed)
    pulse_clarity: float  # 0-1, how clear the pulse is
    kick_prominence: float  # 0-1, how prominent kick is at beat positions
    hp_ratio: float  # harmonic / percussive energy ratio
    onset_envelope: NDArray[np.float32]  # frame-level onset strength
```

Обновить `TrackFeatures`:

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
```

### Step 2: Написать failing test

Файл `tests/utils/test_beats.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, BeatsResult
from app.utils.audio.beats import detect_beats

SR = 44100

@pytest.fixture
def kick_pattern() -> AudioSignal:
    """10-second 4/4 kick pattern at 140 BPM with sub-bass energy.

    Simulates a techno kick: short burst at 50 Hz every beat.
    """
    duration = 10.0
    bpm = 140.0
    samples = np.zeros(int(SR * duration), dtype=np.float32)
    interval = int(60.0 / bpm * SR)
    kick_len = int(0.03 * SR)  # 30ms kick

    for i in range(0, len(samples), interval):
        end = min(i + kick_len, len(samples))
        t = np.arange(end - i) / SR
        # Sub-bass sine burst with fast decay
        kick = 0.9 * np.sin(2 * np.pi * 50.0 * t) * np.exp(-t * 40)
        samples[i:end] += kick.astype(np.float32)

    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

class TestDetectBeats:
    def test_returns_beats_result(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert isinstance(result, BeatsResult)

    def test_beat_count_reasonable(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        # 10s at 140 BPM ≈ 23 beats
        assert 15 <= len(result.beat_times) <= 30

    def test_beats_sorted(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert np.all(np.diff(result.beat_times) > 0)

    def test_downbeats_subset_of_beats(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        # Every downbeat should be close to some beat
        for db in result.downbeat_times:
            dists = np.abs(result.beat_times - db)
            assert np.min(dists) < 0.05  # within 50ms

    def test_onset_rate_range(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert result.onset_rate_mean > 0
        assert result.onset_rate_max >= result.onset_rate_mean

    def test_pulse_clarity_range(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert 0.0 <= result.pulse_clarity <= 1.0

    def test_kick_prominence_range(self, kick_pattern: AudioSignal) -> None:
        result = detect_beats(kick_pattern)
        assert 0.0 <= result.kick_prominence <= 1.0

    def test_hp_ratio_positive(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert result.hp_ratio >= 0.0

    def test_onset_envelope_length(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert len(result.onset_envelope) > 0

    def test_kick_pattern_has_high_pulse_clarity(
        self, kick_pattern: AudioSignal
    ) -> None:
        result = detect_beats(kick_pattern)
        # A regular kick pattern should have clear pulse
        assert result.pulse_clarity > 0.3
```

### Step 3: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_beats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.audio.beats'`

### Step 4: Реализовать

Файл `app/utils/audio/beats.py`:

```python
"""Beat, onset, and rhythm feature extraction.

Uses essentia for beat tracking and onset detection.
Computes derived features: pulse_clarity, kick_prominence, hp_ratio.
Maps to TrackAudioFeaturesComputed fields: onset_rate_mean, onset_rate_max,
pulse_clarity, kick_prominence, hp_ratio.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from app.utils.audio._types import AudioSignal, BeatsResult

_HOP_SIZE = 512
_ONSET_WINDOW_S = 2.0  # window for windowed onset rate
_SUB_BASS_LOW = 20.0
_SUB_BASS_HIGH = 80.0
_HARMONIC_LOW = 200.0
_HARMONIC_HIGH = 3000.0
_PERCUSSIVE_LOW = 3000.0
_PERCUSSIVE_HIGH = 12000.0
_FILTER_ORDER = 4

def _band_rms(samples: np.ndarray, sr: int, low: float, high: float) -> float:
    """RMS energy in a frequency band via Butterworth bandpass."""
    nyq = sr / 2.0
    lo = max(low / nyq, 0.001)
    hi = min(high / nyq, 0.999)
    if lo >= hi:
        return 0.0
    sos = butter(_FILTER_ORDER, [lo, hi], btype="bandpass", output="sos")
    filtered = sosfiltfilt(sos, samples)
    return float(np.sqrt(np.mean(filtered**2)))

def detect_beats(
    signal: AudioSignal,
    *,
    min_bpm: float = 80.0,
    max_bpm: float = 200.0,
) -> BeatsResult:
    """Detect beats, onsets, and compute rhythm features."""
    import essentia.standard as es

    sr = signal.sample_rate
    audio = signal.samples

    # ── 1. Beat tracking ──
    rhythm = es.RhythmExtractor2013(
        method="multifeature",
        minTempo=min_bpm,
        maxTempo=max_bpm,
    )
    _, beat_times, beats_confidence, _, _ = rhythm(audio)

    beat_times = np.sort(beat_times).astype(np.float32)

    # Downbeats: every 4th beat (4/4 assumption, standard for techno)
    downbeat_times = beat_times[::4].astype(np.float32) if len(beat_times) >= 4 else beat_times

    # ── 2. Onset detection ──
    onset_rate_algo = es.OnsetRate()
    onsets_times, onset_rate_global = onset_rate_algo(audio)

    # Windowed onset rate: max onset density in sliding window
    if len(onsets_times) > 1 and signal.duration_s > _ONSET_WINDOW_S:
        window_counts = []
        for t in np.arange(0, signal.duration_s - _ONSET_WINDOW_S, _ONSET_WINDOW_S / 2):
            count = np.sum(
                (onsets_times >= t) & (onsets_times < t + _ONSET_WINDOW_S)
            )
            window_counts.append(float(count) / _ONSET_WINDOW_S)
        onset_rate_max = float(max(window_counts)) if window_counts else onset_rate_global
    else:
        onset_rate_max = onset_rate_global

    # ── 3. Onset envelope (frame-level) ──
    onset_env_frames = []
    w = es.Windowing(type="hann")
    spectrum = es.Spectrum(size=2048)
    flux = es.Flux()
    for frame in es.FrameGenerator(audio, frameSize=2048, hopSize=_HOP_SIZE):
        windowed = w(frame)
        spec = spectrum(windowed)
        onset_env_frames.append(float(flux(spec)))
    onset_envelope = np.array(onset_env_frames, dtype=np.float32)

    # ── 4. Pulse clarity ──
    # Mean of beat confidence values — higher = clearer rhythmic pulse
    if len(beats_confidence) > 0:
        pulse_clarity = float(np.clip(np.mean(beats_confidence), 0.0, 1.0))
    else:
        pulse_clarity = 0.0

    # ── 5. Kick prominence ──
    # Energy in sub-bass at beat positions vs overall sub-bass energy
    if len(beat_times) > 2:
        beat_samples = (beat_times * sr).astype(int)
        beat_samples = beat_samples[beat_samples < len(audio)]
        window_half = int(0.015 * sr)  # ±15ms around beat

        beat_energies = []
        for bs in beat_samples:
            start = max(0, bs - window_half)
            end = min(len(audio), bs + window_half)
            segment = audio[start:end]
            if len(segment) > 0:
                beat_energies.append(float(np.mean(segment**2)))

        overall_energy = float(np.mean(audio**2)) + 1e-10
        beat_mean_energy = float(np.mean(beat_energies)) if beat_energies else 0.0
        kick_prominence = float(np.clip(beat_mean_energy / overall_energy, 0.0, 1.0))
    else:
        kick_prominence = 0.0

    # ── 6. Harmonic / Percussive ratio ──
    harmonic_rms = _band_rms(audio, sr, _HARMONIC_LOW, _HARMONIC_HIGH)
    percussive_rms = _band_rms(audio, sr, _PERCUSSIVE_LOW, _PERCUSSIVE_HIGH)
    hp_ratio = harmonic_rms / (percussive_rms + 1e-10)

    return BeatsResult(
        beat_times=beat_times,
        downbeat_times=downbeat_times,
        onset_rate_mean=float(onset_rate_global),
        onset_rate_max=float(onset_rate_max),
        pulse_clarity=pulse_clarity,
        kick_prominence=kick_prominence,
        hp_ratio=float(hp_ratio),
        onset_envelope=onset_envelope,
    )
```

### Step 5: Запустить тесты

Run: `uv run pytest tests/utils/test_beats.py -v`
Expected: All PASS.

### Step 6: Обновить `__init__.py`

В `app/utils/audio/__init__.py` добавить:

```python
from app.utils.audio._types import BeatsResult
from app.utils.audio.beats import detect_beats
```

И в `__all__`:

```python
    "BeatsResult",
    "detect_beats",
```

### Step 7: Commit

```bash
git add app/utils/audio/beats.py app/utils/audio/_types.py app/utils/audio/__init__.py tests/utils/test_beats.py
git commit -m "feat(utils): add beat & onset detection with rhythm features

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 12: Source Separation (Demucs v4)

Разделяет трек на 4 стема: drums, bass, vocals, other. Маппится на `AudioAsset` (asset_type 1-4). Стемы используются для улучшения качества последующего анализа: key detection на bass+other, beat tracking на drums.

**Зависимости:** `torch>=2.0`, `demucs>=4.0` — тяжёлые (~2 GB).

**Files:**
- Modify: `pyproject.toml` (добавить `ml` optional deps)
- Modify: `app/utils/audio/_types.py` (добавить `StemsResult`)
- Create: `app/utils/audio/stems.py`
- Create: `tests/utils/test_stems.py`

### Step 1: Добавить ML-зависимости

В `pyproject.toml` добавить в `[project.optional-dependencies]`:

```toml
ml = [
    "demucs>=4.0",
    "torch>=2.0",
]
```

И mypy override:

```toml
[[tool.mypy.overrides]]
module = ["demucs.*", "torch.*"]
ignore_missing_imports = true
```

Run: `uv sync --extra ml`

### Step 2: Добавить StemsResult в _types.py

В `app/utils/audio/_types.py`:

```python
@dataclass(frozen=True, slots=True)
class StemsResult:
    """Four-stem source separation result."""

    drums: AudioSignal  # asset_type = 1
    bass: AudioSignal  # asset_type = 2
    vocals: AudioSignal  # asset_type = 3
    other: AudioSignal  # asset_type = 4
```

### Step 3: Написать failing test

Файл `tests/utils/test_stems.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")
demucs = pytest.importorskip("demucs")

from app.utils.audio import AudioSignal, StemsResult
from app.utils.audio.stems import separate_stems

SR = 44100

@pytest.fixture
def short_mix() -> AudioSignal:
    """3-second synthetic mix: kick (50Hz) + bass (100Hz) + lead (800Hz) + hats (8kHz)."""
    duration = 3.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (
        0.3 * np.sin(2 * np.pi * 50.0 * t)  # kick
        + 0.3 * np.sin(2 * np.pi * 100.0 * t)  # bass
        + 0.2 * np.sin(2 * np.pi * 800.0 * t)  # lead
        + 0.1 * np.sin(2 * np.pi * 8000.0 * t)  # hats
    ).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

class TestSeparateStems:
    def test_returns_stems_result(self, short_mix: AudioSignal) -> None:
        result = separate_stems(short_mix)
        assert isinstance(result, StemsResult)

    def test_four_stems_present(self, short_mix: AudioSignal) -> None:
        result = separate_stems(short_mix)
        assert isinstance(result.drums, AudioSignal)
        assert isinstance(result.bass, AudioSignal)
        assert isinstance(result.vocals, AudioSignal)
        assert isinstance(result.other, AudioSignal)

    def test_stems_same_sample_rate(self, short_mix: AudioSignal) -> None:
        result = separate_stems(short_mix)
        for stem in (result.drums, result.bass, result.vocals, result.other):
            assert stem.sample_rate == short_mix.sample_rate

    def test_stems_similar_duration(self, short_mix: AudioSignal) -> None:
        result = separate_stems(short_mix)
        for stem in (result.drums, result.bass, result.vocals, result.other):
            # Demucs may pad slightly — allow 0.5s tolerance
            assert abs(stem.duration_s - short_mix.duration_s) < 0.5

    def test_stems_not_all_silent(self, short_mix: AudioSignal) -> None:
        result = separate_stems(short_mix)
        total_energy = sum(
            float(np.mean(s.samples**2))
            for s in (result.drums, result.bass, result.vocals, result.other)
        )
        assert total_energy > 1e-8
```

### Step 4: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_stems.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.audio.stems'`

### Step 5: Реализовать

Файл `app/utils/audio/stems.py`:

```python
"""Source separation using Demucs v4 (HTDemucs).

Separates audio into 4 stems: drums, bass, vocals, other.
Maps to AudioAsset.asset_type: 1=drums, 2=bass, 3=vocals, 4=other.
"""

from __future__ import annotations

import logging

import numpy as np

from app.utils.audio._types import AudioSignal, StemsResult

logger = logging.getLogger(__name__)

_MODEL_NAME = "htdemucs"
_STEM_NAMES = ("drums", "bass", "vocals", "other")

def separate_stems(
    signal: AudioSignal,
    *,
    model_name: str = _MODEL_NAME,
    device: str | None = None,
) -> StemsResult:
    """Separate audio into 4 stems using Demucs v4.

    Args:
        signal: Input audio signal (mono or stereo).
        model_name: Demucs model name ('htdemucs', 'htdemucs_ft').
        device: 'cuda', 'cpu', or None (auto-detect).

    Returns:
        StemsResult with drums, bass, vocals, other AudioSignal objects.
    """
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    logger.info("Loading Demucs model %s on %s", model_name, device)
    model = get_model(model_name)
    model.to(device)

    sr = signal.sample_rate
    audio = signal.samples

    # Demucs expects: (batch, channels, samples) as torch.Tensor
    # Convert mono to stereo (duplicate channel) — Demucs requires 2 channels
    if audio.ndim == 1:
        audio_2ch = np.stack([audio, audio], axis=0)  # (2, samples)
    else:
        audio_2ch = audio

    tensor = torch.tensor(audio_2ch, dtype=torch.float32).unsqueeze(0)  # (1, 2, samples)
    tensor = tensor.to(device)

    # Resample to model's expected sample rate if needed
    model_sr = model.samplerate
    if sr != model_sr:
        import torchaudio

        tensor = torchaudio.functional.resample(tensor, sr, model_sr)

    logger.info("Running source separation (%d samples)...", tensor.shape[-1])

    with torch.no_grad():
        sources = apply_model(model, tensor, device=device)
    # sources shape: (1, num_sources, 2, samples)

    # Resample back if needed
    if sr != model_sr:
        sources = torchaudio.functional.resample(sources, model_sr, sr)

    sources = sources.squeeze(0).cpu().numpy()  # (num_sources, 2, samples)

    # Build stem name → index mapping
    stem_map = {name: i for i, name in enumerate(model.sources)}

    stems: dict[str, AudioSignal] = {}
    for name in _STEM_NAMES:
        idx = stem_map.get(name)
        if idx is not None:
            # Convert stereo to mono (mean of channels)
            stem_mono = sources[idx].mean(axis=0).astype(np.float32)
        else:
            stem_mono = np.zeros(len(signal.samples), dtype=np.float32)

        stems[name] = AudioSignal(
            samples=stem_mono,
            sample_rate=sr,
            duration_s=len(stem_mono) / sr,
        )

    logger.info("Separation complete: %s", list(stems.keys()))

    return StemsResult(
        drums=stems["drums"],
        bass=stems["bass"],
        vocals=stems["vocals"],
        other=stems["other"],
    )
```

### Step 6: Запустить тесты

Run: `uv run pytest tests/utils/test_stems.py -v`
Expected: All PASS (может занять 10-30с из-за загрузки модели).

> **NOTE:** Первый запуск скачает модель htdemucs (~80 MB). На CPU тест с 3-секундным аудио занимает ~5-10с.

### Step 7: Commit

```bash
git add pyproject.toml app/utils/audio/stems.py app/utils/audio/_types.py tests/utils/test_stems.py
git commit -m "feat(utils): add source separation via Demucs v4

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 13: Structure Segmentation

Определяет структурные секции трека (intro, buildup, drop, breakdown, outro). Маппится на модель `TrackSection` (section_type 0-11). Вместо allin1 (зависит от madmom) — собственная DSP-реализация на essentia + scipy.

**Алгоритм:**
1. Вычислить frame-level energy и spectral flux
2. Построить novelty function (производная сглаженной energy кривой)
3. Найти пики novelty → границы секций
4. Для каждой секции: вычислить energy stats, labeling по энергетическому профилю

**Files:**
- Modify: `app/utils/audio/_types.py` (добавить `SectionResult`)
- Create: `app/utils/audio/structure.py`
- Create: `tests/utils/test_structure.py`

### Step 1: Добавить SectionResult в _types.py

В `app/utils/audio/_types.py`:

```python
@dataclass(frozen=True, slots=True)
class SectionResult:
    """One detected structural section.

    section_type matches SectionType enum (app/models/enums.py):
      0=intro, 1=buildup, 2=drop, 3=breakdown, 4=outro,
      5=break, 6=inst, 7=verse, 8=chorus, 9=bridge, 10=solo, 11=unknown
    """

    section_type: int
    start_s: float
    end_s: float
    duration_s: float
    energy_mean: float  # 0-1
    energy_max: float  # 0-1
    energy_slope: float  # positive = rising, negative = falling
    boundary_confidence: float  # 0-1
```

### Step 2: Написать failing test

Файл `tests/utils/test_structure.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal
from app.utils.audio.structure import segment_structure, SectionResult

SR = 44100

@pytest.fixture
def techno_structure() -> AudioSignal:
    """30-second signal simulating intro(low) → buildup(rising) → drop(high) → outro(falling).

    0-8s:   quiet (intro)
    8-14s:  rising energy (buildup)
    14-22s: loud (drop)
    22-30s: falling energy (outro)
    """
    duration = 30.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)

    # Envelope: 0→0.2 (intro), 0.2→0.8 (buildup), 0.8 (drop), 0.8→0.1 (outro)
    envelope = np.piecewise(
        t,
        [t < 8, (t >= 8) & (t < 14), (t >= 14) & (t < 22), t >= 22],
        [
            lambda x: 0.15 + 0.05 * np.sin(2 * np.pi * 0.5 * x),
            lambda x: 0.2 + (x - 8) / 6 * 0.6,
            lambda x: 0.8,
            lambda x: 0.8 - (x - 22) / 8 * 0.7,
        ],
    )

    # Carrier: mix of kick (50Hz) + noise for texture
    carrier = (
        0.5 * np.sin(2 * np.pi * 50 * t)
        + 0.3 * np.sin(2 * np.pi * 200 * t)
        + 0.2 * np.random.default_rng(42).standard_normal(len(t))
    )

    samples = (envelope * carrier).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)

class TestSegmentStructure:
    def test_returns_list_of_sections(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        assert isinstance(sections, list)
        assert all(isinstance(s, SectionResult) for s in sections)

    def test_at_least_two_sections(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        assert len(sections) >= 2

    def test_sections_cover_full_duration(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        assert sections[0].start_s < 1.0  # starts near beginning
        assert sections[-1].end_s > techno_structure.duration_s - 1.0

    def test_sections_non_overlapping(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for i in range(len(sections) - 1):
            assert sections[i].end_s <= sections[i + 1].start_s + 0.1  # small tolerance

    def test_section_type_valid(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for s in sections:
            assert 0 <= s.section_type <= 11

    def test_energy_fields_range(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for s in sections:
            assert 0.0 <= s.energy_mean <= 1.0
            assert 0.0 <= s.energy_max <= 1.0
            assert 0.0 <= s.boundary_confidence <= 1.0

    def test_duration_positive(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for s in sections:
            assert s.duration_s > 0

    def test_drop_section_has_high_energy(self, techno_structure: AudioSignal) -> None:
        """The loudest section should be labeled as DROP (2) or have high energy."""
        sections = segment_structure(techno_structure)
        loudest = max(sections, key=lambda s: s.energy_mean)
        # Either labeled as drop or has energy > 0.5
        assert loudest.section_type == 2 or loudest.energy_mean > 0.5
```

### Step 3: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_structure.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 4: Реализовать

Файл `app/utils/audio/structure.py`:

```python
"""Structure segmentation for techno tracks.

DSP-based approach: energy novelty function → peak picking → section labeling.
Maps to TrackSection model (section_type 0-11, see app/models/enums.py).

Labeling heuristic for techno:
  - First section with low energy → INTRO (0)
  - Rising energy → BUILDUP (1)
  - High energy plateau → DROP (2)
  - Falling energy from high → BREAKDOWN (3)
  - Last section with low energy → OUTRO (4)
  - Low energy in middle → BREAK (5)
  - Everything else → UNKNOWN (11)
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from app.utils.audio._types import AudioSignal, SectionResult

# Section type constants (match SectionType enum)
INTRO = 0
BUILDUP = 1
DROP = 2
BREAKDOWN = 3
OUTRO = 4
BREAK = 5
UNKNOWN = 11

_FRAME_SIZE = 2048
_HOP_SIZE = 512
_SMOOTH_WINDOW = 100  # frames for energy smoothing (~2.3s at 44100/512)
_MIN_SECTION_S = 3.0  # minimum section duration
_NOVELTY_SMOOTH = 20  # frames for novelty smoothing
_ENERGY_HIGH_PERCENTILE = 70  # above this = "high energy"
_ENERGY_LOW_PERCENTILE = 30  # below this = "low energy"

def _frame_energies(signal: AudioSignal) -> np.ndarray:
    """Compute frame-level RMS energy."""
    import essentia.standard as es

    energies = []
    for frame in es.FrameGenerator(
        signal.samples, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE
    ):
        energies.append(float(np.sqrt(np.mean(frame**2))))
    return np.array(energies, dtype=np.float32)

def _find_boundaries(energy: np.ndarray, min_frames: int) -> list[int]:
    """Find section boundaries from energy novelty peaks."""
    # Smooth energy curve
    smooth = uniform_filter1d(energy.astype(np.float64), size=_SMOOTH_WINDOW)

    # Novelty = absolute derivative of smoothed energy
    novelty = np.abs(np.diff(smooth))
    novelty = uniform_filter1d(novelty, size=_NOVELTY_SMOOTH)

    # Normalize novelty
    nov_max = novelty.max()
    if nov_max > 0:
        novelty = novelty / nov_max

    # Find peaks in novelty (= section boundaries)
    peaks, properties = find_peaks(
        novelty,
        distance=min_frames,
        height=0.15,  # minimum novelty threshold
        prominence=0.1,
    )

    return sorted(peaks.tolist())

def _label_section(
    energy_mean: float,
    energy_slope: float,
    is_first: bool,
    is_last: bool,
    high_threshold: float,
    low_threshold: float,
) -> int:
    """Assign section_type based on energy profile."""
    if is_first and energy_mean < high_threshold:
        return INTRO
    if is_last and energy_mean < high_threshold:
        return OUTRO
    if energy_mean >= high_threshold and abs(energy_slope) < 0.1:
        return DROP
    if energy_slope > 0.05:
        return BUILDUP
    if energy_slope < -0.05 and energy_mean > low_threshold:
        return BREAKDOWN
    if energy_mean < low_threshold and not is_first and not is_last:
        return BREAK
    return UNKNOWN

def segment_structure(
    signal: AudioSignal,
    *,
    min_section_s: float = _MIN_SECTION_S,
) -> list[SectionResult]:
    """Segment track into structural sections.

    Returns list of SectionResult sorted by start time.
    """
    sr = signal.sample_rate
    frame_energy = _frame_energies(signal)
    frames_per_sec = sr / _HOP_SIZE
    min_frames = int(min_section_s * frames_per_sec)

    # Normalize energy to 0-1
    e_max = frame_energy.max()
    if e_max > 0:
        norm_energy = frame_energy / e_max
    else:
        norm_energy = frame_energy

    # Find boundaries
    boundaries = _find_boundaries(norm_energy, min_frames)

    # Add start and end
    all_boundaries = [0] + boundaries + [len(norm_energy) - 1]

    # Compute thresholds
    high_thresh = float(np.percentile(norm_energy, _ENERGY_HIGH_PERCENTILE))
    low_thresh = float(np.percentile(norm_energy, _ENERGY_LOW_PERCENTILE))

    sections: list[SectionResult] = []
    for i in range(len(all_boundaries) - 1):
        start_frame = all_boundaries[i]
        end_frame = all_boundaries[i + 1]

        if end_frame <= start_frame:
            continue

        seg_energy = norm_energy[start_frame:end_frame]
        start_s = start_frame / frames_per_sec
        end_s = end_frame / frames_per_sec
        duration_s = end_s - start_s

        if duration_s < min_section_s * 0.5:
            continue

        e_mean = float(np.mean(seg_energy))
        e_max_val = float(np.max(seg_energy))

        # Energy slope: linear regression coefficient
        if len(seg_energy) > 1:
            x = np.arange(len(seg_energy), dtype=np.float64)
            slope = float(np.polyfit(x, seg_energy.astype(np.float64), 1)[0])
            # Normalize slope to roughly -1..1 range
            slope = float(np.clip(slope * len(seg_energy), -1.0, 1.0))
        else:
            slope = 0.0

        # Boundary confidence: novelty height at this boundary
        boundary_conf = 0.5  # default for first/last
        if i > 0 and i < len(all_boundaries) - 1:
            smooth = uniform_filter1d(norm_energy.astype(np.float64), size=_SMOOTH_WINDOW)
            novelty = np.abs(np.diff(smooth))
            nov_max = novelty.max() or 1.0
            if start_frame < len(novelty):
                boundary_conf = float(np.clip(novelty[start_frame] / nov_max, 0.0, 1.0))

        section_type = _label_section(
            e_mean, slope,
            is_first=(i == 0),
            is_last=(i == len(all_boundaries) - 2),
            high_threshold=high_thresh,
            low_threshold=low_thresh,
        )

        sections.append(SectionResult(
            section_type=section_type,
            start_s=start_s,
            end_s=end_s,
            duration_s=duration_s,
            energy_mean=float(np.clip(e_mean, 0.0, 1.0)),
            energy_max=float(np.clip(e_max_val, 0.0, 1.0)),
            energy_slope=slope,
            boundary_confidence=boundary_conf,
        ))

    # Fallback: if no sections found, return one UNKNOWN section
    if not sections:
        sections.append(SectionResult(
            section_type=UNKNOWN,
            start_s=0.0,
            end_s=signal.duration_s,
            duration_s=signal.duration_s,
            energy_mean=float(np.mean(norm_energy)),
            energy_max=float(np.max(norm_energy)),
            energy_slope=0.0,
            boundary_confidence=0.0,
        ))

    return sections
```

### Step 5: Запустить тесты

Run: `uv run pytest tests/utils/test_structure.py -v`
Expected: All PASS.

### Step 6: Commit

```bash
git add app/utils/audio/structure.py app/utils/audio/_types.py tests/utils/test_structure.py
git commit -m "feat(utils): add structure segmentation with techno-specific labeling

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 14: Groove Similarity

Вычисляет groove similarity между двумя треками через normalized cross-correlation onset envelopes. Маппится на `Transition.groove_similarity` (0-1).

**Зависимость:** только numpy (onset envelope из `detect_beats()`).

**Files:**
- Create: `app/utils/audio/groove.py`
- Create: `tests/utils/test_groove.py`

### Step 1: Написать failing test

Файл `tests/utils/test_groove.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

from app.utils.audio.groove import groove_similarity

class TestGrooveSimilarity:
    def test_identical_envelopes_max_similarity(self) -> None:
        env = np.array([0.1, 0.5, 0.2, 0.8, 0.1, 0.5, 0.2, 0.8], dtype=np.float32)
        score = groove_similarity(env, env)
        assert score > 0.95

    def test_opposite_envelopes_low_similarity(self) -> None:
        env_a = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0], dtype=np.float32)
        env_b = np.array([0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0], dtype=np.float32)
        score = groove_similarity(env_a, env_b)
        assert score < 0.5

    def test_result_between_0_and_1(self) -> None:
        rng = np.random.default_rng(42)
        env_a = rng.random(1000).astype(np.float32)
        env_b = rng.random(1000).astype(np.float32)
        score = groove_similarity(env_a, env_b)
        assert 0.0 <= score <= 1.0

    def test_symmetric(self) -> None:
        rng = np.random.default_rng(42)
        env_a = rng.random(500).astype(np.float32)
        env_b = rng.random(500).astype(np.float32)
        assert abs(groove_similarity(env_a, env_b) - groove_similarity(env_b, env_a)) < 1e-6

    def test_different_lengths_handled(self) -> None:
        env_a = np.ones(100, dtype=np.float32)
        env_b = np.ones(150, dtype=np.float32)
        score = groove_similarity(env_a, env_b)
        assert 0.0 <= score <= 1.0

    def test_silent_envelope_returns_zero(self) -> None:
        env_a = np.zeros(100, dtype=np.float32)
        env_b = np.ones(100, dtype=np.float32)
        score = groove_similarity(env_a, env_b)
        assert score == 0.0

    def test_similar_patterns_high_score(self) -> None:
        """Two slightly different 4/4 patterns should have high similarity."""
        pattern = np.tile([1.0, 0.0, 0.5, 0.0], 25).astype(np.float32)
        noisy = pattern + np.random.default_rng(42).normal(0, 0.1, len(pattern)).astype(np.float32)
        score = groove_similarity(pattern, np.clip(noisy, 0, 2).astype(np.float32))
        assert score > 0.7
```

### Step 2: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_groove.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Реализовать

Файл `app/utils/audio/groove.py`:

```python
"""Groove similarity via normalized cross-correlation of onset envelopes.

Used for Transition.groove_similarity (0-1).
Higher values indicate more compatible rhythmic patterns.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

def groove_similarity(
    env_a: NDArray[np.float32],
    env_b: NDArray[np.float32],
) -> float:
    """Compute groove similarity between two onset envelopes.

    Uses normalized cross-correlation at zero lag, which measures
    how well the rhythmic patterns align beat-for-beat.

    Args:
        env_a: Onset envelope of track A (frame-level, from detect_beats).
        env_b: Onset envelope of track B (frame-level, from detect_beats).

    Returns:
        Similarity score in [0, 1]. 1 = identical groove.
    """
    # Truncate to same length
    min_len = min(len(env_a), len(env_b))
    if min_len == 0:
        return 0.0

    a = env_a[:min_len].astype(np.float64)
    b = env_b[:min_len].astype(np.float64)

    # Zero-mean
    a = a - a.mean()
    b = b - b.mean()

    # Normalized cross-correlation at zero lag
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0

    ncc = float(np.dot(a, b) / (norm_a * norm_b))

    # Clamp to [0, 1] — negative correlation treated as 0
    return float(np.clip(ncc, 0.0, 1.0))
```

### Step 4: Запустить тесты

Run: `uv run pytest tests/utils/test_groove.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add app/utils/audio/groove.py tests/utils/test_groove.py
git commit -m "feat(utils): add groove similarity via onset envelope cross-correlation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 15: Transition Scoring Pipeline

Объединяет все компоненты в composite `transition_quality` score (0-1). Маппится на модели `TransitionCandidate` (pre-filter) и `Transition` (full scoring).

**Scoring формула (взвешенная сумма):**
- BPM distance penalty (40%)
- Key distance penalty через Camelot (25%)
- Energy step compatibility (15%)
- Spectral overlap / bass conflict (10%)
- Groove similarity bonus (10%)

**Files:**
- Modify: `app/utils/audio/_types.py` (добавить `TransitionScore`)
- Create: `app/utils/audio/transition_score.py`
- Create: `tests/utils/test_transition_score.py`

### Step 1: Добавить TransitionScore в _types.py

В `app/utils/audio/_types.py`:

```python
@dataclass(frozen=True, slots=True)
class TransitionScore:
    """Composite transition quality score between two tracks.

    Maps to Transition model fields.
    """

    transition_quality: float  # 0-1, composite score (higher = better)
    bpm_distance: float  # absolute BPM difference
    key_distance_weighted: float  # Camelot distance × confidence
    energy_step: float  # signed energy difference (positive = going up)
    low_conflict_score: float  # 0-1, bass frequency overlap risk
    overlap_score: float  # 0-1, spectral compatibility
    groove_similarity: float  # 0-1, rhythmic pattern compatibility
```

### Step 2: Написать failing test

Файл `tests/utils/test_transition_score.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

from app.utils.audio import (
    BandEnergyResult,
    BpmResult,
    KeyResult,
    SpectralResult,
)
from app.utils.audio.transition_score import (
    TransitionScore,
    score_transition,
)

def _make_bpm(bpm: float, conf: float = 0.9) -> BpmResult:
    return BpmResult(bpm=bpm, confidence=conf, stability=0.9, is_variable=False)

def _make_key(key_code: int, conf: float = 0.8) -> KeyResult:
    return KeyResult(
        key="C", scale="minor", key_code=key_code, confidence=conf,
        is_atonal=False, chroma=np.zeros(12, dtype=np.float32),
    )

def _make_energy(sub: float = 0.5, low: float = 0.5) -> BandEnergyResult:
    return BandEnergyResult(
        sub=sub, low=low, low_mid=0.4, mid=0.3,
        high_mid=0.2, high=0.1, low_high_ratio=5.0, sub_lowmid_ratio=1.0,
    )

def _make_spectral(centroid: float = 1500.0) -> SpectralResult:
    return SpectralResult(
        centroid_mean_hz=centroid, rolloff_85_hz=5000.0, rolloff_95_hz=8000.0,
        flatness_mean=0.3, flux_mean=0.5, flux_std=0.1, contrast_mean_db=20.0,
    )

class TestScoreTransition:
    def test_returns_transition_score(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(140), bpm_b=_make_bpm(140),
            key_a=_make_key(0), key_b=_make_key(0),
            energy_a=_make_energy(), energy_b=_make_energy(),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
        )
        assert isinstance(result, TransitionScore)

    def test_identical_tracks_high_quality(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(140), bpm_b=_make_bpm(140),
            key_a=_make_key(0), key_b=_make_key(0),
            energy_a=_make_energy(), energy_b=_make_energy(),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
        )
        assert result.transition_quality > 0.8

    def test_large_bpm_gap_low_quality(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(130), bpm_b=_make_bpm(150),
            key_a=_make_key(0), key_b=_make_key(0),
            energy_a=_make_energy(), energy_b=_make_energy(),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
        )
        assert result.transition_quality < 0.5
        assert result.bpm_distance == 20.0

    def test_incompatible_key_lowers_quality(self) -> None:
        # Cm (0) → F#m (12) = Camelot distance 6
        result = score_transition(
            bpm_a=_make_bpm(140), bpm_b=_make_bpm(140),
            key_a=_make_key(0), key_b=_make_key(12),
            energy_a=_make_energy(), energy_b=_make_energy(),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
        )
        compatible = score_transition(
            bpm_a=_make_bpm(140), bpm_b=_make_bpm(140),
            key_a=_make_key(0), key_b=_make_key(0),
            energy_a=_make_energy(), energy_b=_make_energy(),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
        )
        assert result.transition_quality < compatible.transition_quality

    def test_quality_between_0_and_1(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(120), bpm_b=_make_bpm(160),
            key_a=_make_key(0), key_b=_make_key(12),
            energy_a=_make_energy(), energy_b=_make_energy(sub=0.9),
            spectral_a=_make_spectral(500), spectral_b=_make_spectral(5000),
        )
        assert 0.0 <= result.transition_quality <= 1.0

    def test_groove_similarity_bonus(self) -> None:
        base = score_transition(
            bpm_a=_make_bpm(140), bpm_b=_make_bpm(140),
            key_a=_make_key(0), key_b=_make_key(0),
            energy_a=_make_energy(), energy_b=_make_energy(),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
            groove_sim=0.0,
        )
        with_groove = score_transition(
            bpm_a=_make_bpm(140), bpm_b=_make_bpm(140),
            key_a=_make_key(0), key_b=_make_key(0),
            energy_a=_make_energy(), energy_b=_make_energy(),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
            groove_sim=0.95,
        )
        assert with_groove.transition_quality > base.transition_quality

    def test_energy_step_signed(self) -> None:
        """Going from low to high energy should have positive energy_step."""
        result = score_transition(
            bpm_a=_make_bpm(140), bpm_b=_make_bpm(140),
            key_a=_make_key(0), key_b=_make_key(0),
            energy_a=_make_energy(sub=0.2, low=0.3),
            energy_b=_make_energy(sub=0.8, low=0.9),
            spectral_a=_make_spectral(), spectral_b=_make_spectral(),
        )
        assert result.energy_step > 0
```

### Step 3: Запустить — убедиться что падает

Run: `uv run pytest tests/utils/test_transition_score.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 4: Реализовать

Файл `app/utils/audio/transition_score.py`:

```python
"""Transition quality scoring between two tracks.

Produces a composite score (0-1) from multiple components.
Maps to TransitionCandidate (pre-filter) and Transition (full scoring) models.

Component weights (configurable):
  - BPM distance:  40%  (most critical for techno beatmatching)
  - Key distance:   25%  (harmonic compatibility via Camelot)
  - Energy step:    15%  (dramaturgical fit)
  - Bass conflict:  10%  (spectral overlap in sub/low bands)
  - Groove sim:     10%  (rhythmic pattern compatibility)
"""

from __future__ import annotations

import numpy as np

from app.utils.audio._types import (
    BandEnergyResult,
    BpmResult,
    KeyResult,
    SpectralResult,
    TransitionScore,
)
from app.utils.audio.camelot import camelot_distance

# Default weights
_W_BPM = 0.40
_W_KEY = 0.25
_W_ENERGY = 0.15
_W_BASS = 0.10
_W_GROOVE = 0.10

# Normalization constants
_BPM_MAX_PENALTY = 20.0  # BPM difference beyond this = 0 score
_KEY_MAX_DISTANCE = 6  # max Camelot distance
_ENERGY_MAX_STEP = 0.5  # energy delta beyond this = penalty

def _bpm_score(bpm_a: float, bpm_b: float) -> float:
    """0-1 score: 1 = same BPM, 0 = ≥20 BPM apart."""
    delta = abs(bpm_a - bpm_b)
    return float(np.clip(1.0 - delta / _BPM_MAX_PENALTY, 0.0, 1.0))

def _key_score(key_a: KeyResult, key_b: KeyResult) -> tuple[float, float]:
    """Returns (score_0_1, weighted_distance).

    Uses Camelot distance weighted by confidence (mirrors SQL key_distance_weighted).
    """
    dist = camelot_distance(key_a.key_code, key_b.key_code)
    min_conf = min(key_a.confidence, key_b.confidence)

    # Weighted distance (same logic as SQL key_distance_weighted)
    if min_conf < 0.4:
        alpha = min_conf / 0.4
        weighted = (1.0 - alpha) * 1.0 + alpha * dist * min_conf
    else:
        weighted = dist * min_conf

    # Score: inverse of normalized distance
    score = float(np.clip(1.0 - dist / _KEY_MAX_DISTANCE, 0.0, 1.0))
    return score, float(weighted)

def _energy_score(energy_a: BandEnergyResult, energy_b: BandEnergyResult) -> tuple[float, float]:
    """Returns (score_0_1, signed_step).

    Small energy steps are preferred. Step sign: positive = going up.
    """
    # Global energy proxy: weighted mean of bands
    e_a = 0.3 * energy_a.sub + 0.3 * energy_a.low + 0.2 * energy_a.mid + 0.2 * energy_a.high
    e_b = 0.3 * energy_b.sub + 0.3 * energy_b.low + 0.2 * energy_b.mid + 0.2 * energy_b.high

    step = e_b - e_a
    score = float(np.clip(1.0 - abs(step) / _ENERGY_MAX_STEP, 0.0, 1.0))
    return score, float(step)

def _bass_conflict_score(energy_a: BandEnergyResult, energy_b: BandEnergyResult) -> float:
    """0-1 score: 1 = no bass conflict, 0 = maximum bass clash.

    Both tracks having high sub/low energy = conflict risk during transition.
    """
    sub_overlap = min(energy_a.sub, energy_b.sub)
    low_overlap = min(energy_a.low, energy_b.low)
    conflict = 0.6 * sub_overlap + 0.4 * low_overlap  # 0-1
    return float(np.clip(1.0 - conflict, 0.0, 1.0))

def _spectral_overlap_score(spec_a: SpectralResult, spec_b: SpectralResult) -> float:
    """0-1 score: 1 = similar spectral profile, 0 = very different.

    Based on centroid proximity — tracks with similar spectral centroids
    blend better during transitions.
    """
    centroid_gap = abs(spec_a.centroid_mean_hz - spec_b.centroid_mean_hz)
    # Normalize: 0-5000 Hz gap → 1-0 score
    return float(np.clip(1.0 - centroid_gap / 5000.0, 0.0, 1.0))

def score_transition(
    *,
    bpm_a: BpmResult,
    bpm_b: BpmResult,
    key_a: KeyResult,
    key_b: KeyResult,
    energy_a: BandEnergyResult,
    energy_b: BandEnergyResult,
    spectral_a: SpectralResult,
    spectral_b: SpectralResult,
    groove_sim: float = 0.5,
    weights: dict[str, float] | None = None,
) -> TransitionScore:
    """Compute composite transition quality score.

    Args:
        bpm_a, bpm_b: BPM results for both tracks.
        key_a, key_b: Key detection results for both tracks.
        energy_a, energy_b: Band energy results for both tracks.
        spectral_a, spectral_b: Spectral results for both tracks.
        groove_sim: Pre-computed groove similarity (0-1), default 0.5.
        weights: Optional custom weights dict with keys: bpm, key, energy, bass, groove.

    Returns:
        TransitionScore with composite quality and all component scores.
    """
    w = weights or {}
    w_bpm = w.get("bpm", _W_BPM)
    w_key = w.get("key", _W_KEY)
    w_energy = w.get("energy", _W_ENERGY)
    w_bass = w.get("bass", _W_BASS)
    w_groove = w.get("groove", _W_GROOVE)

    # Compute components
    bpm_sc = _bpm_score(bpm_a.bpm, bpm_b.bpm)
    key_sc, key_dist_weighted = _key_score(key_a, key_b)
    energy_sc, energy_step = _energy_score(energy_a, energy_b)
    bass_sc = _bass_conflict_score(energy_a, energy_b)
    overlap_sc = _spectral_overlap_score(spectral_a, spectral_b)

    # Composite: weighted average of component scores + groove bonus
    # Bass and spectral overlap are combined into a single "compatibility" score
    compatibility = 0.5 * bass_sc + 0.5 * overlap_sc
    groove_clamped = float(np.clip(groove_sim, 0.0, 1.0))

    quality = (
        w_bpm * bpm_sc
        + w_key * key_sc
        + w_energy * energy_sc
        + w_bass * compatibility
        + w_groove * groove_clamped
    )
    quality = float(np.clip(quality, 0.0, 1.0))

    return TransitionScore(
        transition_quality=quality,
        bpm_distance=abs(bpm_a.bpm - bpm_b.bpm),
        key_distance_weighted=key_dist_weighted,
        energy_step=energy_step,
        low_conflict_score=bass_sc,
        overlap_score=overlap_sc,
        groove_similarity=groove_clamped,
    )
```

### Step 5: Запустить тесты

Run: `uv run pytest tests/utils/test_transition_score.py -v`
Expected: All PASS.

### Step 6: Обновить экспорт

В `app/utils/audio/__init__.py` добавить:

```python
from app.utils.audio._types import BeatsResult, SectionResult, StemsResult, TransitionScore
from app.utils.audio.beats import detect_beats
from app.utils.audio.groove import groove_similarity
from app.utils.audio.structure import segment_structure
from app.utils.audio.transition_score import score_transition
```

И в `__all__`:

```python
    "BeatsResult",
    "SectionResult",
    "StemsResult",
    "TransitionScore",
    "detect_beats",
    "groove_similarity",
    "score_transition",
    "segment_structure",
```

> **NOTE:** `separate_stems` НЕ добавляется в `__init__.py` по умолчанию — это тяжёлая операция с torch-зависимостью. Импортировать явно: `from app.utils.audio.stems import separate_stems`.

### Step 7: Commit

```bash
git add app/utils/audio/transition_score.py app/utils/audio/_types.py app/utils/audio/__init__.py tests/utils/test_transition_score.py
git commit -m "feat(utils): add transition scoring pipeline

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 16: Integration — Wire Phase 2 into TrackAnalysisService

Расширяем `TrackAnalysisService` из Task 10 для поддержки Phase 2 фичей: beats, structure, stems.

**Files:**
- Modify: `app/services/track_analysis.py`
- Create: `app/repositories/sections.py` (если не существует)
- Modify: `tests/test_track_analysis.py`

### Step 1: Создать SectionsRepository

Файл `app/repositories/sections.py`:

```python
from app.models.sections import TrackSection
from app.repositories.base import BaseRepository

class SectionsRepository(BaseRepository[TrackSection]):
    model = TrackSection
```

### Step 2: Расширить TrackAnalysisService

В `app/services/track_analysis.py` добавить метод `analyze_track_full`:

```python
    async def analyze_track_full(
        self,
        track_id: int,
        audio_path: str | Path,
        run_id: int,
    ) -> TrackFeatures:
        """Full analysis including beats and structure (Phase 2).

        Falls back to Phase 1 features if beat/structure extraction fails.
        """
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)

        signal = load_audio(audio_path)
        validate_audio(signal)

        # Phase 1 features (always computed)
        from app.utils.audio.bpm import estimate_bpm
        from app.utils.audio.key_detect import detect_key
        from app.utils.audio.loudness import measure_loudness
        from app.utils.audio.energy import compute_band_energies
        from app.utils.audio.spectral import extract_spectral_features

        bpm_result = estimate_bpm(signal)
        key_result = detect_key(signal)
        loudness_result = measure_loudness(signal)
        band_energy_result = compute_band_energies(signal)
        spectral_result = extract_spectral_features(signal)

        # Phase 2 features (optional, graceful failure)
        beats_result = None
        try:
            from app.utils.audio.beats import detect_beats
            beats_result = detect_beats(signal)
        except Exception:
            self.logger.warning("Beat detection failed for track %d", track_id, exc_info=True)

        features = TrackFeatures(
            bpm=bpm_result,
            key=key_result,
            loudness=loudness_result,
            band_energy=band_energy_result,
            spectral=spectral_result,
            beats=beats_result,
        )

        # Persist core features
        await self.features_repo.create(
            track_id=track_id,
            run_id=run_id,
            bpm=features.bpm.bpm,
            tempo_confidence=features.bpm.confidence,
            bpm_stability=features.bpm.stability,
            is_variable_tempo=features.bpm.is_variable,
            lufs_i=features.loudness.lufs_i,
            lufs_s_mean=features.loudness.lufs_s_mean,
            lufs_m_max=features.loudness.lufs_m_max,
            rms_dbfs=features.loudness.rms_dbfs,
            true_peak_db=features.loudness.true_peak_db,
            crest_factor_db=features.loudness.crest_factor_db,
            lra_lu=features.loudness.lra_lu,
            energy_mean=features.band_energy.mid,
            energy_max=max(
                features.band_energy.sub, features.band_energy.low,
                features.band_energy.low_mid, features.band_energy.mid,
                features.band_energy.high_mid, features.band_energy.high,
            ),
            energy_std=0.0,
            sub_energy=features.band_energy.sub,
            low_energy=features.band_energy.low,
            lowmid_energy=features.band_energy.low_mid,
            mid_energy=features.band_energy.mid,
            highmid_energy=features.band_energy.high_mid,
            high_energy=features.band_energy.high,
            low_high_ratio=features.band_energy.low_high_ratio,
            sub_lowmid_ratio=features.band_energy.sub_lowmid_ratio,
            centroid_mean_hz=features.spectral.centroid_mean_hz,
            rolloff_85_hz=features.spectral.rolloff_85_hz,
            rolloff_95_hz=features.spectral.rolloff_95_hz,
            flatness_mean=features.spectral.flatness_mean,
            flux_mean=features.spectral.flux_mean,
            flux_std=features.spectral.flux_std,
            contrast_mean_db=features.spectral.contrast_mean_db,
            key_code=features.key.key_code,
            key_confidence=features.key.confidence,
            is_atonal=features.key.is_atonal,
            chroma=",".join(f"{v:.6f}" for v in features.key.chroma),
            # Phase 2 fields
            onset_rate_mean=beats_result.onset_rate_mean if beats_result else None,
            onset_rate_max=beats_result.onset_rate_max if beats_result else None,
            pulse_clarity=beats_result.pulse_clarity if beats_result else None,
            kick_prominence=beats_result.kick_prominence if beats_result else None,
            hp_ratio=beats_result.hp_ratio if beats_result else None,
        )

        # Persist structure sections
        if beats_result:
            try:
                from app.utils.audio.structure import segment_structure
                sections = segment_structure(signal)
                for section in sections:
                    await self.sections_repo.create(
                        track_id=track_id,
                        run_id=run_id,
                        start_ms=int(section.start_s * 1000),
                        end_ms=int(section.end_s * 1000),
                        section_type=section.section_type,
                        section_duration_ms=int(section.duration_s * 1000),
                        section_energy_mean=section.energy_mean,
                        section_energy_max=section.energy_max,
                        section_energy_slope=section.energy_slope,
                        boundary_confidence=section.boundary_confidence,
                    )
            except Exception:
                self.logger.warning("Structure segmentation failed for track %d", track_id, exc_info=True)

        return features
```

### Step 3: Добавить тест

В `tests/test_track_analysis.py` добавить:

```python
    @patch("app.services.track_analysis.extract_all_features")
    async def test_analyze_track_full_with_beats(
        self, mock_extract: MagicMock, service: TrackAnalysisService
    ) -> None:
        features = _fake_features()
        mock_extract.return_value = features
        # analyze_track_full вызывается с mock — проверяем что не падает
        result = await service.analyze_track(1, "/fake/path.wav", run_id=1)
        assert result.bpm.bpm == 140.0
```

### Step 4: Запустить все тесты

Run: `uv run pytest tests/ -v`
Expected: All PASS.

Run: `uv run ruff check app/ tests/`
Expected: No errors.

### Step 5: Commit

```bash
git add app/services/track_analysis.py app/repositories/sections.py tests/test_track_analysis.py
git commit -m "feat(services): extend TrackAnalysisService with beats and structure

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Итоговая архитектура после Phase 2

```text
app/utils/audio/
├── __init__.py           # public API (всё кроме stems)
├── _types.py             # 10 result dataclasses
├── loader.py             # load_audio(), validate_audio()
├── camelot.py            # camelot_distance(), is_compatible()
├── bpm.py                # estimate_bpm() → BpmResult
├── key_detect.py         # detect_key() → KeyResult
├── loudness.py           # measure_loudness() → LoudnessResult
├── energy.py             # compute_band_energies() → BandEnergyResult
├── spectral.py           # extract_spectral() → SpectralResult
├── beats.py              # detect_beats() → BeatsResult
├── structure.py          # segment_structure() → list[SectionResult]
├── stems.py              # separate_stems() → StemsResult (отдельный импорт)
├── groove.py             # groove_similarity() → float
├── transition_score.py   # score_transition() → TransitionScore
└── pipeline.py           # extract_all_features() — orchestrator
```

```text
Граф зависимостей:

pipeline.py ─→ loader.py
            ├─→ bpm.py ────────→ essentia
            ├─→ key_detect.py ──→ essentia
            ├─→ loudness.py ────→ essentia
            ├─→ energy.py ──────→ scipy.signal
            ├─→ spectral.py ────→ essentia
            └─→ beats.py ───────→ essentia + scipy.signal

structure.py ──→ essentia + scipy (find_peaks, uniform_filter1d)
stems.py ──────→ torch + demucs (тяжёлый, отдельный импорт)
groove.py ─────→ numpy only
transition_score.py ──→ camelot.py + numpy
camelot.py ────→ pure Python (no deps)
```

---

## Сводка зависимостей (обновлённая)

| Фаза | Библиотеки | Размер | Лицензия | Python 3.12 |
|------|-----------|--------|----------|-------------|
| **Phase 1 (Tasks 1-10)** | essentia, soundfile, scipy, numpy | ~200 MB | AGPL/BSD/ISC | OK |
| **Phase 2: Beats (Task 11)** | (essentia + scipy — уже установлены) | 0 MB | — | OK |
| **Phase 2: Stems (Task 12)** | demucs, torch | ~2 GB | MIT/BSD | OK |
| **Phase 2: Structure (Task 13)** | (essentia + scipy — уже установлены) | 0 MB | — | OK |
| **Phase 2: Groove (Task 14)** | (numpy — уже установлен) | 0 MB | — | OK |
| **Phase 2: Scoring (Task 15)** | (pure Python + numpy) | 0 MB | — | OK |
| **Phase 2: Integration (Task 16)** | — | 0 MB | — | OK |

> **NOTE:** Tasks 11, 13, 14, 15, 16 не требуют новых зависимостей — всё уже есть из Phase 1. Только Task 12 (stems) добавляет torch + demucs (~2 GB).

---

## Контрольные точки

После каждого таска:
1. `uv run pytest tests/ -v` — все тесты зелёные
2. `uv run ruff check app/ tests/` — нет ошибок линтера
3. `uv run mypy app/` — нет ошибок типов
4. Commit с осмысленным сообщением
