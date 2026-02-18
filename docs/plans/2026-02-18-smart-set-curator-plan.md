# Smart Set Curator — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add mood classification, slot-based track selection, improved GA fitness, iterative review workflow, and library gap analysis to the DJ set generation system.

**Architecture:** Pure-function mood classifier feeds into a curation service that selects tracks by template slots, then passes candidates to an improved GA (LUFS energy + variety penalty). New MCP tools enable review/adjust cycles. All new modules follow existing Router->Service->Repository pattern with frozen dataclasses for pure computation and Pydantic models for MCP output.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, FastMCP 3.0, Pydantic v2, numpy, pytest

---

## Task 1: Mood Classifier — Pure Function Module

**Files:**
- Create: `app/utils/audio/mood_classifier.py`
- Test: `tests/utils/test_mood_classifier.py`

**Step 1: Write the failing tests**

Create `tests/utils/test_mood_classifier.py`:

```python
"""Tests for rule-based mood classifier."""

from app.utils.audio.mood_classifier import (
    MoodClassification,
    TrackMood,
    classify_track,
)

def test_hard_techno_high_bpm_high_kick():
    result = classify_track(bpm=142.0, lufs_i=-7.0, kick_prominence=0.8,
                            spectral_centroid_mean=3000.0, onset_rate=6.0,
                            hp_ratio=0.3)
    assert result.mood == TrackMood.HARD_TECHNO

def test_industrial_high_centroid_high_onset():
    result = classify_track(bpm=132.0, lufs_i=-8.0, kick_prominence=0.4,
                            spectral_centroid_mean=5000.0, onset_rate=10.0,
                            hp_ratio=0.3)
    assert result.mood == TrackMood.INDUSTRIAL

def test_ambient_dub_low_bpm_low_lufs():
    result = classify_track(bpm=122.0, lufs_i=-13.0, kick_prominence=0.3,
                            spectral_centroid_mean=1500.0, onset_rate=3.0,
                            hp_ratio=0.6)
    assert result.mood == TrackMood.AMBIENT_DUB

def test_peak_time_high_kick_high_lufs():
    result = classify_track(bpm=130.0, lufs_i=-6.5, kick_prominence=0.7,
                            spectral_centroid_mean=2500.0, onset_rate=5.0,
                            hp_ratio=0.4)
    assert result.mood == TrackMood.PEAK_TIME

def test_melodic_deep_high_hp_low_centroid():
    result = classify_track(bpm=128.0, lufs_i=-9.0, kick_prominence=0.3,
                            spectral_centroid_mean=1800.0, onset_rate=4.0,
                            hp_ratio=0.7)
    assert result.mood == TrackMood.MELODIC_DEEP

def test_driving_default_category():
    result = classify_track(bpm=130.0, lufs_i=-9.0, kick_prominence=0.5,
                            spectral_centroid_mean=2500.0, onset_rate=5.0,
                            hp_ratio=0.5)
    assert result.mood == TrackMood.DRIVING

def test_classification_has_confidence():
    result = classify_track(bpm=142.0, lufs_i=-7.0, kick_prominence=0.8,
                            spectral_centroid_mean=3000.0, onset_rate=6.0,
                            hp_ratio=0.3)
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.features_used) > 0

def test_classify_track_returns_frozen_dataclass():
    result = classify_track(bpm=130.0, lufs_i=-9.0, kick_prominence=0.5,
                            spectral_centroid_mean=2500.0, onset_rate=5.0,
                            hp_ratio=0.5)
    assert isinstance(result, MoodClassification)

def test_mood_energy_order():
    """TrackMood.energy_order() returns moods sorted by intensity."""
    order = TrackMood.energy_order()
    assert order == [
        TrackMood.AMBIENT_DUB,
        TrackMood.MELODIC_DEEP,
        TrackMood.DRIVING,
        TrackMood.PEAK_TIME,
        TrackMood.INDUSTRIAL,
        TrackMood.HARD_TECHNO,
    ]

def test_mood_intensity_value():
    assert TrackMood.AMBIENT_DUB.intensity == 1
    assert TrackMood.HARD_TECHNO.intensity == 6

def test_priority_hard_techno_over_industrial():
    """HARD_TECHNO (bpm>=140, kick>0.6) takes priority over INDUSTRIAL."""
    result = classify_track(bpm=145.0, lufs_i=-7.0, kick_prominence=0.8,
                            spectral_centroid_mean=5000.0, onset_rate=10.0,
                            hp_ratio=0.3)
    assert result.mood == TrackMood.HARD_TECHNO

def test_priority_industrial_over_ambient():
    """INDUSTRIAL takes priority over AMBIENT_DUB."""
    result = classify_track(bpm=125.0, lufs_i=-13.0, kick_prominence=0.3,
                            spectral_centroid_mean=5000.0, onset_rate=10.0,
                            hp_ratio=0.3)
    assert result.mood == TrackMood.INDUSTRIAL
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/utils/test_mood_classifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.audio.mood_classifier'`

**Step 3: Write the implementation**

Create `app/utils/audio/mood_classifier.py`:

```python
"""Rule-based mood classification for techno tracks.

Classifies tracks into 6 mood categories using audio features.
Priority order (first match wins):
  HARD_TECHNO → INDUSTRIAL → AMBIENT_DUB → PEAK_TIME → MELODIC_DEEP → DRIVING

Pure computation — no DB, no IO, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_INTENSITY_MAP: dict[str, int] = {
    "ambient_dub": 1,
    "melodic_deep": 2,
    "driving": 3,
    "peak_time": 4,
    "industrial": 5,
    "hard_techno": 6,
}

class TrackMood(StrEnum):
    """Techno mood categories ordered by energy intensity."""

    AMBIENT_DUB = "ambient_dub"
    MELODIC_DEEP = "melodic_deep"
    DRIVING = "driving"
    PEAK_TIME = "peak_time"
    INDUSTRIAL = "industrial"
    HARD_TECHNO = "hard_techno"

    @property
    def intensity(self) -> int:
        """Energy intensity level (1=lowest, 6=highest)."""
        return _INTENSITY_MAP[self.value]

    @classmethod
    def energy_order(cls) -> list[TrackMood]:
        """Return moods sorted by increasing energy intensity."""
        return sorted(cls, key=lambda m: m.intensity)

@dataclass(frozen=True, slots=True)
class MoodClassification:
    """Result of mood classification for a single track."""

    mood: TrackMood
    confidence: float  # 0.0-1.0
    features_used: tuple[str, ...]  # which features triggered the classification

def classify_track(
    *,
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    spectral_centroid_mean: float,
    onset_rate: float,
    hp_ratio: float,
) -> MoodClassification:
    """Classify a track into one of 6 mood categories.

    Uses priority-based rule matching (first match wins).

    Args:
        bpm: Track tempo in BPM.
        lufs_i: Integrated loudness (LUFS).
        kick_prominence: Kick energy at beat positions [0, 1].
        spectral_centroid_mean: Mean spectral centroid (Hz).
        onset_rate: Onsets per second.
        hp_ratio: Harmonic/percussive energy ratio [0, 1].

    Returns:
        MoodClassification with mood, confidence, and features_used.
    """
    # Priority 1: HARD_TECHNO — fast + percussive
    if bpm >= 140 and kick_prominence > 0.6:
        conf = min(1.0, (bpm - 140) / 10 * 0.5 + kick_prominence * 0.5)
        return MoodClassification(
            mood=TrackMood.HARD_TECHNO,
            confidence=conf,
            features_used=("bpm", "kick_prominence"),
        )

    # Priority 2: INDUSTRIAL — harsh + busy
    if spectral_centroid_mean > 4000 and onset_rate > 8:
        conf = min(1.0, (spectral_centroid_mean - 4000) / 2000 * 0.5 + (onset_rate - 8) / 4 * 0.5)
        return MoodClassification(
            mood=TrackMood.INDUSTRIAL,
            confidence=conf,
            features_used=("spectral_centroid_mean", "onset_rate"),
        )

    # Priority 3: AMBIENT_DUB — slow + quiet
    if bpm < 128 and lufs_i < -11:
        conf = min(1.0, (128 - bpm) / 10 * 0.5 + (-11 - lufs_i) / 5 * 0.5)
        return MoodClassification(
            mood=TrackMood.AMBIENT_DUB,
            confidence=conf,
            features_used=("bpm", "lufs_i"),
        )

    # Priority 4: PEAK_TIME — heavy kick + loud
    if kick_prominence > 0.6 and lufs_i > -8:
        conf = min(1.0, kick_prominence * 0.5 + (lufs_i + 8) / 4 * 0.5)
        return MoodClassification(
            mood=TrackMood.PEAK_TIME,
            confidence=conf,
            features_used=("kick_prominence", "lufs_i"),
        )

    # Priority 5: MELODIC_DEEP — harmonic + warm
    if hp_ratio > 0.6 and spectral_centroid_mean < 2000:
        conf = min(1.0, hp_ratio * 0.5 + (2000 - spectral_centroid_mean) / 1000 * 0.5)
        return MoodClassification(
            mood=TrackMood.MELODIC_DEEP,
            confidence=conf,
            features_used=("hp_ratio", "spectral_centroid_mean"),
        )

    # Default: DRIVING
    return MoodClassification(
        mood=TrackMood.DRIVING,
        confidence=0.5,
        features_used=(),
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/utils/test_mood_classifier.py -v`
Expected: All PASS

