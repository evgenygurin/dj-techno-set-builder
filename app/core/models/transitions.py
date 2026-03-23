from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import Base


class TransitionCandidate(Base):
    __tablename__ = "transition_candidates"
    __table_args__ = (
        CheckConstraint(
            "from_track_id <> to_track_id",
            name="ck_candidates_direction",
        ),
    )

    from_track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    to_track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("transition_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    bpm_distance: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("bpm_distance >= 0", name="ck_candidates_bpm_dist"),
    )
    key_distance: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("key_distance >= 0", name="ck_candidates_key_dist"),
    )
    embedding_similarity: Mapped[float | None] = mapped_column(Float)
    energy_delta: Mapped[float | None] = mapped_column(Float)
    is_fully_scored: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Transition(Base):
    __tablename__ = "transitions"
    __table_args__ = (
        CheckConstraint(
            "from_track_id <> to_track_id",
            name="ck_transitions_direction",
        ),
    )

    transition_id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("transition_runs.run_id", ondelete="CASCADE"),
    )
    from_track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
    )
    to_track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
    )
    from_section_id: Mapped[int | None]
    to_section_id: Mapped[int | None]

    # Scoring components
    overlap_ms: Mapped[int] = mapped_column(
        CheckConstraint("overlap_ms >= 0", name="ck_transitions_overlap"),
    )
    bpm_distance: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("bpm_distance >= 0", name="ck_transitions_bpm_dist"),
    )
    energy_step: Mapped[float] = mapped_column(Float)
    centroid_gap_hz: Mapped[float | None] = mapped_column(Float)
    low_conflict_score: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint(
            "low_conflict_score BETWEEN 0 AND 1",
            name="ck_transitions_low_conflict",
        ),
    )
    overlap_score: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("overlap_score BETWEEN 0 AND 1", name="ck_transitions_overlap_score"),
    )
    groove_similarity: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint(
            "groove_similarity BETWEEN 0 AND 1",
            name="ck_transitions_groove_sim",
        ),
    )
    key_distance_weighted: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint(
            "key_distance_weighted >= 0",
            name="ck_transitions_key_dist_weighted",
        ),
    )
    transition_quality: Mapped[float] = mapped_column(
        Float,
        CheckConstraint(
            "transition_quality BETWEEN 0 AND 1",
            name="ck_transitions_quality",
        ),
    )
    # trans_feature vector(32) — pgvector only, String placeholder for SQLite
    trans_feature: Mapped[str | None] = mapped_column(String(500))
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
