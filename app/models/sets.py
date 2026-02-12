from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DjSet(TimestampMixin, Base):
    __tablename__ = "dj_sets"

    set_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None]
    target_duration_ms: Mapped[int | None] = mapped_column(
        CheckConstraint("target_duration_ms > 0", name="ck_sets_duration"),
    )
    target_bpm_min: Mapped[float | None] = mapped_column(Float)
    target_bpm_max: Mapped[float | None] = mapped_column(Float)
    target_energy_arc: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class DjSetVersion(Base):
    __tablename__ = "dj_set_versions"

    set_version_id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("dj_sets.set_id", ondelete="CASCADE"))
    version_label: Mapped[str | None] = mapped_column(String(100))
    generator_run: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DjSetConstraint(Base):
    __tablename__ = "dj_set_constraints"

    constraint_id: Mapped[int] = mapped_column(primary_key=True)
    set_version_id: Mapped[int] = mapped_column(
        ForeignKey("dj_set_versions.set_version_id", ondelete="CASCADE"),
    )
    constraint_type: Mapped[str] = mapped_column(String(100))
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DjSetItem(Base):
    __tablename__ = "dj_set_items"
    __table_args__ = (UniqueConstraint("set_version_id", "sort_index", name="uq_set_items_sort"),)

    set_item_id: Mapped[int] = mapped_column(primary_key=True)
    set_version_id: Mapped[int] = mapped_column(
        ForeignKey("dj_set_versions.set_version_id", ondelete="CASCADE"),
    )
    sort_index: Mapped[int] = mapped_column(
        CheckConstraint("sort_index >= 0", name="ck_set_items_sort"),
    )
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    transition_id: Mapped[int | None] = mapped_column(
        ForeignKey("transitions.transition_id", ondelete="SET NULL"),
    )
    in_section_id: Mapped[int | None]
    out_section_id: Mapped[int | None]
    mix_in_ms: Mapped[int | None] = mapped_column(
        CheckConstraint("mix_in_ms >= 0", name="ck_set_items_mix_in"),
    )
    mix_out_ms: Mapped[int | None] = mapped_column(
        CheckConstraint("mix_out_ms >= 0", name="ck_set_items_mix_out"),
    )
    planned_eq: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DjSetFeedback(Base):
    __tablename__ = "dj_set_feedback"

    feedback_id: Mapped[int] = mapped_column(primary_key=True)
    set_version_id: Mapped[int] = mapped_column(
        ForeignKey("dj_set_versions.set_version_id", ondelete="CASCADE"),
    )
    set_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("dj_set_items.set_item_id", ondelete="CASCADE"),
    )
    rating: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("rating BETWEEN -1 AND 5", name="ck_feedback_rating"),
    )
    feedback_type: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "feedback_type IN ('manual', 'live_crowd', 'a_b_test')",
            name="ck_feedback_type",
        ),
        default="manual",
    )
    notes: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
