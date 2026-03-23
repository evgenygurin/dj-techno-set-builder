"""Techno audio quality criteria — pure validation logic.

Checks track audio features against established techno production standards.
No DB, no framework deps — just thresholds and reasons.
"""

from __future__ import annotations

from typing import Any


def audit_track_features(feat: Any) -> list[str]:
    """Check a single track's features against techno criteria.

    Args:
        feat: Object with audio feature attributes (ORM or Pydantic).

    Returns:
        List of failure reasons (empty = passed).
    """
    reasons: list[str] = []

    # BPM: 120-155
    if feat.bpm < 120:
        reasons.append(f"BPM {feat.bpm:.1f} < 120")
    elif feat.bpm > 155:
        reasons.append(f"BPM {feat.bpm:.1f} > 155")

    # LUFS: -20 to -4
    if feat.lufs_i < -20:
        reasons.append(f"LUFS {feat.lufs_i:.1f} < -20")
    elif feat.lufs_i > -4:
        reasons.append(f"LUFS {feat.lufs_i:.1f} > -4")

    # energy_mean > 0.05
    if feat.energy_mean <= 0.05:
        reasons.append(f"energy {feat.energy_mean:.3f} <= 0.05")

    # onset_rate_mean > 1.0
    if getattr(feat, "onset_rate_mean", None) is not None and feat.onset_rate_mean <= 1.0:
        reasons.append(f"onset_rate {feat.onset_rate_mean:.2f} <= 1.0")

    # kick_prominence > 0.05
    if getattr(feat, "kick_prominence", None) is not None and feat.kick_prominence <= 0.05:
        reasons.append(f"kick {feat.kick_prominence:.3f} <= 0.05")

    # centroid: 300-10000 Hz
    centroid = getattr(feat, "centroid_mean_hz", None)
    if centroid is not None:
        if centroid < 300:
            reasons.append(f"centroid {centroid:.0f}Hz < 300")
        elif centroid > 10000:
            reasons.append(f"centroid {centroid:.0f}Hz > 10000")

    # flatness < 0.5
    if getattr(feat, "flatness_mean", None) is not None and feat.flatness_mean >= 0.5:
        reasons.append(f"flatness {feat.flatness_mean:.3f} >= 0.5")

    # tempo_confidence > 0.3
    if feat.tempo_confidence <= 0.3:
        reasons.append(f"tempo_conf {feat.tempo_confidence:.2f} <= 0.3")

    # bpm_stability > 0.3
    if feat.bpm_stability <= 0.3:
        reasons.append(f"bpm_stab {feat.bpm_stability:.2f} <= 0.3")

    # pulse_clarity > 0.02
    if getattr(feat, "pulse_clarity", None) is not None and feat.pulse_clarity <= 0.02:
        reasons.append(f"pulse {feat.pulse_clarity:.3f} <= 0.02")

    # hp_ratio < 8.0
    if getattr(feat, "hp_ratio", None) is not None and feat.hp_ratio >= 8.0:
        reasons.append(f"hp_ratio {feat.hp_ratio:.2f} >= 8.0")

    return reasons