**Step 5: Lint**

Run: `uv run ruff check app/utils/audio/mood_classifier.py tests/utils/test_mood_classifier.py && uv run ruff format --check app/utils/audio/mood_classifier.py tests/utils/test_mood_classifier.py`

**Step 6: Commit**

```bash
git add app/utils/audio/mood_classifier.py tests/utils/test_mood_classifier.py
git commit -m "feat: add rule-based mood classifier (6 techno categories)"
```

---

## Task 2: Slot-Based Set Templates

**Files:**
- Create: `app/utils/audio/set_templates.py`
- Test: `tests/utils/test_set_templates.py`

**Step 1: Write the failing tests**

Create `tests/utils/test_set_templates.py`:

```python
"""Tests for set templates and slot definitions."""

from app.utils.audio.mood_classifier import TrackMood
from app.utils.audio.set_templates import (
    SetSlot,
    SetTemplate,
    TemplateName,
    get_template,
    list_templates,
)

def test_list_templates_returns_all():
    names = list_templates()
    assert TemplateName.CLASSIC_60 in names
    assert TemplateName.ROLLER_90 in names
    assert TemplateName.FULL_LIBRARY in names
    assert len(names) >= 8

def test_get_classic_60():
    t = get_template(TemplateName.CLASSIC_60)
    assert t.name == TemplateName.CLASSIC_60
    assert 18 <= t.target_track_count <= 22
    assert 55 <= t.duration_minutes <= 65
    assert len(t.slots) >= 5

def test_classic_60_starts_with_ambient():
    t = get_template(TemplateName.CLASSIC_60)
    first_slot = t.slots[0]
    assert first_slot.mood in (TrackMood.AMBIENT_DUB, TrackMood.MELODIC_DEEP)

def test_classic_60_has_breathing_moment():
    t = get_template(TemplateName.CLASSIC_60)
    moods = [s.mood for s in t.slots]
    # After a PEAK_TIME, there should be a lower-energy mood before another peak
    for i in range(1, len(moods) - 1):
        if moods[i - 1] == TrackMood.PEAK_TIME and moods[i + 1] == TrackMood.PEAK_TIME:
            assert moods[i].intensity < TrackMood.PEAK_TIME.intensity

def test_slot_positions_are_sorted():
    for name in list_templates():
        t = get_template(name)
        positions = [s.position for s in t.slots]
        assert positions == sorted(positions), f"{name}: positions not sorted"

def test_slot_positions_start_at_zero():
    for name in list_templates():
        t = get_template(name)
        assert t.slots[0].position == 0.0, f"{name}: first position != 0.0"

def test_full_library_template():
    t = get_template(TemplateName.FULL_LIBRARY)
    assert t.target_track_count == 0  # 0 = use all tracks
    assert t.breathe_interval == 7

def test_set_slot_is_frozen():
    slot = SetSlot(position=0.0, mood=TrackMood.DRIVING,
                   energy_target=-9.0, bpm_range=(126, 130),
                   duration_target_s=180, flexibility=0.5)
    assert slot.mood == TrackMood.DRIVING

def test_template_has_description():
    t = get_template(TemplateName.CLASSIC_60)
    assert len(t.description) > 10
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/utils/test_set_templates.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `app/utils/audio/set_templates.py`:

```python
"""Slot-based set templates for DJ curation.

Each template defines a sequence of slots with target mood, energy,
BPM range, and duration. The curation service uses these to select
tracks that match the desired set arc.

Pure computation — no DB or IO.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.utils.audio.mood_classifier import TrackMood

class TemplateName(StrEnum):
    """Available set template names."""

    WARM_UP_30 = "warm_up_30"
    CLASSIC_60 = "classic_60"
    PEAK_HOUR_60 = "peak_hour_60"
    ROLLER_90 = "roller_90"
    PROGRESSIVE_120 = "progressive_120"
    WAVE_120 = "wave_120"
    CLOSING_60 = "closing_60"
    FULL_LIBRARY = "full_library"

@dataclass(frozen=True, slots=True)
class SetSlot:
    """A single slot in a set template.

    Attributes:
        position: Normalised position in set [0.0, 1.0].
        mood: Required mood category for this slot.
        energy_target: Target LUFS for this slot (e.g. -10.0).
        bpm_range: Allowed BPM range (min, max).
        duration_target_s: Target track duration in seconds.
        flexibility: How strict constraints are [0.0=strict, 1.0=loose].
    """

    position: float
    mood: TrackMood
    energy_target: float
    bpm_range: tuple[float, float]
    duration_target_s: int
    flexibility: float

@dataclass(frozen=True, slots=True)
class SetTemplate:
    """Complete set template with metadata and slot sequence."""

    name: TemplateName
    description: str
    duration_minutes: int
    target_track_count: int  # 0 = use all tracks
    slots: tuple[SetSlot, ...]
    breathe_interval: int = 0  # 0 = no breathing constraint

def _classic_60() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.CLASSIC_60,
        description="Standard 60-min arc: warm-up -> build -> peak -> breathe -> peak -> cooldown",
        duration_minutes=60,
        target_track_count=20,
        slots=(
            SetSlot(0.00, TrackMood.AMBIENT_DUB, -12.0, (122, 126), 200, 0.7),
            SetSlot(0.05, TrackMood.AMBIENT_DUB, -11.5, (123, 127), 200, 0.6),
            SetSlot(0.10, TrackMood.MELODIC_DEEP, -10.5, (124, 128), 190, 0.5),
            SetSlot(0.15, TrackMood.MELODIC_DEEP, -10.0, (125, 129), 190, 0.5),
            SetSlot(0.22, TrackMood.DRIVING, -9.5, (126, 130), 180, 0.4),
            SetSlot(0.30, TrackMood.DRIVING, -9.0, (127, 131), 180, 0.4),
            SetSlot(0.38, TrackMood.DRIVING, -8.5, (127, 131), 180, 0.4),
            SetSlot(0.45, TrackMood.PEAK_TIME, -7.5, (128, 134), 180, 0.3),
            SetSlot(0.52, TrackMood.PEAK_TIME, -7.0, (129, 135), 180, 0.3),
            SetSlot(0.60, TrackMood.PEAK_TIME, -6.5, (130, 136), 180, 0.3),
            SetSlot(0.68, TrackMood.DRIVING, -9.0, (128, 132), 180, 0.5),  # breathe
            SetSlot(0.73, TrackMood.MELODIC_DEEP, -9.5, (127, 131), 190, 0.5),  # breathe
            SetSlot(0.78, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.83, TrackMood.PEAK_TIME, -7.0, (129, 135), 180, 0.3),
            SetSlot(0.87, TrackMood.PEAK_TIME, -6.5, (130, 136), 180, 0.3),
            SetSlot(0.90, TrackMood.PEAK_TIME, -7.0, (130, 136), 180, 0.3),
            SetSlot(0.93, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.4),
            SetSlot(0.96, TrackMood.MELODIC_DEEP, -10.0, (127, 131), 190, 0.5),
            SetSlot(0.98, TrackMood.MELODIC_DEEP, -10.5, (126, 130), 200, 0.6),
            SetSlot(1.00, TrackMood.AMBIENT_DUB, -11.5, (124, 128), 200, 0.7),
        ),
    )

def _warm_up_30() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.WARM_UP_30,
        description="30-min warm-up opener: ambient/melodic with gradual energy build",
        duration_minutes=30,
        target_track_count=9,
        slots=(
            SetSlot(0.00, TrackMood.AMBIENT_DUB, -13.0, (120, 126), 210, 0.7),
            SetSlot(0.12, TrackMood.AMBIENT_DUB, -12.0, (122, 127), 200, 0.6),
            SetSlot(0.25, TrackMood.MELODIC_DEEP, -11.0, (124, 128), 200, 0.5),
            SetSlot(0.37, TrackMood.MELODIC_DEEP, -10.5, (125, 129), 190, 0.5),
            SetSlot(0.50, TrackMood.MELODIC_DEEP, -10.0, (126, 130), 190, 0.4),
            SetSlot(0.62, TrackMood.DRIVING, -9.5, (126, 130), 180, 0.4),
            SetSlot(0.75, TrackMood.DRIVING, -9.0, (127, 131), 180, 0.4),
            SetSlot(0.87, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(1.00, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
        ),
    )

def _peak_hour_60() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.PEAK_HOUR_60,
        description="60-min peak hour: high energy throughout with minimal cooldown",
        duration_minutes=60,
        target_track_count=20,
        slots=(
            SetSlot(0.00, TrackMood.DRIVING, -9.0, (128, 132), 180, 0.4),
            SetSlot(0.05, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.4),
            SetSlot(0.10, TrackMood.PEAK_TIME, -7.5, (130, 135), 175, 0.3),
            SetSlot(0.16, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.22, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.28, TrackMood.INDUSTRIAL, -7.0, (132, 138), 170, 0.4),
            SetSlot(0.34, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.40, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.46, TrackMood.DRIVING, -8.0, (130, 134), 180, 0.4),  # breathe
            SetSlot(0.52, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.58, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.64, TrackMood.INDUSTRIAL, -6.5, (132, 138), 170, 0.4),
            SetSlot(0.70, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.76, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.82, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.87, TrackMood.DRIVING, -8.0, (129, 133), 180, 0.4),  # breathe
            SetSlot(0.90, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.93, TrackMood.PEAK_TIME, -7.5, (130, 135), 175, 0.3),
            SetSlot(0.96, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.4),
            SetSlot(1.00, TrackMood.DRIVING, -9.0, (128, 132), 180, 0.5),
        ),
    )

def _roller_90() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.ROLLER_90,
        description="90-min extended roller: quick ramp to high energy, 2 peaks with brief valley",
        duration_minutes=90,
        target_track_count=28,
        slots=(
            SetSlot(0.00, TrackMood.MELODIC_DEEP, -10.0, (125, 129), 190, 0.5),
            SetSlot(0.04, TrackMood.DRIVING, -9.0, (127, 131), 185, 0.4),
            SetSlot(0.08, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.12, TrackMood.PEAK_TIME, -7.5, (129, 134), 180, 0.3),
            SetSlot(0.16, TrackMood.PEAK_TIME, -7.0, (130, 135), 175, 0.3),
            SetSlot(0.20, TrackMood.PEAK_TIME, -6.5, (130, 136), 175, 0.3),
            SetSlot(0.25, TrackMood.PEAK_TIME, -6.5, (131, 136), 175, 0.3),
            SetSlot(0.30, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.35, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.40, TrackMood.INDUSTRIAL, -7.0, (132, 138), 170, 0.4),
            SetSlot(0.45, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.50, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.5),  # valley
            SetSlot(0.54, TrackMood.MELODIC_DEEP, -9.5, (128, 132), 190, 0.5),  # valley
            SetSlot(0.58, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.4),
            SetSlot(0.62, TrackMood.DRIVING, -8.0, (129, 134), 180, 0.4),
            SetSlot(0.66, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.70, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.74, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.78, TrackMood.INDUSTRIAL, -6.5, (132, 138), 170, 0.4),
            SetSlot(0.82, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.86, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.89, TrackMood.PEAK_TIME, -7.0, (130, 135), 175, 0.3),
            SetSlot(0.92, TrackMood.DRIVING, -8.0, (129, 133), 180, 0.4),
            SetSlot(0.94, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.96, TrackMood.DRIVING, -9.0, (128, 131), 185, 0.5),
            SetSlot(0.97, TrackMood.MELODIC_DEEP, -10.0, (127, 130), 190, 0.5),
            SetSlot(0.98, TrackMood.MELODIC_DEEP, -10.5, (126, 129), 195, 0.6),
            SetSlot(1.00, TrackMood.MELODIC_DEEP, -11.0, (125, 128), 200, 0.6),
        ),
    )

def _progressive_120() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.PROGRESSIVE_120,
        description="120-min slow build to single massive peak at ~80%, then gradual release",
        duration_minutes=120,
        target_track_count=38,
        slots=tuple(
            SetSlot(
                position=round(i / 37, 2),
                mood=_progressive_mood(i / 37),
                energy_target=_progressive_energy(i / 37),
                bpm_range=_progressive_bpm(i / 37),
                duration_target_s=190,
                flexibility=0.5 if i / 37 < 0.5 else 0.3,
            )
            for i in range(38)
        ),
    )

def _progressive_mood(pos: float) -> TrackMood:
    if pos < 0.15:
        return TrackMood.AMBIENT_DUB
    if pos < 0.30:
        return TrackMood.MELODIC_DEEP
    if pos < 0.55:
        return TrackMood.DRIVING
    if pos < 0.85:
        return TrackMood.PEAK_TIME
    if pos < 0.92:
        return TrackMood.DRIVING
    return TrackMood.MELODIC_DEEP

def _progressive_energy(pos: float) -> float:
    if pos < 0.80:
        return -13.0 + pos / 0.80 * 7.0  # -13 → -6
    return -6.0 - (pos - 0.80) / 0.20 * 5.0  # -6 → -11

def _progressive_bpm(pos: float) -> tuple[float, float]:
    base = 122.0 + pos * 14.0  # 122 → 136
    return (base - 2, base + 2)

def _wave_120() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.WAVE_120,
        description="120-min oscillating energy: 3 peaks of increasing intensity with valleys",
        duration_minutes=120,
        target_track_count=38,
        slots=tuple(
            SetSlot(
                position=round(i / 37, 2),
                mood=_wave_mood(i / 37),
                energy_target=_wave_energy(i / 37),
                bpm_range=_wave_bpm(i / 37),
                duration_target_s=190,
                flexibility=0.5,
            )
            for i in range(38)
        ),
    )

def _wave_mood(pos: float) -> TrackMood:
    import math

    wave = math.sin(pos * math.pi * 3)  # 3 cycles
    amp = pos * 0.5 + 0.3  # increasing amplitude
    val = 0.5 + wave * amp
    if val < 0.25:
        return TrackMood.MELODIC_DEEP
    if val < 0.45:
        return TrackMood.DRIVING
    if val < 0.7:
        return TrackMood.PEAK_TIME
    return TrackMood.INDUSTRIAL

def _wave_energy(pos: float) -> float:
    import math

    wave = math.sin(pos * math.pi * 3)
    amp = pos * 0.5 + 0.3
    base = -10.0 + pos * 2.0  # slight upward trend
    return max(-14.0, min(-6.0, base + wave * amp * 4.0))

def _wave_bpm(pos: float) -> tuple[float, float]:
    base = 126.0 + pos * 8.0
    return (base - 3, base + 3)

def _closing_60() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.CLOSING_60,
        description="60-min closing: peak start, gradual cooldown to ambient close",
        duration_minutes=60,
        target_track_count=20,
        slots=(
            SetSlot(0.00, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.05, TrackMood.PEAK_TIME, -7.0, (130, 135), 175, 0.3),
            SetSlot(0.10, TrackMood.PEAK_TIME, -7.5, (129, 134), 180, 0.3),
            SetSlot(0.16, TrackMood.DRIVING, -8.0, (129, 133), 180, 0.4),
            SetSlot(0.22, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.28, TrackMood.PEAK_TIME, -7.5, (129, 134), 180, 0.3),  # mini peak
            SetSlot(0.34, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.40, TrackMood.DRIVING, -9.0, (127, 131), 185, 0.4),
            SetSlot(0.46, TrackMood.MELODIC_DEEP, -9.5, (127, 131), 190, 0.5),
            SetSlot(0.52, TrackMood.DRIVING, -9.0, (127, 131), 185, 0.4),
            SetSlot(0.58, TrackMood.MELODIC_DEEP, -10.0, (126, 130), 190, 0.5),
            SetSlot(0.64, TrackMood.MELODIC_DEEP, -10.0, (126, 130), 190, 0.5),
            SetSlot(0.70, TrackMood.MELODIC_DEEP, -10.5, (125, 129), 195, 0.5),
            SetSlot(0.76, TrackMood.MELODIC_DEEP, -10.5, (125, 129), 195, 0.6),
            SetSlot(0.82, TrackMood.AMBIENT_DUB, -11.0, (124, 128), 200, 0.6),
            SetSlot(0.87, TrackMood.AMBIENT_DUB, -11.5, (123, 127), 200, 0.7),
            SetSlot(0.90, TrackMood.AMBIENT_DUB, -12.0, (122, 126), 210, 0.7),
            SetSlot(0.93, TrackMood.AMBIENT_DUB, -12.5, (121, 125), 210, 0.8),
            SetSlot(0.96, TrackMood.AMBIENT_DUB, -13.0, (120, 125), 220, 0.8),
            SetSlot(1.00, TrackMood.AMBIENT_DUB, -13.5, (118, 124), 230, 0.8),
        ),
    )

def _full_library() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.FULL_LIBRARY,
        description="Order entire library with breathing moments every 7 tracks",
        duration_minutes=0,
        target_track_count=0,  # 0 = use all tracks
        slots=(),  # Empty — GA generates slots dynamically
        breathe_interval=7,
    )

_TEMPLATES: dict[TemplateName, SetTemplate] = {}

def _init_templates() -> None:
    global _TEMPLATES  # noqa: PLW0603
    _TEMPLATES = {
        TemplateName.WARM_UP_30: _warm_up_30(),
        TemplateName.CLASSIC_60: _classic_60(),
        TemplateName.PEAK_HOUR_60: _peak_hour_60(),
        TemplateName.ROLLER_90: _roller_90(),
        TemplateName.PROGRESSIVE_120: _progressive_120(),
        TemplateName.WAVE_120: _wave_120(),
        TemplateName.CLOSING_60: _closing_60(),
        TemplateName.FULL_LIBRARY: _full_library(),
    }

_init_templates()

def list_templates() -> list[TemplateName]:
    """Return all available template names."""
    return list(_TEMPLATES.keys())

def get_template(name: TemplateName) -> SetTemplate:
    """Get a template by name.

    Raises:
        KeyError: If template name not found.
    """
    return _TEMPLATES[name]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/utils/test_set_templates.py -v`
Expected: All PASS

**Step 5: Lint and commit**

```bash
uv run ruff check app/utils/audio/set_templates.py tests/utils/test_set_templates.py
uv run ruff format --check app/utils/audio/set_templates.py tests/utils/test_set_templates.py
git add app/utils/audio/set_templates.py tests/utils/test_set_templates.py
git commit -m "feat: add slot-based set templates (8 templates)"
```

---

## Task 3: Curation Service — Smart Track Selection

**Files:**
- Create: `app/services/set_curation.py`
- Create: `app/schemas/set_curation.py`
- Test: `tests/services/test_set_curation.py`

**Step 1: Write Pydantic schemas**

Create `app/schemas/set_curation.py`:

```python
"""Schemas for set curation."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema

