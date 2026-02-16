"""Convert ORM audio features to TransitionScoringService TrackFeatures.

Single source of truth — every call-site that needs ORM → TrackFeatures
must go through this function to prevent drift between scoring paths.
"""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING

from app.services.transition_scoring import TrackFeatures

if TYPE_CHECKING:
    from app.models.features import TrackAudioFeaturesComputed


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
        kick_prominence=feat.kick_prominence if feat.kick_prominence is not None else 0.5,
        hnr_db=feat.hnr_mean_db if feat.hnr_mean_db is not None else 0.0,
        spectral_slope=feat.slope_db_per_oct if feat.slope_db_per_oct is not None else 0.0,
    )
