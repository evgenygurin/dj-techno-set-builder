# djay Pro AI Crossfader FX — Implementation Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 7 fake transition types with all 16 real djay Pro AI Crossfader FX types, rewrite the recommender to match actual djay behavior, and add section-based mix points.

**Architecture:** Expand `TransitionType` StrEnum (7 → 16 real Crossfader FX names) → rewrite `recommend_transition()` with mood-aware + position-aware algorithm → load `track_sections` for mix_out_ms/mix_in_ms → enhance cheat sheet with expanded djay block. All existing wiring (`_scoring_helpers.py`, `TransitionScoreResult`, `djay_compatibility_score()`) stays intact.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Pydantic v2, pytest-asyncio. No new deps.

---

## What already exists (DO NOT recreate)

| Component | File | Status |
|-----------|------|--------|
| `TransitionRecommendation` dataclass | `app/utils/audio/_types.py:171` | ✅ Has `djay_bars`, `djay_bpm_mode` |
| `TransitionScoreResult` Pydantic | `app/mcp/types/workflows.py` | ✅ Has all 4 djay fields |
| `djay_compatibility_score()` | `app/services/transition_scoring.py:432` | ✅ Returns [0.0, 1.5] multiplier |
| `score_consecutive_transitions()` | `app/mcp/tools/_scoring_helpers.py` | ✅ Calls `recommend_transition()`, populates djay fields |
| `_generate_cheat_sheet()` | `app/mcp/tools/delivery.py:112` | ✅ Has basic djay line |
| `set_position` / `energy_direction` | `_scoring_helpers.py:128-133` | ✅ Computed per transition |

## What changes

| File | Action | Delta |
|------|--------|-------|
| `app/utils/audio/_types.py` | Modify | 7 → 16 enum values in `TransitionType` |
| `app/services/transition_type.py` | Rewrite | New 16-type recommender with mood awareness |
| `app/mcp/tools/_scoring_helpers.py` | Modify | Batch-load sections for mix_out_ms/mix_in_ms |
| `app/mcp/tools/delivery.py` | Modify | Expanded multi-line djay block in cheat sheet |
| `tests/services/test_transition_type_djay.py` | Rewrite | Tests for all 16 types |

---

## djay Pro AI Crossfader FX Reference (from app screenshots)

### Classic FX (9 types)

| # | Name | Audio processing | Best for techno |
|---|------|-----------------|-----------------|
| 1 | **Fade** | Volume crossfade | ambient/dub, minimal — "невидимый" переход |
| 2 | **Filter** | LPF on outgoing, HPF on incoming | **Основной для техно.** Маскирует тональные конфликты |
| 3 | **EQ** | 3-band swap (low→mid→high) | **Второй по важности.** Чистый swap бочки |
| 4 | **Echo** | Sync delay + feedback на уходящем | hypnotic, dub, minimal |
| 5 | **Dissolve** | Granular degradation + reverb | ambient, melodic_deep |
| 6 | **Tremolo** | LFO amplitude modulation | tribal, driving, acid |
| 7 | **Lunar Echo** | Shimmer reverb + pitch modulation | dub_techno, ambient |
| 8 | **Riser** | Noise sweep + HPF вверх | peak_time, driving — build-up |
| 9 | **Shuffle** | Random selection (meta-type) | Не для серьёзных сетов |

### Neural Mix FX (7 types)

| # | Name | Audio processing | Best for techno |
|---|------|-----------------|-----------------|
| 10 | **Neural Mix (Fade)** | Stem-aware crossfade, drums swap чисто | **Лучший default.** Все поджанры |
| 11 | **Neural Mix (Echo Out)** | Stem-separated echo | hypnotic, dub — чистый echo |
| 12 | **Neural Mix (Vocal Sustain)** | Vocal freeze в granular pad | Редко в техно |
| 13 | **Neural Mix (Harmonic Sustain)** | Synth/pad freeze | melodic_deep, progressive |
| 14 | **Neural Mix (Drum Swap)** | Мгновенная замена drum-стема | **Мощнейший!** driving, peak_time |
| 15 | **Neural Mix (Vocal Cut)** | Убирает вокал из перехода | Для vocal tracks |
| 16 | **Neural Mix (Drum Cut)** | Drums out → breakdown → drop | progressive, hypnotic, hard |

### Position-in-set matrix