class CurateRequest(BaseSchema):
    playlist_id: int
    template: str = Field(default="classic_60", description="Template name")
    target_count: int | None = Field(default=None, description="Override track count")
    exclude_track_ids: list[int] = Field(default_factory=list)

class CurateCandidate(BaseSchema):
    track_id: int
    title: str
    artist: str
    mood: str
    slot_score: float
    bpm: float
    lufs_i: float
    key: str | None = None

class CurateResult(BaseSchema):
    template: str
    target_count: int
    candidates: list[CurateCandidate]
    mood_distribution: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
```

**Step 2: Write the failing tests**

Create `tests/services/test_set_curation.py`:

```python
"""Tests for set curation service."""

from unittest.mock import MagicMock

import pytest

from app.services.set_curation import SetCurationService
from app.utils.audio.mood_classifier import TrackMood

def _make_mock_feature(
    track_id: int,
    bpm: float = 130.0,
    lufs_i: float = -9.0,
    kick_prominence: float = 0.5,
    centroid_mean_hz: float = 2500.0,
    onset_rate_mean: float = 5.0,
    hp_ratio: float = 0.5,
    key_code: int = 4,
) -> MagicMock:
    feat = MagicMock()
    feat.track_id = track_id
    feat.bpm = bpm
    feat.lufs_i = lufs_i
    feat.kick_prominence = kick_prominence
    feat.centroid_mean_hz = centroid_mean_hz
    feat.onset_rate_mean = onset_rate_mean
    feat.hp_ratio = hp_ratio
    feat.key_code = key_code
    feat.key_confidence = 0.8
    feat.chroma_entropy = 0.5
    return feat

