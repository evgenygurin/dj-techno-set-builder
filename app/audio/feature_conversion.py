"""Convert ORM audio features to TransitionScoringService TrackFeatures.

Single source of truth — every call-site that needs ORM → TrackFeatures
must go through this function to prevent drift between scoring paths.

Defaults are centralised in ``_DEFAULTS`` to avoid magic numbers scattered
across the conversion logic.
"""

from __future__ import annotations

import contextlib
import json as _json
from typing import TYPE_CHECKING

from app.core.models.enums import SectionType
from app.services.transition_scoring import TrackFeatures

if TYPE_CHECKING:
    from app.core.models.features import TrackAudioFeaturesComputed
    from app.core.models.sections import TrackSection

# Centralised fallback defaults for Phase-2 nullable ORM fields.
# Each value is the neutral/median assumption when the real value is missing.
_DEFAULTS: dict[str, float] = {
    "onset_rate": 5.0,  # P50 onset_rate_mean — moderate rhythmic density
    "kick_prominence": 0.5,  # neutral kick presence (mid-range)
    "hnr_db": 0.0,  # 0 dB HNR — equal harmonic/noise energy
    "spectral_slope": 0.0,  # flat spectrum — no tilt assumption
    "hp_ratio": 0.5,  # equal harmonic/percussive — neutral balance
}


def orm_features_to_track_features(
    feat: TrackAudioFeaturesComputed,
    sections: list[TrackSection] | None = None,
) -> TrackFeatures:
    """Convert ``TrackAudioFeaturesComputed`` ORM row to ``TrackFeatures``.

    Mapping rules:
    * ``harmonic_density`` ← ``chroma_entropy`` (fallback: ``key_confidence``)
    * ``band_ratios`` ← normalised ``[low_energy, mid_energy, high_energy]``
    * ``onset_rate`` ← ``onset_rate_mean`` (Phase-2 field, fallback = 5.0)
    * ``mfcc_vector`` ← JSON-parsed ``mfcc_vector`` (Phase-2, nullable)
    * ``kick_prominence`` ← ``kick_prominence`` (Phase-2, fallback = 0.5)
    * ``hnr_db`` ← ``hnr_mean_db`` (Phase-2, fallback = 0.0)
    * ``spectral_slope`` ← ``slope_db_per_oct`` (Phase-2, fallback = 0.0)
    * ``first_section`` / ``last_section`` ← sorted ``sections`` list (optional)
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

    # Section data: derive first/last section type names for structure scoring
    first_section: str | None = None
    last_section: str | None = None
    if sections:
        sorted_secs = sorted(sections, key=lambda s: s.start_ms)
        with contextlib.suppress(ValueError):
            first_section = SectionType(sorted_secs[0].section_type).name.lower()
        with contextlib.suppress(ValueError):
            last_section = SectionType(sorted_secs[-1].section_type).name.lower()

    return TrackFeatures(
        bpm=feat.bpm,
        energy_lufs=feat.lufs_i,
        key_code=feat.key_code if feat.key_code is not None else 0,
        harmonic_density=harmonic_density,
        centroid_hz=feat.centroid_mean_hz or 2000.0,
        band_ratios=band_ratios,
        onset_rate=feat.onset_rate_mean or _DEFAULTS["onset_rate"],
        mfcc_vector=mfcc_vector,
        kick_prominence=(
            feat.kick_prominence
            if feat.kick_prominence is not None
            else _DEFAULTS["kick_prominence"]
        ),
        hnr_db=(feat.hnr_mean_db if feat.hnr_mean_db is not None else _DEFAULTS["hnr_db"]),
        spectral_slope=(
            feat.slope_db_per_oct
            if feat.slope_db_per_oct is not None
            else _DEFAULTS["spectral_slope"]
        ),
        hp_ratio=(feat.hp_ratio if feat.hp_ratio is not None else _DEFAULTS["hp_ratio"]),
        first_section=first_section,
        last_section=last_section,
    )
