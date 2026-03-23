from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import Base, TimestampMixin


class YandexMetadata(TimestampMixin, Base):
    """Yandex Music track metadata — one row per track."""

    __tablename__ = "yandex_metadata"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    yandex_track_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    yandex_album_id: Mapped[str | None] = mapped_column(String(50))
    album_title: Mapped[str | None] = mapped_column(String(500))
    album_type: Mapped[str | None] = mapped_column(String(50))
    album_genre: Mapped[str | None] = mapped_column(String(100))
    album_year: Mapped[int | None] = mapped_column()
    label_name: Mapped[str | None] = mapped_column(String(300))
    release_date: Mapped[str | None] = mapped_column(String(10))
    duration_ms: Mapped[int | None] = mapped_column()
    cover_uri: Mapped[str | None] = mapped_column(String(500))
    explicit: Mapped[bool | None] = mapped_column(Boolean)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)
