"""Convert ORM audio features to domain types.

Single source of truth — every call-site that needs ORM → TrackFeatures
or ORM → TrackData must go through these functions to prevent drift.

Defaults are centralised in ``_DEFAULTS`` to avoid magic numbers scattered
across the conversion logic.
"""

from __future__ import annotations

import contextlib
import json as _json
from typing import TYPE_CHECKING, Any

from app.models.enums import SectionType
from app.services.transition_scoring import TrackFeatures
from app.utils.audio.energy_arcs import lufs_to_energy
from app.utils.audio.mood_classifier import classify_track
from app.utils.audio.set_generator import TrackData

if TYPE_CHECKING:
    from app.models.features import TrackAudioFeaturesComputed
    from app.models.sections import TrackSection

# Centralised fallback defaults for Phase-2 nullable ORM fields.
# Each value is the neutral/median assumption when the real value is missing.
_DEFAULTS: dict[str, float] = {
    "onset_rate": 5.0,  # P50 onset_rate_mean — moderate rhythmic density
    "kick_prominence": 0.5,  # neutral kick presence (mid-range)
    "hnr_db": 0.0,  # 0 dB HNR — equal harmonic/noise energy
    "spectral_slope": 0.0,  # flat spectrum — no tilt assumption
    "hp_ratio": 2.0,  # P50 for techno ~2.2 (harmonic-dominant); was 0.5 (BUG)
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


# Centralised fallback defaults for mood classification.
# Values are P50 medians from real techno data (N=583).
_CLASSIFY_DEFAULTS: dict[str, float] = {
    "kick_prominence": 0.5,
    "spectral_centroid_mean": 2500.0,
    "onset_rate": 5.0,
    "hp_ratio": 2.0,  # P50 for techno ~2.2; NOT 0.5
    "flux_mean": 0.18,
    "flux_std": 0.10,
    "energy_std": 0.13,
    "energy_mean": 0.22,
    "lra_lu": 6.6,
    "crest_factor_db": 13.3,
    "flatness_mean": 0.06,
}


def orm_to_track_data(
    feat: TrackAudioFeaturesComputed | Any,
    artist_id: int = 0,
) -> TrackData:
    """Convert a features object to ``TrackData`` with mood classification.

    Accepts both ORM ``TrackAudioFeaturesComputed`` and Pydantic
    ``AudioFeaturesRead`` — any object with matching attribute names.

    Single source of truth — replaces 3+ duplicated inline patterns across
    ``set_generation.py``, ``mcp/tools/setbuilder.py``, ``mcp/tools/curation.py``,
    and ``services/set_curation.py``.

    Uses the FULL 13-parameter ``classify_track()`` call with correct defaults
    (fixes hp_ratio bug: was 0.5 in some call-sites, should be 2.0).
    """

    def _g(attr: str, default: float) -> float:
        """Get float attr from feat, falling back to default if missing/non-numeric."""
        val = getattr(feat, attr, None)
        return val if isinstance(val, (int, float)) else default

    d = _CLASSIFY_DEFAULTS
    classification = classify_track(
        bpm=feat.bpm,
        lufs_i=feat.lufs_i,
        kick_prominence=_g("kick_prominence", d["kick_prominence"]),
        spectral_centroid_mean=_g("centroid_mean_hz", d["spectral_centroid_mean"]),
        onset_rate=_g("onset_rate_mean", d["onset_rate"]),
        hp_ratio=_g("hp_ratio", d["hp_ratio"]),
        flux_mean=_g("flux_mean", d["flux_mean"]),
        flux_std=_g("flux_std", d["flux_std"]),
        energy_std=_g("energy_std", d["energy_std"]),
        energy_mean=_g("energy_mean", d["energy_mean"]),
        lra_lu=_g("lra_lu", d["lra_lu"]),
        crest_factor_db=_g("crest_factor_db", d["crest_factor_db"]),
        flatness_mean=_g("flatness_mean", d["flatness_mean"]),
    )

    return TrackData(
        track_id=feat.track_id,
        bpm=feat.bpm,
        energy=lufs_to_energy(feat.lufs_i),
        key_code=feat.key_code or 0,
        mood=classification.mood.intensity,
        artist_id=artist_id,
    )