| Позиция | Лучшие FX |
|---------|-----------|
| **Opening** (0.0-0.15) | Fade, NM Fade, Dissolve, Lunar Echo |
| **Build-up** (0.15-0.40) | Filter, EQ, NM Echo Out, NM Harmonic Sustain |
| **Drive** (0.40-0.65) | NM Drum Swap, EQ, Filter, Tremolo |
| **Pre-peak** (0.65-0.80) | Riser, NM Drum Cut, Filter |
| **Peak** (0.80-0.90) | NM Drum Swap, EQ, Filter |
| **Closing** (0.90-1.0) | Fade, Dissolve, Lunar Echo, Echo, NM Fade |

---

## Task 1: Update `TransitionType` enum (16 real types)

**Files:**
- Modify: `app/utils/audio/_types.py:10-19`
- Test: `tests/services/test_transition_type_djay.py`

- [ ] **Step 1: Write failing test for 16 enum values**

```python
# tests/services/test_transition_type_djay.py
"""Tests for djay Pro AI Crossfader FX transition types."""

from app.utils.audio._types import TransitionType

def test_transition_type_has_all_16_djay_cfx():
    """TransitionType must match exact djay Pro AI Crossfader FX names."""
    expected = {
        # Classic FX
        "Fade", "Filter", "EQ", "Echo", "Dissolve",
        "Tremolo", "Lunar Echo", "Riser", "Shuffle",
        # Neural Mix FX
        "Neural Mix (Fade)", "Neural Mix (Echo Out)",
        "Neural Mix (Vocal Sustain)", "Neural Mix (Harmonic Sustain)",
        "Neural Mix (Drum Swap)", "Neural Mix (Vocal Cut)",
        "Neural Mix (Drum Cut)",
    }
    actual = {member.value for member in TransitionType}
    assert actual == expected, f"Missing: {expected - actual}, Extra: {actual - expected}"

def test_transition_type_enum_names():
    """Enum attribute names must be valid Python identifiers."""
    assert TransitionType.FADE == "Fade"
    assert TransitionType.FILTER == "Filter"
    assert TransitionType.EQ == "EQ"
    assert TransitionType.ECHO == "Echo"
    assert TransitionType.DISSOLVE == "Dissolve"
    assert TransitionType.TREMOLO == "Tremolo"
    assert TransitionType.LUNAR_ECHO == "Lunar Echo"
    assert TransitionType.RISER == "Riser"
    assert TransitionType.SHUFFLE == "Shuffle"
    assert TransitionType.NM_FADE == "Neural Mix (Fade)"
    assert TransitionType.NM_ECHO_OUT == "Neural Mix (Echo Out)"
    assert TransitionType.NM_VOCAL_SUSTAIN == "Neural Mix (Vocal Sustain)"
    assert TransitionType.NM_HARMONIC_SUSTAIN == "Neural Mix (Harmonic Sustain)"
    assert TransitionType.NM_DRUM_SWAP == "Neural Mix (Drum Swap)"
    assert TransitionType.NM_VOCAL_CUT == "Neural Mix (Vocal Cut)"
    assert TransitionType.NM_DRUM_CUT == "Neural Mix (Drum Cut)"

def test_transition_recommendation_has_djay_fields():
    from app.utils.audio._types import TransitionRecommendation

    rec = TransitionRecommendation(
        transition_type=TransitionType.NM_DRUM_SWAP,
        confidence=0.9,
        reason="test",
        djay_bars=8,
        djay_bpm_mode="Sync",
    )
    assert rec.djay_bars == 8
    assert rec.djay_bpm_mode == "Sync"
    assert rec.transition_type == "Neural Mix (Drum Swap)"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/test_transition_type_djay.py -v
```
Expected: FAIL — old enum has 7 values, not 16.

- [ ] **Step 3: Replace TransitionType enum with 16 real types**

Replace in `app/utils/audio/_types.py:10-19`:

