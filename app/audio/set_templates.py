"""Slot-based set templates for DJ curation.

Each template defines a sequence of slots with target mood, energy,
BPM range, and duration. The curation service uses these to select
tracks that match the desired set arc.

Pure computation — no DB or IO.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from app.audio.mood_classifier import TrackMood


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


# ── Template definitions ─────────────────────────────────────


def _classic_60() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.CLASSIC_60,
        description="Standard 60-min arc: warm-up -> build -> peak -> breathe -> peak -> cooldown",
        duration_minutes=60,
        target_track_count=20,
        slots=(
            SetSlot(0.00, TrackMood.DUB_TECHNO, -12.0, (122, 126), 200, 0.7),
            SetSlot(0.05, TrackMood.DUB_TECHNO, -11.5, (123, 127), 200, 0.6),
            SetSlot(0.10, TrackMood.DETROIT, -10.5, (124, 128), 190, 0.5),
            SetSlot(0.15, TrackMood.MELODIC_DEEP, -10.0, (125, 129), 190, 0.5),
            SetSlot(0.22, TrackMood.PROGRESSIVE, -9.5, (126, 130), 180, 0.4),
            SetSlot(0.30, TrackMood.DRIVING, -9.0, (127, 131), 180, 0.4),
            SetSlot(0.38, TrackMood.HYPNOTIC, -8.5, (127, 131), 180, 0.4),
            SetSlot(0.45, TrackMood.PEAK_TIME, -7.5, (128, 134), 180, 0.3),
            SetSlot(0.52, TrackMood.RAW, -7.0, (129, 135), 180, 0.3),
            SetSlot(0.60, TrackMood.PEAK_TIME, -6.5, (130, 136), 180, 0.3),
            SetSlot(0.68, TrackMood.DRIVING, -9.0, (128, 132), 180, 0.5),  # breathe
            SetSlot(0.73, TrackMood.MELODIC_DEEP, -9.5, (127, 131), 190, 0.5),  # breathe
            SetSlot(0.78, TrackMood.HYPNOTIC, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.83, TrackMood.RAW, -7.0, (129, 135), 180, 0.3),
            SetSlot(0.87, TrackMood.PEAK_TIME, -6.5, (130, 136), 180, 0.3),
            SetSlot(0.90, TrackMood.PEAK_TIME, -7.0, (130, 136), 180, 0.3),
            SetSlot(0.93, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.4),
            SetSlot(0.96, TrackMood.DETROIT, -10.0, (127, 131), 190, 0.5),
            SetSlot(0.98, TrackMood.MELODIC_DEEP, -10.5, (126, 130), 200, 0.6),
            SetSlot(1.00, TrackMood.DUB_TECHNO, -11.5, (124, 128), 200, 0.7),
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
            SetSlot(0.12, TrackMood.DUB_TECHNO, -12.0, (122, 127), 200, 0.6),
            SetSlot(0.25, TrackMood.MINIMAL, -11.0, (124, 128), 200, 0.5),
            SetSlot(0.37, TrackMood.DETROIT, -10.5, (125, 129), 190, 0.5),
            SetSlot(0.50, TrackMood.MELODIC_DEEP, -10.0, (126, 130), 190, 0.4),
            SetSlot(0.62, TrackMood.PROGRESSIVE, -9.5, (126, 130), 180, 0.4),
            SetSlot(0.75, TrackMood.DRIVING, -9.0, (127, 131), 180, 0.4),
            SetSlot(0.87, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(1.00, TrackMood.HYPNOTIC, -8.5, (128, 132), 180, 0.4),
        ),
    )


def _peak_hour_60() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.PEAK_HOUR_60,
        description="60-min peak hour: high energy throughout with minimal cooldown",
        duration_minutes=60,
        target_track_count=20,
        slots=(
            SetSlot(0.00, TrackMood.HYPNOTIC, -9.0, (128, 132), 180, 0.4),
            SetSlot(0.05, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.4),
            SetSlot(0.10, TrackMood.PEAK_TIME, -7.5, (130, 135), 175, 0.3),
            SetSlot(0.16, TrackMood.RAW, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.22, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.28, TrackMood.ACID, -7.0, (132, 138), 170, 0.4),
            SetSlot(0.34, TrackMood.RAW, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.40, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.46, TrackMood.TRIBAL, -8.0, (130, 134), 180, 0.4),  # breathe
            SetSlot(0.52, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.58, TrackMood.RAW, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.64, TrackMood.INDUSTRIAL, -6.5, (132, 138), 170, 0.4),
            SetSlot(0.70, TrackMood.ACID, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.76, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.82, TrackMood.RAW, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.87, TrackMood.HYPNOTIC, -8.0, (129, 133), 180, 0.4),  # breathe
            SetSlot(0.90, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.93, TrackMood.PEAK_TIME, -7.5, (130, 135), 175, 0.3),
            SetSlot(0.96, TrackMood.DRIVING, -8.5, (129, 133), 180, 0.4),
            SetSlot(1.00, TrackMood.DRIVING, -9.0, (128, 132), 180, 0.5),
        ),
    )


def _roller_90() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.ROLLER_90,
        description=(
            "90-min extended roller: quick ramp to high energy, 2 peaks with brief valley"
        ),
        duration_minutes=90,
        target_track_count=28,
        slots=(
            SetSlot(0.00, TrackMood.PROGRESSIVE, -10.0, (125, 129), 190, 0.5),
            SetSlot(0.04, TrackMood.HYPNOTIC, -9.0, (127, 131), 185, 0.4),
            SetSlot(0.08, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.12, TrackMood.PEAK_TIME, -7.5, (129, 134), 180, 0.3),
            SetSlot(0.16, TrackMood.RAW, -7.0, (130, 135), 175, 0.3),
            SetSlot(0.20, TrackMood.PEAK_TIME, -6.5, (130, 136), 175, 0.3),
            SetSlot(0.25, TrackMood.ACID, -6.5, (131, 136), 175, 0.3),
            SetSlot(0.30, TrackMood.RAW, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.35, TrackMood.PEAK_TIME, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.40, TrackMood.INDUSTRIAL, -7.0, (132, 138), 170, 0.4),
            SetSlot(0.45, TrackMood.ACID, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.50, TrackMood.TRIBAL, -8.5, (129, 133), 180, 0.5),  # valley
            SetSlot(0.54, TrackMood.MELODIC_DEEP, -9.5, (128, 132), 190, 0.5),  # valley
            SetSlot(0.58, TrackMood.PROGRESSIVE, -8.5, (129, 133), 180, 0.4),
            SetSlot(0.62, TrackMood.HYPNOTIC, -8.0, (129, 134), 180, 0.4),
            SetSlot(0.66, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.70, TrackMood.RAW, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.74, TrackMood.ACID, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.78, TrackMood.INDUSTRIAL, -6.5, (132, 138), 170, 0.4),
            SetSlot(0.82, TrackMood.RAW, -6.5, (131, 137), 175, 0.3),
            SetSlot(0.86, TrackMood.PEAK_TIME, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.89, TrackMood.RAW, -7.0, (130, 135), 175, 0.3),
            SetSlot(0.92, TrackMood.HYPNOTIC, -8.0, (129, 133), 180, 0.4),
            SetSlot(0.94, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.96, TrackMood.PROGRESSIVE, -9.0, (128, 131), 185, 0.5),
            SetSlot(0.97, TrackMood.DETROIT, -10.0, (127, 130), 190, 0.5),
            SetSlot(0.98, TrackMood.MELODIC_DEEP, -10.5, (126, 129), 195, 0.6),
            SetSlot(1.00, TrackMood.DUB_TECHNO, -11.0, (125, 128), 200, 0.6),
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
        return -13.0 + pos / 0.80 * 7.0  # -13 -> -6
    return -6.0 - (pos - 0.80) / 0.20 * 5.0  # -6 -> -11


def _progressive_bpm(pos: float) -> tuple[float, float]:
    base = 122.0 + pos * 14.0  # 122 -> 136
    return (base - 2, base + 2)


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


def _wave_mood(pos: float) -> TrackMood:
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
    wave = math.sin(pos * math.pi * 3)
    amp = pos * 0.5 + 0.3
    base = -10.0 + pos * 2.0  # slight upward trend
    return max(-14.0, min(-6.0, base + wave * amp * 4.0))


def _wave_bpm(pos: float) -> tuple[float, float]:
    base = 126.0 + pos * 8.0
    return (base - 3, base + 3)


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


def _closing_60() -> SetTemplate:
    return SetTemplate(
        name=TemplateName.CLOSING_60,
        description="60-min closing: peak start, gradual cooldown to ambient close",
        duration_minutes=60,
        target_track_count=20,
        slots=(
            SetSlot(0.00, TrackMood.RAW, -7.0, (130, 136), 175, 0.3),
            SetSlot(0.05, TrackMood.PEAK_TIME, -7.0, (130, 135), 175, 0.3),
            SetSlot(0.10, TrackMood.PEAK_TIME, -7.5, (129, 134), 180, 0.3),
            SetSlot(0.16, TrackMood.HYPNOTIC, -8.0, (129, 133), 180, 0.4),
            SetSlot(0.22, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.28, TrackMood.TRIBAL, -7.5, (129, 134), 180, 0.3),  # mini peak
            SetSlot(0.34, TrackMood.DRIVING, -8.5, (128, 132), 180, 0.4),
            SetSlot(0.40, TrackMood.HYPNOTIC, -9.0, (127, 131), 185, 0.4),
            SetSlot(0.46, TrackMood.PROGRESSIVE, -9.5, (127, 131), 190, 0.5),
            SetSlot(0.52, TrackMood.MELODIC_DEEP, -9.0, (127, 131), 185, 0.4),
            SetSlot(0.58, TrackMood.DETROIT, -10.0, (126, 130), 190, 0.5),
            SetSlot(0.64, TrackMood.MELODIC_DEEP, -10.0, (126, 130), 190, 0.5),
            SetSlot(0.70, TrackMood.MINIMAL, -10.5, (125, 129), 195, 0.5),
            SetSlot(0.76, TrackMood.MELODIC_DEEP, -10.5, (125, 129), 195, 0.6),
            SetSlot(0.82, TrackMood.DUB_TECHNO, -11.0, (124, 128), 200, 0.6),
            SetSlot(0.87, TrackMood.DUB_TECHNO, -11.5, (123, 127), 200, 0.7),
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


# ── Template registry ────────────────────────────────────────

_TEMPLATES: dict[TemplateName, SetTemplate] = {}


def _init_templates() -> None:
    global _TEMPLATES
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
