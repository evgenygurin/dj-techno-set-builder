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
            reason="Pre-peak build-up — frequency sweep creates tension",
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
