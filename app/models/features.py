from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TrackAudioFeaturesComputed(Base):
    __tablename__ = "track_audio_features_computed"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # -- Tempo --
    bpm: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("bpm BETWEEN 20 AND 300", name="ck_taf_bpm"),
    )
    tempo_confidence: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("tempo_confidence BETWEEN 0 AND 1", name="ck_taf_tempo_conf"),
    )
    bpm_stability: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("bpm_stability BETWEEN 0 AND 1", name="ck_taf_bpm_stability"),
    )
    is_variable_tempo: Mapped[bool] = mapped_column(Boolean, server_default="0")

    # -- Loudness (EBU R128) --
    lufs_i: Mapped[float] = mapped_column(Float)
    lufs_s_mean: Mapped[float | None] = mapped_column(Float)
    lufs_m_max: Mapped[float | None] = mapped_column(Float)
    rms_dbfs: Mapped[float] = mapped_column(Float)
    true_peak_db: Mapped[float | None] = mapped_column(Float)
    crest_factor_db: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("crest_factor_db >= 0", name="ck_taf_crest_factor"),
    )
    lra_lu: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("lra_lu >= 0", name="ck_taf_lra"),
    )

    # -- Energy (global aggregates) --
    energy_mean: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("energy_mean BETWEEN 0 AND 1", name="ck_taf_energy_mean"),
    )
    energy_max: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("energy_max BETWEEN 0 AND 1", name="ck_taf_energy_max"),
    )
    energy_std: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("energy_std >= 0", name="ck_taf_energy_std"),
    )
    energy_slope_mean: Mapped[float | None] = mapped_column(Float)

    # -- Band energies (normalized 0..1) --
    sub_energy: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("sub_energy BETWEEN 0 AND 1", name="ck_taf_sub_energy"),
    )
    low_energy: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("low_energy BETWEEN 0 AND 1", name="ck_taf_low_energy"),
    )
    lowmid_energy: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("lowmid_energy BETWEEN 0 AND 1", name="ck_taf_lowmid_energy"),
    )
    mid_energy: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("mid_energy BETWEEN 0 AND 1", name="ck_taf_mid_energy"),
    )
    highmid_energy: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("highmid_energy BETWEEN 0 AND 1", name="ck_taf_highmid_energy"),
    )
    high_energy: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("high_energy BETWEEN 0 AND 1", name="ck_taf_high_energy"),
    )
    low_high_ratio: Mapped[float | None] = mapped_column(Float)
    sub_lowmid_ratio: Mapped[float | None] = mapped_column(Float)

    # -- Spectral descriptors --
    centroid_mean_hz: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("centroid_mean_hz >= 0", name="ck_taf_centroid"),
    )
    rolloff_85_hz: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("rolloff_85_hz >= 0", name="ck_taf_rolloff_85"),
    )
    rolloff_95_hz: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("rolloff_95_hz >= 0", name="ck_taf_rolloff_95"),
    )
    flatness_mean: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("flatness_mean BETWEEN 0 AND 1", name="ck_taf_flatness"),
    )
    flux_mean: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("flux_mean >= 0", name="ck_taf_flux_mean"),
    )
    flux_std: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("flux_std >= 0", name="ck_taf_flux_std"),
    )
    slope_db_per_oct: Mapped[float | None] = mapped_column(Float)
    contrast_mean_db: Mapped[float | None] = mapped_column(Float)

    # -- Tonal / Harmonic --
    key_code: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("keys.key_code"),
        CheckConstraint("key_code BETWEEN 0 AND 23", name="ck_taf_key_code"),
    )
    key_confidence: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("key_confidence BETWEEN 0 AND 1", name="ck_taf_key_conf"),
    )
    is_atonal: Mapped[bool] = mapped_column(Boolean, server_default="0")
    # chroma vector(12) — pgvector only, String placeholder for SQLite compat
    chroma: Mapped[str | None] = mapped_column(String(500))
    hnr_mean_db: Mapped[float | None] = mapped_column(Float)

    # -- Rhythm / Groove --
    hp_ratio: Mapped[float | None] = mapped_column(Float)
    onset_rate_mean: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("onset_rate_mean >= 0", name="ck_taf_onset_rate_mean"),
    )
    onset_rate_max: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("onset_rate_max >= 0", name="ck_taf_onset_rate_max"),
    )
    pulse_clarity: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("pulse_clarity BETWEEN 0 AND 1", name="ck_taf_pulse_clarity"),
    )
    kick_prominence: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("kick_prominence BETWEEN 0 AND 1", name="ck_taf_kick_prominence"),
    )

    # -- Meta --
    computed_from_asset_type: Mapped[int | None] = mapped_column(SmallInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
