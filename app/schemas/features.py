from datetime import datetime

from app.schemas.base import BaseSchema


class AudioFeaturesRead(BaseSchema):
    track_id: int
    run_id: int
    # Tempo
    bpm: float
    tempo_confidence: float
    bpm_stability: float
    is_variable_tempo: bool
    # Loudness
    lufs_i: float
    lufs_s_mean: float | None = None
    lufs_m_max: float | None = None
    rms_dbfs: float
    true_peak_db: float | None = None
    crest_factor_db: float | None = None
    lra_lu: float | None = None
    # Energy
    energy_mean: float
    energy_max: float
    energy_std: float | None = None
    energy_slope_mean: float | None = None
    # Band energies
    sub_energy: float | None = None
    low_energy: float | None = None
    lowmid_energy: float | None = None
    mid_energy: float | None = None
    highmid_energy: float | None = None
    high_energy: float | None = None
    low_high_ratio: float | None = None
    sub_lowmid_ratio: float | None = None
    # Spectral
    centroid_mean_hz: float | None = None
    rolloff_85_hz: float | None = None
    rolloff_95_hz: float | None = None
    flatness_mean: float | None = None
    flux_mean: float | None = None
    flux_std: float | None = None
    contrast_mean_db: float | None = None
    # Tonal
    key_code: int
    key_confidence: float
    is_atonal: bool
    # Rhythm (optional, Phase 2)
    hp_ratio: float | None = None
    onset_rate_mean: float | None = None
    onset_rate_max: float | None = None
    pulse_clarity: float | None = None
    kick_prominence: float | None = None
    # Meta
    created_at: datetime


class AudioFeaturesList(BaseSchema):
    items: list[AudioFeaturesRead]
    total: int