```python
class TransitionType(StrEnum):
    """djay Pro AI Crossfader FX transition types (exact UI names)."""

    # Classic FX
    FADE = "Fade"
    FILTER = "Filter"
    EQ = "EQ"
    ECHO = "Echo"
    DISSOLVE = "Dissolve"
    TREMOLO = "Tremolo"
    LUNAR_ECHO = "Lunar Echo"
    RISER = "Riser"
    SHUFFLE = "Shuffle"
    # Neural Mix FX
    NM_FADE = "Neural Mix (Fade)"
    NM_ECHO_OUT = "Neural Mix (Echo Out)"
    NM_VOCAL_SUSTAIN = "Neural Mix (Vocal Sustain)"
    NM_HARMONIC_SUSTAIN = "Neural Mix (Harmonic Sustain)"
    NM_DRUM_SWAP = "Neural Mix (Drum Swap)"
    NM_VOCAL_CUT = "Neural Mix (Vocal Cut)"
    NM_DRUM_CUT = "Neural Mix (Drum Cut)"
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest tests/services/test_transition_type_djay.py -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Fix any imports of old enum members**

Search for references to removed members and update:

```bash
uv run ruff check app/ tests/ --select E
```

| Old member | New member |
|------------|-----------|
| `NEURAL_MIX` | `NM_FADE` (or `NM_DRUM_SWAP` depending on context) |
| `TECHNO` | `FILTER` (HPF sweep was the "techno" effect) |
| `REPEATER` | `TREMOLO` (closest match for rhythmic gating) |
| `BEAT_MATCH` | `FADE` (simple crossfade) |

Check files: `app/services/transition_type.py`, `app/mcp/tools/delivery.py`, any test that references `TransitionType.*`.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -x -q
```
Expected: All pass. Fix any broken imports.

- [ ] **Step 7: Commit**

```bash
git add app/utils/audio/_types.py tests/services/test_transition_type_djay.py
git commit -F /tmp/msg.txt
# feat(audio): replace 7 fake transition types with 16 real djay Pro AI Crossfader FX
```

---

## Task 2: Rewrite transition recommender (16-type algorithm)

**Files:**
- Rewrite: `app/services/transition_type.py`
- Test: `tests/services/test_transition_type_djay.py` (add recommendation tests)

**Design decisions:**
- Priority-based selection (first matching rule wins) — same pattern, more rules
- Mood of outgoing track (`hp_ratio`, `centroid_hz`, `kick_prominence`) determines style
- `set_position` determines aggression level
- Neural Mix types preferred when `kick_prominence > 0.65` (good stem separation)
- `alt_type` field populated with second-best option

- [ ] **Step 1: Write tests for recommendation rules**

Add to `tests/services/test_transition_type_djay.py`:

```python
import pytest
from app.services.transition_scoring import TrackFeatures
from app.services.transition_type import recommend_transition
from app.utils.audio._types import TransitionType

def _make_features(**overrides) -> TrackFeatures:
    """Helper to create TrackFeatures with techno defaults."""
    defaults = dict(
        bpm=130.0, energy_lufs=-8.0, key_code=0,
        harmonic_density=0.5, centroid_hz=2500.0,
        band_ratios=[0.3, 0.4, 0.3], onset_rate=4.0,
        kick_prominence=0.75, hnr_db=5.0, spectral_slope=-0.02,
    )
    defaults.update(overrides)
    return TrackFeatures(**defaults)

class TestNeuralMixDrumSwap:
    """NM Drum Swap: strong kicks + close BPM + close key."""

    def test_strong_kicks_close_bpm_key(self):
        a = _make_features(kick_prominence=0.85, bpm=128.0)
        b = _make_features(kick_prominence=0.80, bpm=129.0)
        rec = recommend_transition(a, b, camelot_dist=1, set_position=0.5, energy_direction="stable")
        assert rec.transition_type == TransitionType.NM_DRUM_SWAP

class TestFilter:
    """Filter: Camelot conflict (dist >= 3)."""

    def test_camelot_conflict(self):
        a = _make_features()
        b = _make_features()
        rec = recommend_transition(a, b, camelot_dist=4, set_position=0.5, energy_direction="stable")
        assert rec.transition_type in (TransitionType.FILTER, TransitionType.EQ)

class TestEQ:
    """EQ: strong kicks + stable energy (driving/peak sections)."""

    def test_driving_section(self):
        a = _make_features(kick_prominence=0.80, centroid_hz=2800.0)
        b = _make_features(kick_prominence=0.82, centroid_hz=2900.0)
        rec = recommend_transition(
            a, b, camelot_dist=1, set_position=0.6,
            energy_direction="stable",
        )
        assert rec.transition_type in (TransitionType.EQ, TransitionType.NM_DRUM_SWAP)

class TestRiser:
    """Riser: energy going up in pre-peak position."""

    def test_pre_peak_energy_up(self):
        a = _make_features(kick_prominence=0.50)
        b = _make_features(kick_prominence=0.50)
        rec = recommend_transition(
            a, b, camelot_dist=1, set_position=0.72,
            energy_direction="up",
        )
        assert rec.transition_type == TransitionType.RISER

class TestNMDrumCut:
    """NM Drum Cut: breakdown moment, energy dropping."""

    def test_breakdown_energy_down(self):
        a = _make_features(kick_prominence=0.80)
        b = _make_features(kick_prominence=0.70, centroid_hz=2000.0)
        rec = recommend_transition(
            a, b, camelot_dist=1, set_position=0.55,
            energy_direction="down",
        )
        assert rec.transition_type in (
            TransitionType.NM_DRUM_CUT, TransitionType.ECHO,
            TransitionType.NM_ECHO_OUT,
        )

class TestLunarEcho:
    """Lunar Echo / Echo: atmospheric tracks or closing."""

    def test_closing_position(self):
        a = _make_features(hp_ratio=3.0, centroid_hz=1800.0)
        b = _make_features(hp_ratio=2.8, centroid_hz=1900.0)
        rec = recommend_transition(
            a, b, camelot_dist=1, set_position=0.95,
            energy_direction="down",
        )
        assert rec.transition_type in (
            TransitionType.LUNAR_ECHO, TransitionType.ECHO,
            TransitionType.FADE, TransitionType.DISSOLVE,
            TransitionType.NM_FADE,
        )

class TestFallbackFade:
    """Fade is the ultimate fallback."""

    def test_generic_tracks(self):
        a = _make_features(kick_prominence=0.40, centroid_hz=2500.0)
        b = _make_features(kick_prominence=0.40, centroid_hz=2500.0)
        rec = recommend_transition(
            a, b, camelot_dist=1, set_position=0.3,
            energy_direction="stable",
        )
        # Should return something valid, not crash
        assert rec.transition_type in TransitionType
        assert 0.0 <= rec.confidence <= 1.0
        assert rec.djay_bars in (4, 8, 16, 32)
```