def test_classify_features_list():
    features = [
        _make_mock_feature(1, bpm=122, lufs_i=-13),  # ambient
        _make_mock_feature(2, bpm=130, lufs_i=-7, kick_prominence=0.8),  # peak
        _make_mock_feature(3, bpm=130, lufs_i=-9),  # driving
    ]
    svc = SetCurationService()
    classified = svc.classify_features(features)
    assert classified[1] == TrackMood.AMBIENT_DUB
    assert classified[2] == TrackMood.PEAK_TIME
    assert classified[3] == TrackMood.DRIVING

def test_mood_distribution():
    features = [
        _make_mock_feature(i, bpm=130, lufs_i=-9)
        for i in range(10)
    ]
    svc = SetCurationService()
    classified = svc.classify_features(features)
    dist = svc.mood_distribution(classified)
    assert sum(dist.values()) == 10

def test_select_candidates_returns_correct_count():
    # Create diverse features
    features = []
    for i in range(50):
        bpm = 122.0 + i * 0.5
        lufs = -13.0 + i * 0.15
        features.append(_make_mock_feature(
            i, bpm=bpm, lufs_i=lufs,
            kick_prominence=0.3 + i * 0.01,
            centroid_mean_hz=1500 + i * 50,
            onset_rate_mean=3.0 + i * 0.1,
            hp_ratio=0.7 - i * 0.01,
        ))
    svc = SetCurationService()
    candidates = svc.select_candidates(features, template_name="classic_60")
    # CLASSIC_60 has 20 slots
    assert len(candidates) <= 20
    assert len(candidates) >= 10  # at least half filled

def test_select_candidates_no_duplicates():
    features = [
        _make_mock_feature(i, bpm=125 + i % 5, lufs_i=-10 + i % 3)
        for i in range(40)
    ]
    svc = SetCurationService()
    candidates = svc.select_candidates(features, template_name="classic_60")
    track_ids = [c.track_id for c in candidates]
    assert len(track_ids) == len(set(track_ids))

def test_select_candidates_respects_exclude():
    features = [_make_mock_feature(i, bpm=130, lufs_i=-9) for i in range(30)]
    svc = SetCurationService()
    excluded = {0, 1, 2, 3, 4}
    candidates = svc.select_candidates(
        features, template_name="classic_60", exclude_ids=excluded
    )
    for c in candidates:
        assert c.track_id not in excluded
