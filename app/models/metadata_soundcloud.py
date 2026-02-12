from datetime import date
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SoundCloudMetadata(TimestampMixin, Base):
    __tablename__ = "soundcloud_metadata"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    soundcloud_track_id: Mapped[str] = mapped_column(String(100), unique=True)
    soundcloud_user_id: Mapped[str | None] = mapped_column(String(100))
    bpm: Mapped[int | None]
    key_signature: Mapped[str | None] = mapped_column(String(20))
    genre: Mapped[str | None] = mapped_column(String(200))
    duration_ms: Mapped[int | None]
    playback_count: Mapped[int | None]
    favoritings_count: Mapped[int | None]
    reposts_count: Mapped[int | None]
    comment_count: Mapped[int | None]
    downloadable: Mapped[bool | None] = mapped_column(Boolean)
    streamable: Mapped[bool | None] = mapped_column(Boolean)
    permalink_url: Mapped[str | None] = mapped_column(String(500))
    artwork_url: Mapped[str | None] = mapped_column(String(500))
    label_name: Mapped[str | None] = mapped_column(String(300))
    release_date: Mapped[date | None]
    is_explicit: Mapped[bool | None] = mapped_column(Boolean)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)
