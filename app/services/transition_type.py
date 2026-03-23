"""Transition type recommender for djay Pro Neural Mix.

Selects the best transition type from 10 djay Pro Crossfader FX options
based on audio features of the outgoing and incoming tracks.

Priority-based selection logic — first matching rule wins.
Pure function, no DB dependencies.
"""

from __future__ import annotations

from app.services.transition_scoring import TrackFeatures
from app.audio._types import TransitionRecommendation, TransitionType


def recommend_transition(
    track_a: TrackFeatures,
    track_b: TrackFeatures,
    *,
    camelot_compatible: bool,
) -> TransitionRecommendation:
    """Recommend a transition type for a track pair.

    Uses priority-based rules matching djay Pro Crossfader FX capabilities.
    First matching rule wins.

    Args:
        track_a: Outgoing track features.
        track_b: Incoming track features.
        camelot_compatible: Whether keys are Camelot-compatible (distance <= 1).

    Returns:
        TransitionRecommendation with type, confidence, reason, and optional alt.
    """
    bpm_diff = abs(track_a.bpm - track_b.bpm)
    energy_delta = track_a.energy_lufs - track_b.energy_lufs  # positive = A louder
    abs_energy_delta = abs(energy_delta)

    # Priority 1: Both drum-heavy → DRUM_CUT (remove kick clash)
    if track_a.kick_prominence > 0.6 and track_b.kick_prominence > 0.6:
        conf = min(track_a.kick_prominence, track_b.kick_prominence)
        return TransitionRecommendation(
            transition_type=TransitionType.DRUM_CUT,
            confidence=conf,
            reason=(
                f"Both tracks are drum-heavy "
                f"(kick {track_a.kick_prominence:.1f} / {track_b.kick_prominence:.1f})"
            ),
            alt_type=TransitionType.EQ,
        )

    # Priority 2: B drum-heavy, A melodic → DRUM_SWAP
    if track_b.kick_prominence > 0.6 and track_a.kick_prominence <= 0.6:
        conf = track_b.kick_prominence * 0.9
        return TransitionRecommendation(
            transition_type=TransitionType.DRUM_SWAP,
            confidence=conf,
            reason=(
                f"Track B has stronger kick ({track_b.kick_prominence:.1f} "
                f"vs {track_a.kick_prominence:.1f})"
            ),
            alt_type=TransitionType.EQ,
        )

    # Priority 3: Both melodic + Camelot match → HARMONIC_SUSTAIN
    avg_hnr = (track_a.hnr_db + track_b.hnr_db) / 2.0
    avg_density = (track_a.harmonic_density + track_b.harmonic_density) / 2.0
    if avg_hnr > 12.0 and avg_density > 0.6 and camelot_compatible:
        conf = min(avg_density, min(avg_hnr / 20.0, 1.0))
        return TransitionRecommendation(
            transition_type=TransitionType.HARMONIC_SUSTAIN,
            confidence=conf,
            reason=(
                f"Both melodic (HNR {avg_hnr:.0f} dB, density {avg_density:.2f}) "
                f"with compatible keys"
            ),
            alt_type=TransitionType.NEURAL_FADE,
        )

    # Priority 4: A has vocal → VOCAL_SUSTAIN
    if track_a.hp_ratio < 0.4:
        conf = 1.0 - track_a.hp_ratio  # lower ratio = higher confidence
        return TransitionRecommendation(
            transition_type=TransitionType.VOCAL_SUSTAIN,
            confidence=min(conf, 0.9),
            reason=f"Track A has vocal content (hp_ratio={track_a.hp_ratio:.2f})",
            alt_type=TransitionType.NEURAL_FADE,
        )

    # Priority 5: BPM diff > 4 → FILTER (mask tempo mismatch)
    if bpm_diff > 4.0:
        conf = min(bpm_diff / 10.0, 0.95)
        return TransitionRecommendation(
            transition_type=TransitionType.FILTER,
            confidence=conf,
            reason=f"BPM difference {bpm_diff:.1f} requires filter masking",
            alt_type=TransitionType.ECHO,
        )

    # Priority 6: High energy delta > 2 LUFS → NEURAL_ECHO_OUT
    if abs_energy_delta > 2.0:
        conf = min(abs_energy_delta / 6.0, 0.95)
        return TransitionRecommendation(
            transition_type=TransitionType.NEURAL_ECHO_OUT,
            confidence=conf,
            reason=f"Energy gap {abs_energy_delta:.1f} LUFS — smooth echo exit",
            alt_type=TransitionType.FILTER,
        )

    # Priority 7: Energy drops (A louder) → NEURAL_FADE
    if energy_delta > 0.5:
        conf = min(energy_delta / 3.0, 0.85)
        return TransitionRecommendation(
            transition_type=TransitionType.NEURAL_FADE,
            confidence=conf,
            reason=f"Energy drops {energy_delta:.1f} LUFS — delicate stem fadeout",
            alt_type=TransitionType.FADE,
        )

    # Priority 8: Both high-energy → EQ
    if track_a.energy_lufs > -9.0 and track_b.energy_lufs > -9.0:
        avg_lufs = (track_a.energy_lufs + track_b.energy_lufs) / 2.0
        conf = min((avg_lufs + 9.0) / 3.0 + 0.5, 0.9)
        return TransitionRecommendation(
            transition_type=TransitionType.EQ,
            confidence=max(conf, 0.5),
            reason=f"Both high-energy ({avg_lufs:.1f} LUFS avg) — classic bass-swap",
            alt_type=TransitionType.DRUM_CUT,
        )

    # Priority 9: Energy rises (B louder) → ECHO
    if energy_delta < -0.3:
        conf = min(abs(energy_delta) / 2.0, 0.8)
        return TransitionRecommendation(
            transition_type=TransitionType.ECHO,
            confidence=max(conf, 0.4),
            reason=f"Energy rises {abs(energy_delta):.1f} LUFS — echo entry",
            alt_type=TransitionType.FADE,
        )

    # Priority 10: Default → FADE
    return TransitionRecommendation(
        transition_type=TransitionType.FADE,
        confidence=0.5,
        reason="Default crossfade — no strong feature signal",
        alt_type=TransitionType.EQ,
    )
