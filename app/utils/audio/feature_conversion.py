"""Convert ORM audio features to TransitionScoringService TrackFeatures.

Single source of truth — every call-site that needs ORM → TrackFeatures
must go through this function to prevent drift between scoring paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.transition_scoring import TrackFeatures

if TYPE_CHECKING:
    from app.models.features import TrackAudioFeaturesComputed


def orm_features_to_track_features(feat: TrackAudioFeaturesComputed) -> TrackFeatures:
    """Convert ``TrackAudioFeaturesComputed`` ORM row to ``TrackFeatures``.

    Mapping rules:
    * ``harmonic_density`` ← ``key_confidence`` (chroma entropy not yet in pipeline)
    * ``band_ratios`` ← normalised ``[low_energy, mid_energy, high_energy]``
    * ``onset_rate`` ← ``onset_rate_mean`` (Phase-2 field, fallback = 5.0)
    """
    harmonic_density = feat.key_confidence or 0.5

    low = feat.low_energy or 0.33
    mid = feat.mid_energy or 0.33
    high = feat.high_energy or 0.34
    total = low + mid + high
    band_ratios = [low / total, mid / total, high / total] if total > 0 else [0.33, 0.33, 0.34]

    return TrackFeatures(
        bpm=feat.bpm,
        energy_lufs=feat.lufs_i,
        key_code=feat.key_code if feat.key_code is not None else 0,
        harmonic_density=harmonic_density,
        centroid_hz=feat.centroid_mean_hz or 2000.0,
        band_ratios=band_ratios,
        onset_rate=feat.onset_rate_mean or 5.0,
    )
