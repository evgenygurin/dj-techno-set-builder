from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import Base


class TrackTimeseriesRef(Base):
    __tablename__ = "track_timeseries_refs"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    feature_set: Mapped[str] = mapped_column(String(100), primary_key=True)
    storage_uri: Mapped[str] = mapped_column(String(500))
    frame_count: Mapped[int] = mapped_column(
        CheckConstraint("frame_count > 0", name="ck_timeseries_frame_count"),
    )
    hop_length: Mapped[int] = mapped_column(
        CheckConstraint("hop_length > 0", name="ck_timeseries_hop_length"),
    )
    sample_rate: Mapped[int] = mapped_column(
        CheckConstraint("sample_rate > 0", name="ck_timeseries_sample_rate"),
    )
    dtype: Mapped[str] = mapped_column(String(20), default="float32")
    shape: Mapped[str | None] = mapped_column(String(50))
    file_size: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
