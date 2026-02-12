from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        UniqueConstraint(
            "track_id",
            "asset_type",
            "source_run_id",
            name="uq_audio_assets_track_type_run",
        ),
    )

    asset_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    asset_type: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("asset_type BETWEEN 0 AND 5", name="ck_audio_assets_type"),
    )
    storage_uri: Mapped[str] = mapped_column(String(500))
    format: Mapped[str] = mapped_column(String(20))
    sample_rate: Mapped[int | None]
    channels: Mapped[int | None] = mapped_column(SmallInteger)
    duration_ms: Mapped[int | None]
    file_size: Mapped[int | None]
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_extraction_runs.run_id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