```

**Step 3: Write the service implementation**

Create `app/services/set_curation.py`:

```python
"""Set curation service — classify tracks and select by template slots.

Orchestrates mood classification and greedy slot-based selection.
No DB dependency — works with feature objects passed in.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.audio.mood_classifier import MoodClassification, TrackMood, classify_track
from app.utils.audio.set_templates import SetSlot, TemplateName, get_template

@dataclass(frozen=True, slots=True)
class CandidateTrack:
    """A track selected for a set with slot scoring metadata."""

    track_id: int
    mood: TrackMood
    slot_score: float
    bpm: float
    lufs_i: float
    key_code: int

class SetCurationService:
    """Classify tracks by mood and select candidates for set templates."""

    def classify_features(
        self,
        features: list[object],
    ) -> dict[int, TrackMood]:
        """Classify a list of ORM feature objects by mood.

        Args:
            features: List of TrackAudioFeaturesComputed-like objects.

        Returns:
            Mapping of track_id → TrackMood.
        """
        result: dict[int, TrackMood] = {}
        for feat in features:
            classification = classify_track(
                bpm=feat.bpm,  # type: ignore[union-attr]
                lufs_i=feat.lufs_i,  # type: ignore[union-attr]
                kick_prominence=feat.kick_prominence or 0.5,  # type: ignore[union-attr]
                spectral_centroid_mean=feat.centroid_mean_hz or 2500.0,  # type: ignore[union-attr]
                onset_rate=feat.onset_rate_mean or 5.0,  # type: ignore[union-attr]
                hp_ratio=feat.hp_ratio or 0.5,  # type: ignore[union-attr]
            )
            result[feat.track_id] = classification.mood  # type: ignore[union-attr]
        return result

    def mood_distribution(
        self,
        classified: dict[int, TrackMood],
    ) -> dict[TrackMood, int]:
        """Count tracks per mood category."""
        dist: dict[TrackMood, int] = {m: 0 for m in TrackMood}
        for mood in classified.values():
            dist[mood] += 1
        return dist

    def select_candidates(
        self,
        features: list[object],
        template_name: str,
        exclude_ids: set[int] | None = None,
        target_count: int | None = None,
    ) -> list[CandidateTrack]:
        """Select tracks for a template using greedy slot matching.

        Args:
            features: ORM feature objects with audio attributes.
            template_name: Template name string (e.g. "classic_60").
            exclude_ids: Track IDs to exclude from selection.
            target_count: Override template's target count.

        Returns:
            Ordered list of CandidateTrack.
        """
        template = get_template(TemplateName(template_name))
        excluded = exclude_ids or set()

        # Classify all tracks
        classified = self.classify_features(features)

        # Build feature lookup
        feat_map: dict[int, object] = {f.track_id: f for f in features}  # type: ignore[union-attr]

        # Use template slots or generate simple slots for full library
        slots = template.slots
        if not slots:
            # FULL_LIBRARY: no slots, return all tracks sorted by mood intensity
            candidates = []
            for feat in features:
                tid = feat.track_id  # type: ignore[union-attr]
                if tid in excluded:
                    continue
                mood = classified.get(tid, TrackMood.DRIVING)
                candidates.append(CandidateTrack(
                    track_id=tid,
                    mood=mood,
                    slot_score=0.5,
                    bpm=feat.bpm,  # type: ignore[union-attr]
                    lufs_i=feat.lufs_i,  # type: ignore[union-attr]
                    key_code=feat.key_code or 0,  # type: ignore[union-attr]
                ))
            candidates.sort(key=lambda c: c.mood.intensity)
            return candidates

        # Greedy slot filling
        used_ids: set[int] = set()
        selected: list[CandidateTrack] = []

        for slot in slots:
            best_score = -1.0
            best_tid: int | None = None

            for feat in features:
                tid = feat.track_id  # type: ignore[union-attr]
                if tid in used_ids or tid in excluded:
                    continue

                score = self._score_candidate_for_slot(
                    feat, slot, classified.get(tid, TrackMood.DRIVING),
                    used_ids, classified,
                )
                if score > best_score:
                    best_score = score
                    best_tid = tid

            if best_tid is not None:
                feat_obj = feat_map[best_tid]
                mood = classified.get(best_tid, TrackMood.DRIVING)
                selected.append(CandidateTrack(
                    track_id=best_tid,
                    mood=mood,
                    slot_score=best_score,
                    bpm=feat_obj.bpm,  # type: ignore[union-attr]
                    lufs_i=feat_obj.lufs_i,  # type: ignore[union-attr]
                    key_code=feat_obj.key_code or 0,  # type: ignore[union-attr]
                ))
                used_ids.add(best_tid)

        return selected

    def _score_candidate_for_slot(
        self,
        feat: object,
        slot: SetSlot,
        track_mood: TrackMood,
        used_ids: set[int],
        classified: dict[int, TrackMood],
    ) -> float:
        """Score a single track against a slot.

        Components:
        - Mood match (40%): exact=1.0, adjacent=0.5, other=0.0
        - Energy fit (30%): closeness of LUFS to target
        - BPM fit (20%): whether BPM falls in slot range
        - Variety (10%): bonus for diverse selection
        """
        bpm = feat.bpm  # type: ignore[union-attr]
        lufs = feat.lufs_i  # type: ignore[union-attr]

        # Mood match
        if track_mood == slot.mood:
            mood_score = 1.0
        elif abs(track_mood.intensity - slot.mood.intensity) == 1:
            mood_score = 0.5
        else:
            mood_score = 0.0

        # Energy fit
        energy_diff = abs(lufs - slot.energy_target)
        energy_score = max(0.0, 1.0 - energy_diff / 8.0)

        # BPM fit
        bpm_low, bpm_high = slot.bpm_range
        if bpm_low <= bpm <= bpm_high:
            bpm_score = 1.0
        else:
            bpm_dist = min(abs(bpm - bpm_low), abs(bpm - bpm_high))
            bpm_score = max(0.0, 1.0 - bpm_dist / 10.0)

        # Flexibility adjustment
        mood_weight = 0.40 * (1.0 - slot.flexibility * 0.3)
        energy_weight = 0.30
        bpm_weight = 0.20
        variety_weight = 0.10

        return (
            mood_weight * mood_score
            + energy_weight * energy_score
            + bpm_weight * bpm_score
            + variety_weight * 0.5  # baseline variety
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_set_curation.py -v`
Expected: All PASS

**Step 5: Lint and commit**

```bash
uv run ruff check app/services/set_curation.py app/schemas/set_curation.py tests/services/test_set_curation.py
uv run ruff format --check app/services/set_curation.py app/schemas/set_curation.py tests/services/test_set_curation.py
git add app/services/set_curation.py app/schemas/set_curation.py tests/services/test_set_curation.py
git commit -m "feat: add set curation service with greedy slot selection"
```

---

## Task 4: Improved GA — LUFS Energy + Variety Penalty

**Files:**
- Modify: `app/utils/audio/set_generator.py` (GAConfig, TrackData, fitness function)
- Modify: `tests/utils/test_set_generator.py`

**Step 1: Write failing tests for new GA features**

Append to `tests/utils/test_set_generator.py`:

```python
def test_variety_penalty_same_mood_triple():
    """3 consecutive tracks with same mood should be penalized."""
    from app.utils.audio.set_generator import variety_score

    # All mood=3 (DRIVING)
    tracks = [
        TrackData(track_id=i, bpm=130.0, energy=0.5, key_code=i % 12,
                  mood=3, artist_id=i)
        for i in range(5)
    ]
    score = variety_score(tracks)
    assert score < 1.0  # penalized

def test_variety_penalty_diverse_mood():
    """Diverse moods should not be penalized."""
    from app.utils.audio.set_generator import variety_score

    tracks = [
        TrackData(track_id=i, bpm=130.0, energy=0.5, key_code=i % 12,
                  mood=i % 6 + 1, artist_id=i)
        for i in range(6)
    ]
    score = variety_score(tracks)
    assert score >= 0.9

def test_ga_config_has_variety_weight():
    config = GAConfig()
    assert hasattr(config, "w_variety")
    assert config.w_variety == 0.20

def test_track_data_has_mood_and_artist():
    td = TrackData(track_id=1, bpm=130.0, energy=0.5, key_code=4,
                   mood=3, artist_id=42)
    assert td.mood == 3
    assert td.artist_id == 42

def test_lufs_energy_used_in_arc():
    """When lufs is provided, energy should be derived from LUFS, not energy_mean."""
    from app.utils.audio.set_generator import lufs_to_energy

    assert 0.0 <= lufs_to_energy(-14.0) <= 0.05  # ambient → low energy
    assert 0.9 <= lufs_to_energy(-6.0) <= 1.0  # hard → high energy
    assert 0.4 <= lufs_to_energy(-10.0) <= 0.6  # mid-range
```

**Step 2: Run to verify they fail**

Run: `uv run pytest tests/utils/test_set_generator.py -v -k "variety or lufs or mood_and_artist or variety_weight"`
Expected: FAIL

**Step 3: Modify `app/utils/audio/set_generator.py`**

Add to `TrackData`:
```python
@dataclass(frozen=True, slots=True)
class TrackData:
    """Lightweight track representation for the GA."""

    track_id: int
    bpm: float
    energy: float  # 0-1, global energy proxy (LUFS-mapped or energy_mean)
    key_code: int
    mood: int = 0  # TrackMood.intensity (1-6), 0 = unclassified
    artist_id: int = 0  # for variety scoring
```

Add to `GAConfig`:
```python
    w_transition: float = 0.40   # was 0.50
    w_energy_arc: float = 0.25   # was 0.30
    w_bpm_smooth: float = 0.15   # was 0.20
    w_variety: float = 0.20      # NEW
```

Add free function:
```python
def lufs_to_energy(lufs: float) -> float:
    """Map LUFS to [0, 1] energy range.

    Techno range: -14 LUFS (ambient) to -6 LUFS (hard).
    """
    return max(0.0, min(1.0, (lufs - (-14.0)) / ((-6.0) - (-14.0))))

def variety_score(tracks: list[TrackData]) -> float:
    """Score sequence diversity (1.0 = perfect variety, 0.0 = no variety).

    Penalises:
    - Same mood for 3+ consecutive tracks (0.3 per occurrence)
    - Same Camelot key for 3+ consecutive (0.2 per occurrence)
    - Same artist within 5-track window (0.1 per occurrence)
    """
    n = len(tracks)
    if n < 3:
        return 1.0

    penalties = 0.0
    for i in range(2, n):
        # Same mood triple
        if tracks[i].mood == tracks[i - 1].mood == tracks[i - 2].mood and tracks[i].mood != 0:
            penalties += 0.3
        # Same key triple
        if tracks[i].key_code == tracks[i - 1].key_code == tracks[i - 2].key_code:
            penalties += 0.2

    for i in range(1, n):
        # Same artist in 5-track window
        if tracks[i].artist_id != 0:
            window = tracks[max(0, i - 4) : i]
            if any(t.artist_id == tracks[i].artist_id for t in window):
                penalties += 0.1

    return max(0.0, 1.0 - penalties / n)
```

Update `_fitness()`:
```python
    def _fitness(self, chromosome: NDArray[np.int32]) -> float:
        """Evaluate fitness of a chromosome (higher = better)."""
        cfg = self.config
        transition = self._mean_transition_quality(chromosome)
        arc = self._energy_arc_score(chromosome)
        bpm = self._bpm_smoothness_score(chromosome)
        var = self._variety_score(chromosome)
        return (
            cfg.w_transition * transition
            + cfg.w_energy_arc * arc
            + cfg.w_bpm_smooth * bpm
            + cfg.w_variety * var
        )

    def _variety_score(self, chromosome: NDArray[np.int32]) -> float:
        """Wrapper for variety_score using chromosome track data."""
        tracks = [self._all_tracks[i] for i in chromosome]
        return variety_score(tracks)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/utils/test_set_generator.py -v`
Expected: All PASS

**Step 5: Run full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: All PASS (new weights are backward-compatible — old default tests use explicit weights)

**Step 6: Lint and commit**

```bash
uv run ruff check app/utils/audio/set_generator.py tests/utils/test_set_generator.py
uv run ruff format --check app/utils/audio/set_generator.py tests/utils/test_set_generator.py
git add app/utils/audio/set_generator.py tests/utils/test_set_generator.py
git commit -m "feat: add variety penalty and LUFS energy mapping to GA"
```

---

## Task 5: Wire LUFS Energy in SetGenerationService

**Files:**
- Modify: `app/services/set_generation.py:127-135` — replace `energy_mean` with `lufs_to_energy(lufs_i)`

**Step 1: Write the failing test**

Add to existing test file or create `tests/services/test_set_generation_lufs.py`:

```python
"""Test LUFS-based energy in set generation."""

from app.utils.audio.set_generator import TrackData, lufs_to_energy

def test_track_data_uses_lufs_energy():
    """Verify TrackData energy should come from LUFS, not energy_mean."""
    # Simulate what set_generation.py should do
    lufs_i = -8.0
    energy = lufs_to_energy(lufs_i)
    track = TrackData(track_id=1, bpm=130.0, energy=energy, key_code=4)
    assert 0.7 <= track.energy <= 0.8  # -8 LUFS → ~0.75 energy
```

**Step 2: Modify `app/services/set_generation.py:127-135`**

Change:
```python
        # Build TrackData list (using energy_mean as proxy for global_energy)
        tracks = [
            TrackData(
                track_id=f.track_id,
                bpm=f.bpm,
                energy=f.energy_mean or 0.5,
                key_code=f.key_code or 0,
            )
            for f in features_list
        ]
```

To:
```python
        from app.utils.audio.set_generator import lufs_to_energy

        # Build TrackData list (LUFS-based energy for accurate perceived loudness)
        tracks = [
            TrackData(
                track_id=f.track_id,
                bpm=f.bpm,
                energy=lufs_to_energy(f.lufs_i),
                key_code=f.key_code or 0,
                mood=0,  # populated by curation service when available
                artist_id=0,  # TODO: wire artist_id from track model
            )
            for f in features_list
        ]
```

**Step 3: Run tests**

Run: `uv run pytest tests/ -v -k "set_generation or set_generator"`
Expected: All PASS

**Step 4: Commit**

```bash
git add app/services/set_generation.py tests/services/test_set_generation_lufs.py
git commit -m "fix: switch GA energy from energy_mean to LUFS-based mapping"
```

---

## Task 6: Fix MCP Bugs — score_transitions Title + search_by_criteria Title

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py:186-192` — fix title display
- Modify: `app/mcp/workflows/discovery_tools.py:241-245` — fix empty titles

**Step 1: Fix score_transitions in `setbuilder_tools.py`**

Lines 188-192, change:
```python
                    from_title=from_key or "",
                    to_title=to_key or "",
```

To:
```python
                    from_title=from_item.title if hasattr(from_item, 'title') else f"Track {from_item.track_id}",
                    to_title=to_item.title if hasattr(to_item, 'title') else f"Track {to_item.track_id}",
```

Wait — the items are `DjSetItemRead` which may not have track title. We need to load the track. Let's look at what data is available.

Actually, the items from `set_svc.list_items()` return `DjSetItemRead` with `track_id` but not `title`. We need to load track info. Minimal fix: add a track title lookup.

Modify `score_transitions` to load track titles via features service (which already has the session):

After line 110 (after getting items), add:
```python
        # Build track title lookup
        from app.repositories.tracks import TrackRepository

        track_repo = TrackRepository(features_svc.features_repo.session)
        track_ids = [item.track_id for item in items]
        title_map: dict[int, str] = {}
        for tid in track_ids:
            track = await track_repo.get_by_id(tid)
            if track:
                title_map[tid] = track.title or f"Track {tid}"
            else:
                title_map[tid] = f"Track {tid}"
```

Then line 188-192:
```python
                    from_title=title_map.get(from_item.track_id, f"Track {from_item.track_id}"),
                    to_title=title_map.get(to_item.track_id, f"Track {to_item.track_id}"),
```

**Step 2: Fix search_by_criteria in `discovery_tools.py`**

Lines 241-245: the title/artists are hardcoded empty. Need track lookup.

After line 214, add track repo:
```python
        from app.repositories.tracks import TrackRepository

        track_repo = TrackRepository(features_svc.features_repo.session)
```

Change line 241-246:
```python
            track = await track_repo.get_by_id(feat.track_id)
            track_title = track.title if track else f"Track {feat.track_id}"
            track_artists = ""
            if track and track.artists:
                track_artists = ", ".join(a.name for a in track.artists)

            results.append(
                TrackDetails(
                    track_id=feat.track_id,
                    title=track_title,
                    artists=track_artists,
                    duration_ms=track.duration_ms if track else None,
                    bpm=feat.bpm,
                    key=camelot,
                    energy_lufs=feat.lufs_i,
                    has_features=True,
                )
            )
```

**Step 3: Lint and run existing MCP tests**

Run: `uv run pytest tests/mcp/ -v`
Expected: All PASS (metadata tests don't invoke tools with DB)

**Step 4: Commit**

```bash
git add app/mcp/workflows/setbuilder_tools.py app/mcp/workflows/discovery_tools.py
git commit -m "fix: show track titles in score_transitions and search_by_criteria"
```

---

## Task 7: New MCP Curation Tools

**Files:**
- Create: `app/mcp/workflows/curation_tools.py`
- Create: `app/mcp/types_curation.py`
- Modify: `app/mcp/workflows/server.py` — register curation tools
- Modify: `app/mcp/dependencies.py` — add curation DI provider
- Test: `tests/mcp/test_curation_tools.py`

**Step 1: Create MCP output types**

Create `app/mcp/types_curation.py`:

```python
"""Pydantic models for curation MCP tool structured output."""

from __future__ import annotations

from pydantic import BaseModel

class MoodDistribution(BaseModel):
    """Distribution of tracks across mood categories."""

    mood: str
    count: int
    percentage: float

class ClassifyResult(BaseModel):
    """Result of classifying tracks by mood."""

    total_classified: int
    distribution: list[MoodDistribution]

class CurateCandidate(BaseModel):
    """A candidate track selected for a set."""

    track_id: int
    mood: str
    slot_score: float
    bpm: float
    lufs_i: float

class CurateSetResult(BaseModel):
    """Result of curating tracks for a set template."""

    template: str
    target_count: int
    selected_count: int
    candidates: list[CurateCandidate]
    mood_distribution: list[MoodDistribution]
    warnings: list[str]

class WeakTransition(BaseModel):
    """A weak transition identified during review."""

    position: int
    from_track_id: int
    to_track_id: int
    score: float
    reason: str

class SetReviewResult(BaseModel):
    """Result of reviewing a set version."""

    overall_score: float
    energy_arc_adherence: float
    variety_score: float
    weak_transitions: list[WeakTransition]
    suggestions: list[str]

class GapDescription(BaseModel):
    """Description of a library gap."""

    mood: str
    needed: int
    available: int
    deficit: int

class LibraryGapResult(BaseModel):
    """Result of analyzing library gaps."""

    total_tracks: int
    tracks_with_features: int
    mood_distribution: list[MoodDistribution]
    gaps: list[GapDescription]
    recommendations: list[str]
```

**Step 2: Create curation tools module**

Create `app/mcp/workflows/curation_tools.py`:

```python
"""Curation tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.mcp.dependencies import get_features_service
from app.mcp.types_curation import (
    ClassifyResult,
    CurateCandidate,
    CurateSetResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
    SetReviewResult,
    WeakTransition,
)
from app.services.features import AudioFeaturesService
from app.services.set_curation import SetCurationService
from app.utils.audio.mood_classifier import TrackMood
from app.utils.audio.set_templates import TemplateName, get_template, list_templates