- [ ] **Step 2: Run tests — expect FAIL (old recommender returns old types)**

```bash
uv run pytest tests/services/test_transition_type_djay.py -v
```

- [ ] **Step 3: Rewrite `app/services/transition_type.py`**

```python
"""Transition type recommender for djay Pro AI.

Selects the best Crossfader FX from 16 djay Pro AI options based on
audio features, set position, and energy direction.

Priority-based: first matching rule wins. Rules ordered by specificity.
Pure function, no DB dependencies.

Crossfader FX categories:
  Classic: Fade, Filter, EQ, Echo, Dissolve, Tremolo, Lunar Echo, Riser, Shuffle
  Neural Mix: NM Fade/Echo Out/Vocal Sustain/Harmonic Sustain/Drum Swap/Vocal Cut/Drum Cut
"""

from __future__ import annotations

from app.services.transition_scoring import TrackFeatures
from app.utils.audio._types import TransitionRecommendation, TransitionType

def recommend_transition(
    track_a: TrackFeatures,
    track_b: TrackFeatures,
    *,
    camelot_dist: int,
    set_position: float = 0.5,
    energy_direction: str = "stable",
) -> TransitionRecommendation:
    """Recommend a djay Pro AI Crossfader FX for a track pair.

    Args:
        track_a: Outgoing track features.
        track_b: Incoming track features.
        camelot_dist: Camelot wheel distance (0=same, 1=adjacent, ...).
        set_position: Position in set (0.0=opening, 1.0=closing).
        energy_direction: "up", "down", or "stable".
    """
    bpm_diff = abs(track_a.bpm - track_b.bpm)
    strong_kicks = track_a.kick_prominence > 0.65 and track_b.kick_prominence > 0.65
    very_strong_kicks = track_a.kick_prominence > 0.75 and track_b.kick_prominence > 0.75
    melodic = track_a.hp_ratio > 2.5 or track_a.centroid_hz < 2200.0
    closing = set_position > 0.90
    opening = set_position < 0.15

    # ── 1. NM Drum Swap — best for techno: clean drum exchange ───────────
    # Requires: strong kicks on both (good stem separation), close BPM, close key
    if very_strong_kicks and bpm_diff <= 4.0 and camelot_dist <= 2:
        kick_min = min(track_a.kick_prominence, track_b.kick_prominence)
        return TransitionRecommendation(
            transition_type=TransitionType.NM_DRUM_SWAP,
            confidence=kick_min,
            reason=(
                f"kick {track_a.kick_prominence:.2f}/{track_b.kick_prominence:.2f} "
                f"— stem-separated drum swap"
            ),
            alt_type=TransitionType.NM_FADE,
            djay_bars=8,
            djay_bpm_mode="Sync",
        )

    # ── 2. Riser — pre-peak build-up ────────────────────────────────────
    if energy_direction == "up" and 0.65 < set_position < 0.80:
        return TransitionRecommendation(
            transition_type=TransitionType.RISER,
            confidence=0.80,
            reason="Нарастающее напряжение перед пиком сета",
            alt_type=TransitionType.FILTER,
            djay_bars=8,
            djay_bpm_mode="Sync + Tempo Blend" if bpm_diff > 3.0 else "Sync",
        )

    # ── 3. NM Drum Cut — breakdown moment (energy dropping) ─────────────
    if energy_direction == "down" and strong_kicks and 0.3 < set_position < 0.85:
        return TransitionRecommendation(
            transition_type=TransitionType.NM_DRUM_CUT,
            confidence=0.78,
            reason="Drums out → breakdown → new track drops in",
            alt_type=TransitionType.ECHO,
            djay_bars=16,
            djay_bpm_mode="Sync",
        )

    # ── 4. Filter — Camelot conflict (masks harmonic clash) ─────────────
    if camelot_dist >= 3:
        bpm_mode = "Sync + Tempo Blend" if bpm_diff > 4.0 else "Sync"
        return TransitionRecommendation(
            transition_type=TransitionType.FILTER,
            confidence=0.75,
            reason=f"Camelot dist {camelot_dist} — LPF/HPF masks harmonic conflict",
            alt_type=TransitionType.EQ,
            djay_bars=8,
            djay_bpm_mode=bpm_mode,
        )

    # ── 5. EQ — driving/peak sections with strong kicks ─────────────────
    if strong_kicks and energy_direction in ("up", "stable") and 0.4 < set_position < 0.90:
        return TransitionRecommendation(
            transition_type=TransitionType.EQ,
            confidence=0.82,
            reason="Strong kicks — EQ swap avoids bass phase conflict",
            alt_type=TransitionType.NM_DRUM_SWAP if very_strong_kicks else TransitionType.FILTER,
            djay_bars=16,
            djay_bpm_mode="Sync" if bpm_diff <= 3.0 else "Sync + Tempo Blend",
        )

    # ── 6. NM Harmonic Sustain — melodic tracks, mid-set ────────────────
    if melodic and strong_kicks and 0.15 < set_position < 0.60:
        return TransitionRecommendation(
            transition_type=TransitionType.NM_HARMONIC_SUSTAIN,
            confidence=0.76,
            reason="Melodic content — pad freeze creates harmonic bridge",
            alt_type=TransitionType.NM_FADE,
            djay_bars=16,
            djay_bpm_mode="Sync",
        )

    # ── 7. Lunar Echo — atmospheric closing ─────────────────────────────
    if closing and melodic:
        return TransitionRecommendation(
            transition_type=TransitionType.LUNAR_ECHO,
            confidence=0.78,
            reason="Closing + melodic — shimmer reverb creates space",
            alt_type=TransitionType.DISSOLVE,
            djay_bars=16,
            djay_bpm_mode="Sync",
        )

    # ── 8. Echo / NM Echo Out — atmospheric or end of set ───────────────
    if melodic or set_position > 0.85:
        if strong_kicks:
            return TransitionRecommendation(
                transition_type=TransitionType.NM_ECHO_OUT,
                confidence=0.75,
                reason="Melodic + strong kicks — stem echo avoids drum chaos",
                alt_type=TransitionType.ECHO,
                djay_bars=8,
                djay_bpm_mode="Sync",
            )
        return TransitionRecommendation(
            transition_type=TransitionType.ECHO,
            confidence=0.73,
            reason="Atmospheric — reverb tail creates smooth exit",
            alt_type=TransitionType.LUNAR_ECHO,
            djay_bars=16,
            djay_bpm_mode="Sync",
        )

    # ── 9. Tremolo — tribal/acid with high onset rate ───────────────────
    if track_a.onset_rate > 5.5 and track_a.kick_prominence > 0.7 and 0.3 < set_position < 0.7:
        return TransitionRecommendation(
            transition_type=TransitionType.TREMOLO,
            confidence=0.68,
            reason=f"onset {track_a.onset_rate:.1f}/s — rhythmic gating adds tension",
            alt_type=TransitionType.FILTER,
            djay_bars=8,
            djay_bpm_mode="Sync",
        )

    # ── 10. Dissolve — opening / very soft transitions ──────────────────
    if opening and melodic:
        return TransitionRecommendation(
            transition_type=TransitionType.DISSOLVE,
            confidence=0.70,
            reason="Opening + melodic — granular dissolve for gentle start",
            alt_type=TransitionType.FADE,
            djay_bars=16,
            djay_bpm_mode="Sync",
        )

    # ── 11. NM Fade — good kicks but no specific rule matched ───────────
    if strong_kicks:
        return TransitionRecommendation(
            transition_type=TransitionType.NM_FADE,
            confidence=0.72,
            reason="Strong kicks — stem-aware fade keeps drums clean",
            alt_type=TransitionType.FILTER,
            djay_bars=16,
            djay_bpm_mode="Sync" if bpm_diff <= 3.0 else "Automatic",
        )

    # ── 12. Filter — general purpose electronic transition ──────────────
    if bpm_diff <= 6.0:
        return TransitionRecommendation(
            transition_type=TransitionType.FILTER,
            confidence=0.70,
            reason="General-purpose frequency sweep",
            alt_type=TransitionType.FADE,
            djay_bars=16,
            djay_bpm_mode="Sync" if bpm_diff <= 3.0 else "Sync + Tempo Blend",
        )

    # ── 13. Fade — ultimate fallback ────────────────────────────────────
    return TransitionRecommendation(
        transition_type=TransitionType.FADE,
        confidence=0.60,
        reason="Standard crossfade",
        alt_type=TransitionType.FILTER,
        djay_bars=16,
        djay_bpm_mode="Automatic",
    )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/services/test_transition_type_djay.py -v
```

