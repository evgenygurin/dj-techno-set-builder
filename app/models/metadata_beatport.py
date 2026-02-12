from datetime import date
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BeatportMetadata(TimestampMixin, Base):
    __tablename__ = "beatport_metadata"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    beatport_track_id: Mapped[str] = mapped_column(String(100), unique=True)
    beatport_release_id: Mapped[str | None] = mapped_column(String(100))
    bpm: Mapped[float | None] = mapped_column(Float)
    key_code: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("key_code BETWEEN 0 AND 23", name="ck_beatport_key_code"),
    )
    length_ms: Mapped[int | None]
    label_name: Mapped[str | None] = mapped_column(String(300))
    genre_name: Mapped[str | None] = mapped_column(String(200))
    subgenre_name: Mapped[str | None] = mapped_column(String(200))
    release_date: Mapped[date | None]
    preview_url: Mapped[str | None] = mapped_column(String(500))
    image_url: Mapped[str | None] = mapped_column(String(500))
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)
