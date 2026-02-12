"""SQLAlchemy ORM models generated from schema_v6.sql."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base
from app.models.common import (
    ensure_float_range,
    ensure_int_range,
    ensure_non_negative,
    ensure_one_of,
    ensure_positive,
)


class DjSet(Base):
    __tablename__ = "dj_sets"
    set_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
    )
    target_duration_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    target_bpm_min: Mapped[float | None] = mapped_column(
        Float,
    )
    target_bpm_max: Mapped[float | None] = mapped_column(
        Float,
    )
    target_energy_arc: Mapped[Any] = mapped_column(
        JSON,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("target_duration_ms")
    def _validate_target_duration_ms(self, key: str, value: int | None) -> int | None:
        return ensure_positive(key, value)


class DjSetVersion(Base):
    __tablename__ = "dj_set_versions"
    __table_args__ = (Index("idx_set_versions_set", "set_id"),)
    set_version_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    set_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dj_sets.set_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_label: Mapped[str | None] = mapped_column(
        Text,
    )
    generator_run: Mapped[Any] = mapped_column(
        JSON,
    )
    score: Mapped[float | None] = mapped_column(
        Float,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("score")
    def _validate_score(self, key: str, value: float | None) -> float | None:
        return ensure_float_range(key, value, min_value=0.0, max_value=1.0)


class DjSetConstraint(Base):
    __tablename__ = "dj_set_constraints"
    __table_args__ = (Index("idx_set_constraints_version", "set_version_id"),)
    constraint_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    set_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dj_set_versions.set_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    constraint_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    value: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DjSetItem(Base):
    __tablename__ = "dj_set_items"
    __table_args__ = (
        UniqueConstraint("set_version_id", "sort_index", name="set_items_sort_uq"),
        ForeignKeyConstraint(
            ["in_section_id", "track_id"],
            ["track_sections.section_id", "track_sections.track_id"],
            name="fk_set_item_in_section",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["out_section_id", "track_id"],
            ["track_sections.section_id", "track_sections.track_id"],
            name="fk_set_item_out_section",
            ondelete="SET NULL",
        ),
        Index("idx_set_items_version", "set_version_id"),
        Index("idx_set_items_track", "track_id"),
    )
    set_item_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    set_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dj_set_versions.set_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    transition_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("transitions.transition_id", ondelete="SET NULL"),
    )
    in_section_id: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    out_section_id: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    mix_in_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    mix_out_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    planned_eq: Mapped[Any] = mapped_column(
        JSON,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("sort_index", "mix_in_ms", "mix_out_ms")
    def _validate_non_negative_fields(self, key: str, value: int | None) -> int | None:
        return ensure_non_negative(key, value)


class DjSetFeedback(Base):
    __tablename__ = "dj_set_feedback"
    __table_args__ = (Index("idx_feedback_set", "set_version_id"),)
    feedback_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    set_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dj_set_versions.set_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    set_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dj_set_items.set_item_id", ondelete="CASCADE"),
    )
    rating: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    feedback_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'manual'"),
    )
    tags: Mapped[Any] = mapped_column(
        JSON,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("rating")
    def _validate_rating(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=-1, max_value=5)
        assert checked is not None
        return checked

    @validates("feedback_type")
    def _validate_feedback_type(self, key: str, value: str) -> str:
        checked = ensure_one_of(key, value, ("manual", "live_crowd", "a_b_test"))
        assert checked is not None
        return checked