- [ ] **Step 5: Run lint + full test suite**

```bash
make check
```

- [ ] **Step 6: Commit**

```bash
git add app/services/transition_type.py tests/services/test_transition_type_djay.py
git commit -F /tmp/msg.txt
# feat(audio): rewrite transition recommender for 16 real djay Pro AI Crossfader FX
```

---

## Task 3: Add section-based mix points (mix_out_ms / mix_in_ms)

**Files:**
- Modify: `app/mcp/tools/_scoring_helpers.py`
- Test: `tests/services/test_transition_type_djay.py` (add section loading test)

**Context:** `track_sections` has 107K rows. `SectionType.INTRO=0`, `SectionType.OUTRO=4`. We batch-load sections for all tracks in the set, then pick intro start / outro start.

- [ ] **Step 1: Write test for section-based mix points**

Add to `tests/services/test_transition_type_djay.py`:

```python
def test_get_section_mix_points():
    """Helper should extract intro/outro ms from section data."""
    from app.mcp.tools._scoring_helpers import _get_mix_points

    # Simulate section data: [(section_type, start_ms, end_ms), ...]
    sections = [
        (0, 0, 32000),      # INTRO: 0-32s
        (2, 32000, 96000),   # DROP
        (4, 180000, 210000), # OUTRO: 180-210s
    ]
    mix_in, mix_out = _get_mix_points(sections)
    assert mix_in == 0       # INTRO start
    assert mix_out == 180000  # OUTRO start
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest tests/services/test_transition_type_djay.py::test_get_section_mix_points -v
```

