from datetime import datetime

from sqlalchemy import CheckConstraint, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Track(TimestampMixin, Base):
    __tablename__ = "tracks"

    track_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    title_sort: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[int] = mapped_column(
        CheckConstraint("duration_ms > 0", name="ck_tracks_duration_positive"),
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("status IN (0, 1)", name="ck_tracks_status_valid"),
        default=0,
    )
    archived_at: Mapped[datetime | None] = mapped_column(default=None)


class Artist(TimestampMixin, Base):
    __tablename__ = "artists"

    artist_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    name_sort: Mapped[str | None] = mapped_column(String(300))