def register_curation_tools(mcp: FastMCP) -> None:
    """Register curation tools on the MCP server."""

    @mcp.tool(annotations={"readOnlyHint": True}, tags={"curation"})
    async def classify_tracks(
        ctx: Context,
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> ClassifyResult:
        """Classify all analyzed tracks into 6 mood categories.

        Uses rule-based classifier on audio features (BPM, LUFS,
        kick prominence, spectral centroid, onset rate, HP ratio).

        Returns mood distribution across all tracks with features.
        """
        all_features = await features_svc.list_all()
        svc = SetCurationService()
        classified = svc.classify_features(all_features)
        dist = svc.mood_distribution(classified)

        total = sum(dist.values())
        distribution = [
            MoodDistribution(
                mood=mood.value,
                count=count,
                percentage=round(count / total * 100, 1) if total > 0 else 0.0,
            )
            for mood, count in sorted(dist.items(), key=lambda x: x[0].intensity)
        ]

        return ClassifyResult(
            total_classified=total,
            distribution=distribution,
        )

    @mcp.tool(tags={"curation"})
    async def curate_set(
        template: str,
        ctx: Context,
        playlist_id: int | None = None,
        target_count: int | None = None,
        exclude_track_ids: list[int] | None = None,
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> CurateSetResult:
        """Select tracks for a set template using mood-based slot matching.

        Available templates: warm_up_30, classic_60, peak_hour_60,
        roller_90, progressive_120, wave_120, closing_60, full_library.

        Args:
            template: Template name (e.g. "classic_60").
            playlist_id: Optional playlist to filter tracks from.
            target_count: Override template's default track count.
            exclude_track_ids: Track IDs to exclude from selection.
        """
        await ctx.report_progress(progress=0, total=100)

        # Load features
        all_features = await features_svc.list_all()
        if playlist_id is not None:
            # Filter by playlist (need playlist items)
            from app.mcp.dependencies import get_playlist_service
            # Note: simplified — in real impl, inject via Depends
            pass  # For now, use all features

        svc = SetCurationService()
        exclude = set(exclude_track_ids or [])

        await ctx.report_progress(progress=30, total=100)

        candidates = svc.select_candidates(
            all_features,
            template_name=template,
            exclude_ids=exclude,
            target_count=target_count,
        )

        await ctx.report_progress(progress=80, total=100)

        classified = svc.classify_features(all_features)
        dist = svc.mood_distribution(classified)
        total = sum(dist.values())

        distribution = [
            MoodDistribution(
                mood=mood.value,
                count=count,
                percentage=round(count / total * 100, 1) if total > 0 else 0.0,
            )
            for mood, count in sorted(dist.items(), key=lambda x: x[0].intensity)
        ]

        tmpl = get_template(TemplateName(template))
        warnings: list[str] = []
        if len(candidates) < len(tmpl.slots):
            warnings.append(
                f"Only {len(candidates)} tracks matched, "
                f"template needs {len(tmpl.slots)} slots"
            )

        await ctx.report_progress(progress=100, total=100)

        return CurateSetResult(
            template=template,
            target_count=tmpl.target_track_count,
            selected_count=len(candidates),
            candidates=[
                CurateCandidate(
                    track_id=c.track_id,
                    mood=c.mood.value,
                    slot_score=round(c.slot_score, 3),
                    bpm=c.bpm,
                    lufs_i=c.lufs_i,
                )
                for c in candidates
            ],
            mood_distribution=distribution,
            warnings=warnings,
        )

    @mcp.tool(annotations={"readOnlyHint": True}, tags={"curation"})
    async def analyze_library_gaps(
        ctx: Context,
        template: str = "classic_60",
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> LibraryGapResult:
        """Analyze library for gaps relative to a set template.

        Compares current mood distribution with what the template needs.
        Returns deficit per mood category and recommendations.

        Args:
            template: Template to compare against (default: classic_60).
        """
        all_features = await features_svc.list_all()
        svc = SetCurationService()
        classified = svc.classify_features(all_features)
        dist = svc.mood_distribution(classified)
        total = sum(dist.values())

        tmpl = get_template(TemplateName(template))

        # Count required per mood from template slots
        needed: dict[TrackMood, int] = {m: 0 for m in TrackMood}
        for slot in tmpl.slots:
            needed[slot.mood] += 1

        gaps: list[GapDescription] = []
        recommendations: list[str] = []
        for mood in TrackMood.energy_order():
            avail = dist.get(mood, 0)
            need = needed.get(mood, 0)
            if need > avail:
                deficit = need - avail
                gaps.append(GapDescription(
                    mood=mood.value,
                    needed=need,
                    available=avail,
                    deficit=deficit,
                ))
                recommendations.append(
                    f"Add {deficit} {mood.value} tracks "
                    f"(need {need}, have {avail})"
                )

        distribution = [
            MoodDistribution(
                mood=mood.value,
                count=dist.get(mood, 0),
                percentage=round(dist.get(mood, 0) / total * 100, 1) if total > 0 else 0.0,
            )
            for mood in TrackMood.energy_order()
        ]

        return LibraryGapResult(
            total_tracks=len(all_features),
            tracks_with_features=total,
            mood_distribution=distribution,
            gaps=gaps,
            recommendations=recommendations,
        )
```

**Step 3: Update `app/mcp/workflows/server.py`**

Add import and registration:
```python
from app.mcp.workflows.curation_tools import register_curation_tools

# In create_workflow_mcp():
    register_curation_tools(mcp)
```

**Step 4: Write MCP metadata tests**

Create `tests/mcp/test_curation_tools.py`:

```python
"""Tests for curation MCP tool registration."""

from fastmcp import FastMCP

async def test_curation_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "classify_tracks" in tool_names
    assert "curate_set" in tool_names
    assert "analyze_library_gaps" in tool_names

async def test_curation_tools_tagged(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in ("classify_tracks", "curate_set", "analyze_library_gaps"):
            assert "curation" in tool.tags

async def test_classify_tracks_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name == "classify_tracks":
            assert tool.annotations.readOnlyHint is True

async def test_analyze_library_gaps_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name == "analyze_library_gaps":
            assert tool.annotations.readOnlyHint is True
```

**Step 5: Run tests**

Run: `uv run pytest tests/mcp/test_curation_tools.py -v`
Expected: All PASS

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

**Step 7: Lint and commit**

```bash
uv run ruff check app/mcp/workflows/curation_tools.py app/mcp/types_curation.py app/mcp/workflows/server.py tests/mcp/test_curation_tools.py
uv run ruff format --check app/mcp/workflows/curation_tools.py app/mcp/types_curation.py app/mcp/workflows/server.py tests/mcp/test_curation_tools.py
git add app/mcp/workflows/curation_tools.py app/mcp/types_curation.py app/mcp/workflows/server.py tests/mcp/test_curation_tools.py
git commit -m "feat: add curation MCP tools (classify, curate, gap analysis)"
```

---

## Task 8: Review Set MCP Tool

**Files:**
- Modify: `app/mcp/workflows/curation_tools.py` — add `review_set` tool
- Modify: `tests/mcp/test_curation_tools.py` — add registration test

**Step 1: Add `review_set` to `curation_tools.py`**

Inside `register_curation_tools`:

```python
    @mcp.tool(annotations={"readOnlyHint": True}, tags={"curation", "setbuilder"})
    async def review_set(
        set_id: int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> SetReviewResult:
        """Review a DJ set version — identify weak spots and suggest improvements.

        Analyses transitions, energy arc, and mood variety. Returns
        weak transitions (score < 0.4), energy plateaus, and suggestions.

        Args:
            set_id: DJ set ID.
            version_id: Set version to review.
        """
        from app.services.transition_scoring_unified import UnifiedTransitionScoringService
        from app.utils.audio.set_generator import lufs_to_energy, variety_score, TrackData

        await set_svc.get(set_id)
        items_list = await set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        if len(items) < 2:
            return SetReviewResult(
                overall_score=0.0, energy_arc_adherence=0.0,
                variety_score=0.0, weak_transitions=[], suggestions=["Set too short"],
            )

        unified_svc = UnifiedTransitionScoringService(features_svc.features_repo.session)
        svc = SetCurationService()

        # Score all transitions
        weak: list[WeakTransition] = []
        scores: list[float] = []
        for i in range(len(items) - 1):
            try:
                components = await unified_svc.score_components_by_ids(
                    items[i].track_id, items[i + 1].track_id,
                )
                total = components["total"]
            except ValueError:
                total = 0.0

            scores.append(total)
            if total < 0.4:
                weak.append(WeakTransition(
                    position=i,
                    from_track_id=items[i].track_id,
                    to_track_id=items[i + 1].track_id,
                    score=round(total, 3),
                    reason="Low transition quality" if total > 0 else "Missing features",
                ))

        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Variety scoring
        all_features = await features_svc.list_all()
        feat_map = {f.track_id: f for f in all_features}
        classified = svc.classify_features(all_features)

        track_data_list = []
        for item in items:
            feat = feat_map.get(item.track_id)
            mood_int = classified.get(item.track_id, TrackMood.DRIVING).intensity
            if feat:
                track_data_list.append(TrackData(
                    track_id=item.track_id, bpm=feat.bpm,
                    energy=lufs_to_energy(feat.lufs_i),
                    key_code=feat.key_code or 0,
                    mood=mood_int,
                ))
        var_score = variety_score(track_data_list) if track_data_list else 0.0

        suggestions: list[str] = []
        if weak:
            suggestions.append(f"{len(weak)} weak transitions (score < 0.4)")
        if var_score < 0.7:
            suggestions.append("Low variety — consider diversifying mood/key sequences")

        return SetReviewResult(
            overall_score=round(avg_score, 3),
            energy_arc_adherence=0.0,  # TODO: compute against template arc
            variety_score=round(var_score, 3),
            weak_transitions=weak,
            suggestions=suggestions,
        )
```

Add needed imports at top of `curation_tools.py`:
```python
from app.mcp.dependencies import get_features_service, get_set_service
from app.services.sets import DjSetService
```

**Step 2: Add test**

```python
async def test_review_set_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "review_set" in tool_names
```

**Step 3: Run tests, lint, commit**

```bash
uv run pytest tests/mcp/test_curation_tools.py -v
uv run ruff check app/mcp/workflows/curation_tools.py
git add app/mcp/workflows/curation_tools.py tests/mcp/test_curation_tools.py
git commit -m "feat: add review_set MCP tool for set quality analysis"
```

---

## Task 9: Full Test Suite + Lint Pass

**Files:** All modified files

**Step 1: Run full test suite**

Run: `uv run pytest -v`

**Step 2: Run linter**

Run: `uv run ruff check && uv run ruff format --check`

**Step 3: Run type checker**

Run: `uv run mypy app/utils/audio/mood_classifier.py app/utils/audio/set_templates.py app/services/set_curation.py`

**Step 4: Fix any issues found**

**Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: lint and type-check fixes for smart set curator"
```

---

## Task 10: Update Documentation

**Files:**
- Modify: `.claude/rules/mcp.md` — add curation tools to table
- Modify: `.claude/rules/audio.md` — add mood_classifier, set_templates

**Step 1: Add curation tools to MCP rules**

In `.claude/rules/mcp.md`, add to the DJ Workflow tools table:

```markdown
| `classify_tracks` | curation | Yes | Classify all tracks by 6 mood categories |
| `curate_set` | curation | No | Select tracks by template + mood slot matching |
| `review_set` | curation, setbuilder | Yes | Review set: weak transitions, variety, suggestions |
| `analyze_library_gaps` | curation | Yes | Compare library vs template needs, find gaps |
```

**Step 2: Commit docs**

```bash
git add .claude/rules/mcp.md
git commit -m "docs: add curation tools to MCP rules documentation"
```

---

## Dependency Graph

```text
Task 1 (mood_classifier) ─┬─→ Task 2 (templates) ─→ Task 3 (curation_service)
                           │                                   │
                           │                                   ├─→ Task 7 (MCP curation tools)
                           │                                   │         │
Task 4 (GA variety+LUFS) ─┤                                   │         ├─→ Task 8 (review_set)
                           │                                   │         │
Task 5 (wire LUFS) ────────┘                                   │         ├─→ Task 9 (full tests)
                                                               │         │
Task 6 (fix MCP bugs) ────────────────────────────────────────┘         ├─→ Task 10 (docs)
```

**Parallelizable:** Tasks 1 + 4 + 6 can run in parallel. Tasks 2 + 5 can run in parallel after 1/4 finish.
