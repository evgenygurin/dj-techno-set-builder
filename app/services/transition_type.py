"""Transition type recommender for djay Pro AI.

Selects the best Crossfader FX transition type from 7 djay Pro AI options
based on audio features of the outgoing and incoming tracks.

Priority-based selection logic — first matching rule wins.
Pure function, no DB dependencies.

Rules match djay Pro AI (Algoriddim) Automix AI behaviour:
  1. Neural Mix  — чёткие барабаны на обоих → стемы дадут чистый drum swap
  2. Techno      — BPM близкий + энергия стабильна/растёт
  3. Riser       — энергия растёт в середине сета (0.4-0.75 set_position)
  4. Filter      — Camelot конфликт (dist >= 3)
  5. Echo        — мелодичный/atmospheric трек или конец сета
  6. Repeater    — высокий onset rate в середине сета
  7. Beat Match  — fallback
"""

from __future__ import annotations

from app.services.transition_scoring import TrackFeatures
from app.utils.audio._types import TransitionRecommendation, TransitionType


def recommend_transition(
    track_a: TrackFeatures,
    track_b: TrackFeatures,
    *,
    camelot_dist: int,
    set_position: float = 0.5,  # 0.0 = начало, 1.0 = конец
    energy_direction: str = "stable",  # "up" | "down" | "stable"
) -> TransitionRecommendation:
    """Recommend a djay Pro AI transition type for a track pair.

    Uses 7 priority-based rules that map to exact Crossfader FX names.
    First matching rule wins.

    Args:
        track_a: Outgoing track features.
        track_b: Incoming track features.
        camelot_dist: Camelot wheel distance (0 = same key, 1 = adjacent, ...).
        set_position: Position in the set (0.0 = opening, 1.0 = closing).
        energy_direction: Direction of energy change ("up", "down", "stable").

    Returns:
        TransitionRecommendation with djay type, bars, BPM mode, and reason.
    """
    bpm_diff = abs(track_a.bpm - track_b.bpm)

    # 1. Neural Mix — чёткие барабаны → стемы дадут чистый drum swap
    if (
        track_a.kick_prominence > 0.75
        and track_b.kick_prominence > 0.75
        and bpm_diff <= 4.0
        and camelot_dist <= 2
    ):
        kick_min = min(track_a.kick_prominence, track_b.kick_prominence)
        return TransitionRecommendation(
            transition_type=TransitionType.NEURAL_MIX,
            confidence=kick_min,
            reason=(
                f"Чёткие барабаны (kick {track_a.kick_prominence:.2f}/"
                f"{track_b.kick_prominence:.2f}) — стемы дадут чистый drum swap"
            ),
            djay_bars=16,
            djay_bpm_mode="Sync",
        )

    # 2. Techno — HPF sweep + resonance peak (основной техно-переход)
    if bpm_diff <= 6.0 and energy_direction in ("up", "stable"):
        bpm_mode = "Sync" if bpm_diff <= 3.0 else "Sync + Tempo Blend"
        conf = max(0.60, 0.85 - bpm_diff * 0.04)
        return TransitionRecommendation(
            transition_type=TransitionType.TECHNO,
            confidence=conf,
            reason=f"BPM diff {bpm_diff:.1f} — HPF sweep + resonance peak",
            djay_bars=16,
            djay_bpm_mode=bpm_mode,
        )

    # 3. Riser — нарастающее напряжение перед пиком сета
    if energy_direction == "up" and 0.4 < set_position < 0.75:
        return TransitionRecommendation(
            transition_type=TransitionType.RISER,
            confidence=0.80,
            reason="Нарастающее напряжение перед пиком сета",
            djay_bars=8,
            djay_bpm_mode="Sync + Tempo Blend",
        )

    # 4. Filter — Camelot конфликт (маскирует гармонический клэш)
    if camelot_dist >= 3:
        bpm_mode = "Sync + Tempo Blend" if bpm_diff > 4.0 else "Sync"
        return TransitionRecommendation(
            transition_type=TransitionType.FILTER,
            confidence=0.75,
            reason=(
                f"Camelot distance {camelot_dist} — LPF/HPF sweep маскирует гармонический конфликт"
            ),
            djay_bars=8,
            djay_bpm_mode=bpm_mode,
        )

    # 5. Echo — мелодичный/atmospheric трек или конец сета
    if track_a.hp_ratio > 2.5 or set_position > 0.85 or track_a.centroid_hz < 2200.0:
        return TransitionRecommendation(
            transition_type=TransitionType.ECHO,
            confidence=0.75,
            reason="Мелодичный/atmospheric трек — reverb хвост создаёт плавный уход",
            djay_bars=16,
            djay_bpm_mode="Sync",
        )

    # 6. Repeater — гипнотические переходы в середине сета
    if track_a.onset_rate > 5.5 and track_a.kick_prominence > 0.8 and 0.2 < set_position < 0.7:
        return TransitionRecommendation(
            transition_type=TransitionType.REPEATER,
            confidence=0.70,
            reason=(
                f"Высокий onset rate {track_a.onset_rate:.1f}/s — "
                f"лупинг последних баров создаёт гипнотическое ожидание"
            ),
            djay_bars=8,
            djay_bpm_mode="Sync",
        )

    # 7. Beat Match — fallback для любой ситуации
    return TransitionRecommendation(
        transition_type=TransitionType.BEAT_MATCH,
        confidence=0.60,
        reason="Стандартный битматч кроссфейд",
        djay_bars=16,
        djay_bpm_mode="Automatic",
    )