- [ ] **Step 3: Add `_get_mix_points()` helper to `_scoring_helpers.py`**

Add at the top of the scoring helpers module:

```python
from app.models.enums import SectionType

def _get_mix_points(
    sections: list[tuple[int, int, int]],
) -> tuple[int | None, int | None]:
    """Extract mix-in (intro start) and mix-out (outro start) from sections.

    Args:
        sections: List of (section_type, start_ms, end_ms) tuples.

    Returns:
        (mix_in_ms, mix_out_ms) — None if section not found.
    """
    mix_in: int | None = None
    mix_out: int | None = None
    for sec_type, start_ms, _end_ms in sections:
        if sec_type == SectionType.INTRO and mix_in is None:
            mix_in = start_ms
        if sec_type == SectionType.OUTRO and (mix_out is None or start_ms > mix_out):
            mix_out = start_ms
    return mix_in, mix_out
```

- [ ] **Step 4: Run helper test — expect PASS**

```bash
uv run pytest tests/services/test_transition_type_djay.py::test_get_section_mix_points -v
```

- [ ] **Step 5: Wire section loading into `score_consecutive_transitions()`**

In `_scoring_helpers.py`, inside `score_consecutive_transitions()`, after building `title_map`:

```python
# Batch-load sections for mix points (single query, not N+1)
from app.repositories.sections import SectionsRepository

section_map: dict[int, list[tuple[int, int, int]]] = {}
try:
    session = features_svc._repo._session  # type: ignore[attr-defined]
    sections_repo = SectionsRepository(session)
    all_track_ids = [item.track_id for item in items]
    # get_latest_by_track_ids() returns dict[track_id, list[TrackSection]]
    raw_map = await sections_repo.get_latest_by_track_ids(all_track_ids)
    section_map = {
        tid: [(s.section_type, s.start_ms, s.end_ms) for s in secs]
        for tid, secs in raw_map.items()
    }
except Exception:
    pass  # sections are optional enrichment
```

