"""SQLAlchemy ORM models generated from schema_v6.sql."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base
from app.models.common import ensure_float_range, ensure_int_range, ensure_non_negative


class DjLibraryItem(Base):
    __tablename__ = "dj_library_items"
    __table_args__ = (Index("idx_dj_lib_track", "track_id"),)
    library_item_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    file_uri: Mapped[str | None] = mapped_column(
        Text,
    )
    file_path: Mapped[str | None] = mapped_column(
        Text,
    )
    file_hash: Mapped[bytes | None] = mapped_column(
        LargeBinary,
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    mime_type: Mapped[str | None] = mapped_column(
        Text,
    )
    bitrate_kbps: Mapped[int | None] = mapped_column(
        Integer,
    )
    sample_rate_hz: Mapped[int | None] = mapped_column(
        Integer,
    )
    channels: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DjBeatgrid(Base):
    __tablename__ = "dj_beatgrid"
    __table_args__ = (
        UniqueConstraint("track_id", "source_app", name="beatgrid_track_source_uq"),
        Index(
            "idx_beatgrid_canonical",
            "track_id",
            unique=True,
            postgresql_where=text("is_canonical = true"),
        ),
    )
    beatgrid_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_app: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    bpm: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    first_downbeat_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    grid_offset_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    grid_confidence: Mapped[float | None] = mapped_column(
        Float,
    )
    is_variable_tempo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    is_canonical: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
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

    @validates("source_app")
    def _validate_source_app(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=1, max_value=5)
        assert checked is not None
        return checked

    @validates("bpm")
    def _validate_bpm(self, key: str, value: float) -> float:
        checked = ensure_float_range(key, value, min_value=20.0, max_value=300.0)
        assert checked is not None
        return checked

    @validates("first_downbeat_ms")
    def _validate_first_downbeat_ms(self, key: str, value: int) -> int:
        checked = ensure_non_negative(key, value)
        assert checked is not None
        return checked

    @validates("grid_confidence")
    def _validate_grid_confidence(self, key: str, value: float | None) -> float | None:
        return ensure_float_range(key, value, min_value=0.0, max_value=1.0)


class DjBeatgridChangePoint(Base):
    __tablename__ = "dj_beatgrid_change_points"
    __table_args__ = (Index("idx_beatgrid_cp_grid", "beatgrid_id", "position_ms"),)
    point_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    beatgrid_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dj_beatgrid.beatgrid_id", ondelete="CASCADE"),
        nullable=False,
    )
    position_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    bpm: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("position_ms")
    def _validate_position_ms(self, key: str, value: int) -> int:
        checked = ensure_non_negative(key, value)
        assert checked is not None
        return checked

    @validates("bpm")
    def _validate_bpm(self, key: str, value: float) -> float:
        checked = ensure_float_range(key, value, min_value=20.0, max_value=300.0)
        assert checked is not None
        return checked


class DjCuePoint(Base):
    __tablename__ = "dj_cue_points"
    __table_args__ = (Index("idx_cues_track", "track_id", "hotcue_index"),)
    cue_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    position_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    cue_kind: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    hotcue_index: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    label: Mapped[str | None] = mapped_column(
        Text,
    )
    color_rgb: Mapped[int | None] = mapped_column(
        Integer,
    )
    is_quantized: Mapped[bool | None] = mapped_column(
        Boolean,
    )
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
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

    @validates("position_ms")
    def _validate_position_ms(self, key: str, value: int) -> int:
        checked = ensure_non_negative(key, value)
        assert checked is not None
        return checked

    @validates("cue_kind")
    def _validate_cue_kind(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=0, max_value=7)
        assert checked is not None
        return checked

    @validates("hotcue_index")
    def _validate_hotcue_index(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=0, max_value=15)

    @validates("color_rgb")
    def _validate_color_rgb(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=0, max_value=16777215)

    @validates("source_app")
    def _validate_source_app(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=1, max_value=5)


class DjSavedLoop(Base):
    __tablename__ = "dj_saved_loops"
    __table_args__ = (
        CheckConstraint(
            "out_ms > in_ms AND length_ms = out_ms - in_ms", name="loop_range_check"
        ),
        Index("idx_loops_track", "track_id", "hotcue_index"),
    )
    loop_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    in_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    out_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    length_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    hotcue_index: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    label: Mapped[str | None] = mapped_column(
        Text,
    )
    is_active_on_load: Mapped[bool | None] = mapped_column(
        Boolean,
    )
    color_rgb: Mapped[int | None] = mapped_column(
        Integer,
    )
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("in_ms")
    def _validate_in_ms(self, key: str, value: int) -> int:
        checked = ensure_non_negative(key, value)
        assert checked is not None
        return checked

    @validates("out_ms", "length_ms")
    def _validate_loop_lengths(self, key: str, value: int) -> int:
        checked = ensure_non_negative(key, value)
        assert checked is not None
        if key == "length_ms" and checked == 0:
            raise ValueError("length_ms must be > 0")
        out_ms = checked if key == "out_ms" else self.out_ms
        length_ms = checked if key == "length_ms" else self.length_ms
        in_ms = self.in_ms
        if in_ms is not None and out_ms is not None and out_ms <= in_ms:
            raise ValueError("out_ms must be greater than in_ms")
        if in_ms is not None and out_ms is not None and length_ms is not None:
            if length_ms != out_ms - in_ms:
                raise ValueError("length_ms must equal out_ms - in_ms")
        return checked

    @validates("hotcue_index")
    def _validate_hotcue_index(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=0, max_value=15)

    @validates("color_rgb")
    def _validate_color_rgb(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=0, max_value=16777215)

    @validates("source_app")
    def _validate_source_app(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=1, max_value=5)


class DjPlaylist(Base):
    __tablename__ = "dj_playlists"
    playlist_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    parent_playlist_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dj_playlists.playlist_id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DjPlaylistItem(Base):
    __tablename__ = "dj_playlist_items"
    __table_args__ = (
        UniqueConstraint("playlist_id", "sort_index", name="dj_playlist_items_uq"),
    )
    playlist_item_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    playlist_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dj_playlists.playlist_id", ondelete="CASCADE"),
        nullable=False,
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    added_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    @validates("sort_index")
    def _validate_sort_index(self, key: str, value: int) -> int:
        checked = ensure_non_negative(key, value)
        assert checked is not None
        return checked


class DjAppExport(Base):
    __tablename__ = "dj_app_exports"
    export_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    target_app: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    export_format: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    playlist_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dj_playlists.playlist_id"),
    )
    storage_uri: Mapped[str | None] = mapped_column(
        Text,
    )
    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("target_app")
    def _validate_target_app(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=1, max_value=3)
        assert checked is not None
        return checked
