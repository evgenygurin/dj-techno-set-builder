from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import Base, TimestampMixin


class ProviderTrackId(TimestampMixin, Base):
    __tablename__ = "provider_track_ids"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    provider_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("providers.provider_id"),
    )
    provider_track_id: Mapped[str] = mapped_column(String(200))
    provider_country: Mapped[str | None] = mapped_column(String(2))


class RawProviderResponse(Base):
    __tablename__ = "raw_provider_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    provider_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("providers.provider_id"),
    )
    provider_track_id: Mapped[str] = mapped_column(String(200))
    endpoint: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now())
