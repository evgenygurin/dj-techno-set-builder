"""SQLAlchemy ORM models generated from schema_v6.sql."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base
from app.models.common import (
    Int4RangeType,
    VectorType,
    ensure_float_range,
    ensure_int_range,
    ensure_non_negative,
    ensure_non_negative_float,
    ensure_one_of,
    ensure_positive,
)


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        UniqueConstraint(
            "track_id", "asset_type", "source_run_id", name="audio_assets_uq"
        ),
        ForeignKeyConstraint(
            ["source_run_id"],
            ["feature_extraction_runs.run_id"],
            name="fk_audio_assets_source_run",
            ondelete="SET NULL",
        ),
        Index("idx_audio_assets_track", "track_id", "asset_type"),
    )
    asset_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    storage_uri: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    format: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    sample_rate: Mapped[int | None] = mapped_column(
        Integer,
    )
    channels: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    source_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    checksum_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("asset_type")
    def _validate_asset_type(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=0, max_value=5)
        assert checked is not None
        return checked


class FeatureExtractionRun(Base):
    __tablename__ = "feature_extraction_runs"
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    pipeline_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    pipeline_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    parameters: Mapped[Any] = mapped_column(
        JSON,
    )
    code_ref: Mapped[str | None] = mapped_column(
        Text,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'running'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("status")
    def _validate_status(self, key: str, value: str) -> str:
        checked = ensure_one_of(key, value, ("running", "completed", "failed"))
        assert checked is not None
        return checked


class TransitionRun(Base):
    __tablename__ = "transition_runs"
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    pipeline_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    pipeline_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    weights: Mapped[Any] = mapped_column(
        JSON,
    )
    constraints: Mapped[Any] = mapped_column(
        JSON,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'running'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("status")
    def _validate_status(self, key: str, value: str) -> str:
        checked = ensure_one_of(key, value, ("running", "completed", "failed"))
        assert checked is not None
        return checked


class Key(Base):
    __tablename__ = "keys"
    __table_args__ = (
        CheckConstraint(
            "key_code = pitch_class * 2 + mode", name="keys_code_deterministic"
        ),
    )
    key_code: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        nullable=False,
    )
    pitch_class: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    mode: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    camelot: Mapped[str | None] = mapped_column(
        Text,
    )

    @validates("key_code", "pitch_class", "mode")
    def _validate_key_fields(self, key: str, value: int) -> int:
        if key == "key_code":
            checked = ensure_int_range(key, value, min_value=0, max_value=23)
        elif key == "pitch_class":
            checked = ensure_int_range(key, value, min_value=0, max_value=11)
        else:
            checked = ensure_one_of(key, value, (0, 1))
        assert checked is not None

        key_code = checked if key == "key_code" else self.key_code
        pitch_class = checked if key == "pitch_class" else self.pitch_class
        mode = checked if key == "mode" else self.mode
        if key_code is not None and pitch_class is not None and mode is not None:
            if key_code != pitch_class * 2 + mode:
                raise ValueError("key_code must be equal to pitch_class * 2 + mode")
        return checked


class KeyEdge(Base):
    __tablename__ = "key_edges"
    from_key_code: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("keys.key_code"),
        primary_key=True,
        nullable=False,
    )
    to_key_code: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("keys.key_code"),
        primary_key=True,
        nullable=False,
    )
    distance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    rule: Mapped[str | None] = mapped_column(
        Text,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TrackAudioFeatureComputed(Base):
    __tablename__ = "track_audio_features_computed"
    __table_args__ = (
        Index(
            "idx_taf_chroma",
            "chroma",
            postgresql_using="hnsw",
            postgresql_ops={"chroma": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 200},
        ),
        Index("idx_taf_bpm", "bpm"),
        Index("idx_taf_key", "key_code", text("key_confidence DESC")),
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    bpm: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    tempo_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    bpm_stability: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    is_variable_tempo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    lufs_i: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    lufs_s_mean: Mapped[float | None] = mapped_column(
        Float,
    )
    lufs_m_max: Mapped[float | None] = mapped_column(
        Float,
    )
    rms_dbfs: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    true_peak_db: Mapped[float | None] = mapped_column(
        Float,
    )
    crest_factor_db: Mapped[float | None] = mapped_column(
        Float,
    )
    lra_lu: Mapped[float | None] = mapped_column(
        Float,
    )
    energy_mean: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    energy_max: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    energy_std: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    energy_slope_mean: Mapped[float | None] = mapped_column(
        Float,
    )
    sub_energy: Mapped[float | None] = mapped_column(
        Float,
    )
    low_energy: Mapped[float | None] = mapped_column(
        Float,
    )
    lowmid_energy: Mapped[float | None] = mapped_column(
        Float,
    )
    mid_energy: Mapped[float | None] = mapped_column(
        Float,
    )
    highmid_energy: Mapped[float | None] = mapped_column(
        Float,
    )
    high_energy: Mapped[float | None] = mapped_column(
        Float,
    )
    low_high_ratio: Mapped[float | None] = mapped_column(
        Float,
    )
    sub_lowmid_ratio: Mapped[float | None] = mapped_column(
        Float,
    )
    centroid_mean_hz: Mapped[float | None] = mapped_column(
        Float,
    )
    rolloff_85_hz: Mapped[float | None] = mapped_column(
        Float,
    )
    rolloff_95_hz: Mapped[float | None] = mapped_column(
        Float,
    )
    flatness_mean: Mapped[float | None] = mapped_column(
        Float,
    )
    flux_mean: Mapped[float | None] = mapped_column(
        Float,
    )
    flux_std: Mapped[float | None] = mapped_column(
        Float,
    )
    slope_db_per_oct: Mapped[float | None] = mapped_column(
        Float,
    )
    contrast_mean_db: Mapped[float | None] = mapped_column(
        Float,
    )
    key_code: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("keys.key_code"),
        nullable=False,
    )
    key_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    is_atonal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    chroma: Mapped[Any] = mapped_column(
        VectorType(12),
    )
    hnr_mean_db: Mapped[float | None] = mapped_column(
        Float,
    )
    hp_ratio: Mapped[float | None] = mapped_column(
        Float,
    )
    onset_rate_mean: Mapped[float | None] = mapped_column(
        Float,
    )
    onset_rate_max: Mapped[float | None] = mapped_column(
        Float,
    )
    pulse_clarity: Mapped[float | None] = mapped_column(
        Float,
    )
    kick_prominence: Mapped[float | None] = mapped_column(
        Float,
    )
    computed_from_asset_type: Mapped[int | None] = mapped_column(
        SmallInteger,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("bpm")
    def _validate_bpm(self, key: str, value: float) -> float:
        checked = ensure_float_range(key, value, min_value=20.0, max_value=300.0)
        assert checked is not None
        return checked

    @validates("tempo_confidence", "bpm_stability", "key_confidence")
    def _validate_unit_confidence(self, key: str, value: float) -> float:
        checked = ensure_float_range(key, value, min_value=0.0, max_value=1.0)
        assert checked is not None
        return checked

    @validates("key_code")
    def _validate_key_code(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=0, max_value=23)
        assert checked is not None
        return checked

    @validates("computed_from_asset_type")
    def _validate_computed_from_asset_type(
        self, key: str, value: int | None
    ) -> int | None:
        return ensure_int_range(key, value, min_value=0, max_value=5)


class TrackSection(Base):
    __tablename__ = "track_sections"
    __table_args__ = (
        CheckConstraint(
            "NOT upper_inf(range_ms) AND NOT lower_inf(range_ms)",
            name="sections_range_bounded",
        ),
        CheckConstraint(
            "section_duration_ms = upper(range_ms) - lower(range_ms)",
            name="sections_duration_matches_range",
        ),
        UniqueConstraint("section_id", "track_id", name="sections_track_uq"),
        Index(
            "idx_sections_track_range",
            "track_id",
            "range_ms",
            postgresql_using="gist",
        ),
        Index("idx_sections_track_run", "track_id", "run_id"),
    )
    section_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    range_ms: Mapped[Any] = mapped_column(
        Int4RangeType(),
        nullable=False,
    )
    section_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    section_duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    section_energy_mean: Mapped[float | None] = mapped_column(
        Float,
    )
    section_energy_max: Mapped[float | None] = mapped_column(
        Float,
    )
    section_energy_slope: Mapped[float | None] = mapped_column(
        Float,
    )
    section_centroid_hz: Mapped[float | None] = mapped_column(
        Float,
    )
    section_flux: Mapped[float | None] = mapped_column(
        Float,
    )
    section_onset_rate: Mapped[float | None] = mapped_column(
        Float,
    )
    section_pulse_clarity: Mapped[float | None] = mapped_column(
        Float,
    )
    boundary_confidence: Mapped[float | None] = mapped_column(
        Float,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("section_type")
    def _validate_section_type(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=0, max_value=11)
        assert checked is not None
        return checked

    @validates("section_duration_ms")
    def _validate_section_duration_ms(self, key: str, value: int) -> int:
        checked = ensure_positive(key, value)
        assert checked is not None
        return checked


class TrackTimeseriesRef(Base):
    __tablename__ = "track_timeseries_refs"
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    feature_set: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        nullable=False,
    )
    storage_uri: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    frame_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    hop_length: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    sample_rate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    dtype: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'float32'"),
    )
    shape: Mapped[str | None] = mapped_column(
        Text,
    )
    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TransitionCandidate(Base):
    __tablename__ = "transition_candidates"
    __table_args__ = (
        CheckConstraint("from_track_id <> to_track_id", name="candidates_direction"),
        Index(
            "idx_candidates_from",
            "from_track_id",
            "bpm_distance",
            "key_distance",
            postgresql_where=text("is_fully_scored = false"),
        ),
        Index(
            "idx_candidates_to",
            "to_track_id",
            postgresql_where=text("is_fully_scored = false"),
        ),
    )
    from_track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    to_track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("transition_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    bpm_distance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    key_distance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    embedding_similarity: Mapped[float | None] = mapped_column(
        Float,
    )
    energy_delta: Mapped[float | None] = mapped_column(
        Float,
    )
    is_fully_scored: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("from_track_id", "to_track_id")
    def _validate_direction(self, key: str, value: int) -> int:
        other = self.to_track_id if key == "from_track_id" else self.from_track_id
        if other is not None and other == value:
            raise ValueError("from_track_id and to_track_id must be different")
        return value

    @validates("bpm_distance", "key_distance")
    def _validate_non_negative_distance(self, key: str, value: float) -> float:
        checked = ensure_non_negative_float(key, value)
        assert checked is not None
        return checked


class Transition(Base):
    __tablename__ = "transitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["from_section_id", "from_track_id"],
            ["track_sections.section_id", "track_sections.track_id"],
            name="fk_from_section",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["to_section_id", "to_track_id"],
            ["track_sections.section_id", "track_sections.track_id"],
            name="fk_to_section",
            ondelete="SET NULL",
        ),
        UniqueConstraint(
            "from_track_id",
            "to_track_id",
            "from_section_id",
            "to_section_id",
            "run_id",
            name="transitions_uq",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("from_track_id <> to_track_id", name="transitions_direction"),
        Index(
            "idx_transitions_from_quality",
            "from_track_id",
            text("transition_quality DESC"),
        ),
        Index(
            "idx_transitions_to_quality", "to_track_id", text("transition_quality DESC")
        ),
        Index(
            "idx_transitions_feature",
            "trans_feature",
            postgresql_using="hnsw",
            postgresql_ops={"trans_feature": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 200},
        ),
    )
    transition_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("transition_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    from_track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    to_track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    from_section_id: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    to_section_id: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    overlap_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    bpm_distance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    energy_step: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    centroid_gap_hz: Mapped[float | None] = mapped_column(
        Float,
    )
    low_conflict_score: Mapped[float | None] = mapped_column(
        Float,
    )
    overlap_score: Mapped[float | None] = mapped_column(
        Float,
    )
    groove_similarity: Mapped[float | None] = mapped_column(
        Float,
    )
    key_distance_weighted: Mapped[float | None] = mapped_column(
        Float,
    )
    transition_quality: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    trans_feature: Mapped[Any] = mapped_column(
        VectorType(32),
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("from_track_id", "to_track_id")
    def _validate_direction(self, key: str, value: int) -> int:
        other = self.to_track_id if key == "from_track_id" else self.from_track_id
        if other is not None and other == value:
            raise ValueError("from_track_id and to_track_id must be different")
        return value

    @validates("overlap_ms")
    def _validate_overlap_ms(self, key: str, value: int) -> int:
        checked = ensure_non_negative(key, value)
        assert checked is not None
        return checked


class EmbeddingType(Base):
    __tablename__ = "embedding_types"
    embedding_type: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        nullable=False,
    )
    dim: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    model_name: Mapped[str | None] = mapped_column(
        Text,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TrackEmbedding(Base):
    __tablename__ = "track_embeddings"
    __table_args__ = (
        UniqueConstraint("track_id", "embedding_type", "run_id", name="embeddings_uq"),
        Index("idx_embeddings_type", "embedding_type", "track_id"),
    )
    embedding_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
    )
    embedding_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey("embedding_types.embedding_type"),
        nullable=False,
    )
    vector: Mapped[Any] = mapped_column(
        VectorType(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
