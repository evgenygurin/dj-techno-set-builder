from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class DjLibraryItem(Base):
    __tablename__ = "dj_library_items"

    library_item_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    file_uri: Mapped[str | None] = mapped_column(String(1000))
    file_path: Mapped[str | None] = mapped_column(String(1000))
    file_hash: Mapped[bytes | None]
    file_size_bytes: Mapped[int | None] = mapped_column(
        CheckConstraint("file_size_bytes >= 0", name="ck_dj_lib_file_size"),
    )
    mime_type: Mapped[str | None] = mapped_column(String(50))
    bitrate_kbps: Mapped[int | None]
    sample_rate_hz: Mapped[int | None]
    channels: Mapped[int | None] = mapped_column(SmallInteger)
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("source_app BETWEEN 1 AND 5", name="ck_dj_lib_source_app"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DjBeatgrid(TimestampMixin, Base):
    __tablename__ = "dj_beatgrid"
    __table_args__ = (UniqueConstraint("track_id", "source_app", name="uq_beatgrid_track_source"),)

    beatgrid_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    source_app: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("source_app BETWEEN 1 AND 5", name="ck_beatgrid_source_app"),
    )
    bpm: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("bpm BETWEEN 20 AND 300", name="ck_beatgrid_bpm"),
    )
    first_downbeat_ms: Mapped[int] = mapped_column(
        CheckConstraint("first_downbeat_ms >= 0", name="ck_beatgrid_downbeat"),
    )
    grid_offset_ms: Mapped[int | None]
    grid_confidence: Mapped[float | None] = mapped_column(
        Float,
        CheckConstraint("grid_confidence BETWEEN 0 AND 1", name="ck_beatgrid_conf"),
    )
    is_variable_tempo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class DjBeatgridChangePoint(Base):
    __tablename__ = "dj_beatgrid_change_points"

    point_id: Mapped[int] = mapped_column(primary_key=True)
    beatgrid_id: Mapped[int] = mapped_column(
        ForeignKey("dj_beatgrid.beatgrid_id", ondelete="CASCADE"),
    )
    position_ms: Mapped[int] = mapped_column(
        CheckConstraint("position_ms >= 0", name="ck_bgcp_position"),
    )
    bpm: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("bpm BETWEEN 20 AND 300", name="ck_bgcp_bpm"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DjCuePoint(TimestampMixin, Base):
    __tablename__ = "dj_cue_points"

    cue_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    position_ms: Mapped[int] = mapped_column(
        CheckConstraint("position_ms >= 0", name="ck_cue_position"),
    )
    cue_kind: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("cue_kind BETWEEN 0 AND 7", name="ck_cue_kind"),
    )
    hotcue_index: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("hotcue_index BETWEEN 0 AND 15", name="ck_cue_hotcue_index"),
    )
    label: Mapped[str | None] = mapped_column(String(200))
    color_rgb: Mapped[int | None] = mapped_column(
        CheckConstraint("color_rgb BETWEEN 0 AND 16777215", name="ck_cue_color"),
    )
    is_quantized: Mapped[bool | None] = mapped_column(Boolean)
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("source_app BETWEEN 1 AND 5", name="ck_cue_source_app"),
    )


class DjSavedLoop(Base):
    __tablename__ = "dj_saved_loops"
    __table_args__ = (
        CheckConstraint(
            "out_ms > in_ms AND length_ms = out_ms - in_ms",
            name="ck_loop_range",
        ),
    )

    loop_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    in_ms: Mapped[int] = mapped_column(
        CheckConstraint("in_ms >= 0", name="ck_loop_in"),
    )
    out_ms: Mapped[int]
    length_ms: Mapped[int] = mapped_column(
        CheckConstraint("length_ms > 0", name="ck_loop_length"),
    )
    hotcue_index: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("hotcue_index BETWEEN 0 AND 15", name="ck_loop_hotcue"),
    )
    label: Mapped[str | None] = mapped_column(String(200))
    is_active_on_load: Mapped[bool | None] = mapped_column(Boolean)
    color_rgb: Mapped[int | None] = mapped_column(
        CheckConstraint("color_rgb BETWEEN 0 AND 16777215", name="ck_loop_color"),
    )
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("source_app BETWEEN 1 AND 5", name="ck_loop_source_app"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DjPlaylist(Base):
    __tablename__ = "dj_playlists"

    playlist_id: Mapped[int] = mapped_column(primary_key=True)
    parent_playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("dj_playlists.playlist_id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(500))
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("source_app BETWEEN 1 AND 5", name="ck_playlist_source_app"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DjPlaylistItem(Base):
    __tablename__ = "dj_playlist_items"
    __table_args__ = (
        UniqueConstraint("playlist_id", "sort_index", name="uq_playlist_items_sort"),
    )

    playlist_item_id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("dj_playlists.playlist_id", ondelete="CASCADE"),
    )
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    sort_index: Mapped[int] = mapped_column(
        CheckConstraint("sort_index >= 0", name="ck_playlist_item_sort"),
    )
    added_at: Mapped[datetime | None]


class DjAppExport(Base):
    __tablename__ = "dj_app_exports"

    export_id: Mapped[int] = mapped_column(primary_key=True)
    target_app: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("target_app BETWEEN 1 AND 3", name="ck_export_target_app"),
    )
    export_format: Mapped[str] = mapped_column(String(50))
    playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("dj_playlists.playlist_id"),
    )
    storage_uri: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