Then update the loop to populate mix points:

```python
# Replace existing mix_out_ms_val / mix_in_ms_val with section-based values
if mix_out_ms_val is None and from_item.track_id in section_map:
    _, mix_out_ms_val = _get_mix_points(section_map[from_item.track_id])
if mix_in_ms_val is None and to_item.track_id in section_map:
    mix_in_ms_val, _ = _get_mix_points(section_map[to_item.track_id])
```

**Note:** `get_latest_by_track_ids()` in `app/repositories/sections.py:22` returns `dict[int, list[TrackSection]]` with a single IN-query. Do NOT use `list_by_track()` — it returns `tuple[list, int]` and would be N+1.

- [ ] **Step 6: Run full test suite**

```bash
make check
```

- [ ] **Step 7: Commit**

```bash
git add app/mcp/tools/_scoring_helpers.py tests/services/test_transition_type_djay.py
git commit -F /tmp/msg.txt
# feat(audio): add section-based mix_in/mix_out points from track_sections
```

---

## Task 4: Enhance cheat sheet with expanded djay block

**Files:**
- Modify: `app/mcp/tools/delivery.py:161-172` (`_generate_cheat_sheet`)

**Current djay line** (single line):
```bash
     📱 djay: Neural Mix · 16 bars · Sync  (out@180s → in@0s)
```

**New expanded block** (multi-line with reason):
```bash
     📱 djay Pro AI:
     ┌─ FX: Neural Mix (Drum Swap)
     ├─ Bars: 8 · BPM: Sync
     ├─ Mix: out@180s → in@0s
     └─ kick 0.85/0.80 — stem-separated drum swap
```

- [ ] **Step 1: Update `_generate_cheat_sheet()` djay block**

Replace lines 161-172 in `delivery.py`:

```python
            # djay Pro AI Crossfader FX block
            if tx.recommended_type:
                djay_bars = tx.djay_bars or 16
                djay_mode = tx.djay_bpm_mode or "Sync"
                reason = tx.reason or ""

                lines.append("     📱 djay Pro AI:")
                lines.append(f"     ┌─ FX: {tx.recommended_type}")

                bar_mode = f"{djay_bars} bars · BPM: {djay_mode}"
                lines.append(f"     ├─ {bar_mode}")

                # Mix points line (if available)
                mix_parts: list[str] = []
                if tx.mix_out_ms is not None:
                    mix_parts.append(f"out@{tx.mix_out_ms // 1000}s")
                if tx.mix_in_ms is not None:
                    mix_parts.append(f"in@{tx.mix_in_ms // 1000}s")
                if mix_parts:
                    lines.append(f"     ├─ Mix: {' → '.join(mix_parts)}")

                # Alt type
                if tx.alt_type:
                    lines.append(f"     ├─ Alt: {tx.alt_type}")

                # Reason (last line with └─)
                if reason:
                    lines.append(f"     └─ {reason}")
                else:
                    # Close the box
                    if lines[-1].startswith("     ├─"):
                        lines[-1] = lines[-1].replace("├─", "└─", 1)
```

- [ ] **Step 2: Verify manually with existing test**

```bash
uv run pytest tests/mcp/test_workflow_delivery.py -v -k cheat
```

If no specific cheat sheet test exists, run delivery tests:
```bash
uv run pytest tests/mcp/ -v -k delivery
```

