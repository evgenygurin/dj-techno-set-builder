from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, SmallInteger, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import Base


class TrackSection(Base):
    __tablename__ = "track_sections"
    __table_args__ = (UniqueConstraint("section_id", "track_id", name="uq_sections_track"),)

    section_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    run_id: Mapped[int] = mapped_column(
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
    )
    # int4range in PG — use start_ms/end_ms pair for ORM (SQLite compat)
    start_ms: Mapped[int]
    end_ms: Mapped[int]
    section_type: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("section_type BETWEEN 0 AND 11", name="ck_sections_type"),
    )
    section_duration_ms: Mapped[int] = mapped_column(
        CheckConstraint("section_duration_ms > 0", name="ck_sections_duration_positive"),
    )

    # Per-section aggregates
    section_energy_mean: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("section_energy_mean BETWEEN 0 AND 1", name="ck_sections_energy_mean"),
    )
    section_energy_max: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("section_energy_max BETWEEN 0 AND 1", name="ck_sections_energy_max"),
    )
    section_energy_slope: Mapped[float | None] = mapped_column(Float)
    section_centroid_hz: Mapped[float | None] = mapped_column(Float)
    section_flux: Mapped[float | None] = mapped_column(Float)
    section_onset_rate: Mapped[float | None] = mapped_column(Float)
    section_pulse_clarity: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint(
            "section_pulse_clarity BETWEEN 0 AND 1",
            name="ck_sections_pulse_clarity",
        ),
    )
    boundary_confidence: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint(
            "boundary_confidence BETWEEN 0 AND 1",
            name="ck_sections_boundary_conf",
        ),
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