- [ ] **Step 3: Run full suite**

```bash
make check
```

- [ ] **Step 4: Commit**

```bash
git add app/mcp/tools/delivery.py
git commit -F /tmp/msg.txt
# feat(mcp): expand cheat sheet djay block with FX name, bars, mix points, reason
```

---

## Task 5: Update cheat sheet footer legend

**Files:**
- Modify: `app/mcp/tools/delivery.py` (footer section of `_generate_cheat_sheet`)

- [ ] **Step 1: Add Crossfader FX legend to cheat sheet footer**

After the existing footer (Keys, BPM lines), add:

```python
    # Crossfader FX legend
    lines.append("")
    lines.append("Crossfader FX:")
    lines.append("  Filter — LPF/HPF sweep (masks key conflicts)")
    lines.append("  EQ — 3-band swap (clean bass transition)")
    lines.append("  NM Drum Swap — AI drum exchange (best for techno)")
    lines.append("  NM Drum Cut — drums out → breakdown → drop")
    lines.append("  NM Fade — AI stem-aware crossfade")
    lines.append("  Riser — noise sweep build-up")
    lines.append("  Echo/Lunar Echo — delay/shimmer reverb")
    lines.append("  Fade — simple volume crossfade")
```

- [ ] **Step 2: Run tests**

```bash
make check
```

- [ ] **Step 3: Commit**

```bash
git add app/mcp/tools/delivery.py
git commit -F /tmp/msg.txt
# docs(mcp): add Crossfader FX legend to cheat sheet footer
```

---

## Task 6: Update docs and rules

**Files:**
- Modify: `.claude/rules/audio.md` — update TransitionType reference
- Modify: `CHANGELOG.md` — add to [Unreleased]

- [ ] **Step 1: Update audio.md transition types reference**

Replace any mention of "7 djay Pro AI options" or the old type list with:

```markdown
### Transition types (16 djay Pro AI Crossfader FX)

`TransitionType` in `app/utils/audio/_types.py` — exact names from djay Pro AI UI:

| Category | Types | Best for techno |
|----------|-------|-----------------|
| Classic | Fade, Filter, EQ, Echo, Dissolve, Tremolo, Lunar Echo, Riser, Shuffle | Filter, EQ, Riser — основные |
| Neural Mix | NM Fade, NM Echo Out, NM Vocal Sustain, NM Harmonic Sustain, NM Drum Swap, NM Vocal Cut, NM Drum Cut | NM Drum Swap, NM Fade, NM Drum Cut — топ для техно |
```

- [ ] **Step 2: Update CHANGELOG.md**

Add to `[Unreleased]` → Changed:

```markdown
- **Changed**: TransitionType enum expanded from 7 fake to 16 real djay Pro AI Crossfader FX types
- **Changed**: Transition recommender rewritten with mood-aware + position-aware algorithm for all 16 types
- **Added**: Section-based mix_in_ms/mix_out_ms from track_sections in transition scoring
- **Changed**: Cheat sheet djay block expanded with FX name, bars, mix points, alt type, reason
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/audio.md CHANGELOG.md
git commit -F /tmp/msg.txt
# docs: update rules and changelog for djay Pro AI Crossfader FX v2
```

---

## Gotchas

| Gotcha | Detail |
|--------|--------|
| `SectionType.OUTRO = 4` | NOT 5. Check `app/models/enums.py` |
| `camelot_dist` param name | NOT `camelot_distance` — match existing signature |
| `hp_ratio` is UNBOUNDED | Range 0.66-17.25 for techno. NOT 0-1 |
| `kick_prominence` range | 0.0-1.0. Threshold for "strong kicks" = 0.65 (not 0.75) |
| `onset_rate` field name | `onset_rate` in TrackFeatures (from `onset_rate_mean` in DB) |
| Old enum members | `NEURAL_MIX`, `TECHNO`, `REPEATER`, `BEAT_MATCH` — grep for all references |
| `Shuffle` type | Meta-type (random). Never recommend it — exclude from algorithm |
| `NM_VOCAL_SUSTAIN/CUT` | Rare in techno (no vocals). Low priority in algorithm |
| DB column names | `onset_rate_mean` (NOT `onset_rate`), `hnr_mean_db` (NOT `hnr_db`) in raw SQL |
| Test pollution | Use `merge()` not `insert()`, high IDs (80000+), index-based features |
