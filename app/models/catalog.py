"""SQLAlchemy ORM models generated from schema_v6.sql."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
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
from app.models.common import ensure_int_range, ensure_one_of, ensure_positive


class Provider(Base):
    __tablename__ = "providers"
    provider_id: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        nullable=False,
    )
    provider_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        UniqueConstraint("fingerprint_sha1", name="tracks_fingerprint_uq"),
        Index(
            "idx_tracks_active",
            "track_id",
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index(
            "idx_tracks_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    fingerprint_sha1: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    title_sort: Mapped[str | None] = mapped_column(
        Text,
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=text("0"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    @validates("duration_ms")
    def _validate_duration_ms(self, key: str, value: int) -> int:
        checked = ensure_positive(key, value)
        assert checked is not None
        return checked

    @validates("status")
    def _validate_status(self, key: str, value: int) -> int:
        checked = ensure_one_of(key, value, (0, 1))
        assert checked is not None
        return checked


class Artist(Base):
    __tablename__ = "artists"
    __table_args__ = (
        Index(
            "idx_artists_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )
    artist_id: Mapped[int] = mapped_column(
        Integer,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    name_sort: Mapped[str | None] = mapped_column(
        Text,
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


class TrackArtist(Base):
    __tablename__ = "track_artists"
    __table_args__ = (Index("idx_track_artists_artist", "artist_id"),)
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    artist_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("artists.artist_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    role: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("role")
    def _validate_role(self, key: str, value: int) -> int:
        checked = ensure_int_range(key, value, min_value=0, max_value=2)
        assert checked is not None
        return checked


class Label(Base):
    __tablename__ = "labels"
    label_id: Mapped[int] = mapped_column(
        Integer,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    name_sort: Mapped[str | None] = mapped_column(
        Text,
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


class Release(Base):
    __tablename__ = "releases"
    release_id: Mapped[int] = mapped_column(
        Integer,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    label_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("labels.label_id", ondelete="SET NULL"),
    )
    release_date: Mapped[date | None] = mapped_column(
        Date,
    )
    release_date_precision: Mapped[str | None] = mapped_column(
        Text,
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

    @validates("release_date_precision")
    def _validate_release_date_precision(
        self, key: str, value: str | None
    ) -> str | None:
        return ensure_one_of(key, value, ("year", "month", "day"))


class TrackRelease(Base):
    __tablename__ = "track_releases"
    __table_args__ = (Index("idx_track_releases_release", "release_id"),)
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    release_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("releases.release_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    track_number: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    disc_number: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Genre(Base):
    __tablename__ = "genres"
    genre_id: Mapped[int] = mapped_column(
        Integer,
        Identity(always=True),
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    parent_genre_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("genres.genre_id", ondelete="SET NULL"),
    )


class TrackGenre(Base):
    __tablename__ = "track_genres"
    __table_args__ = (
        UniqueConstraint(
            "track_id",
            "genre_id",
            "source_provider_id",
            name="track_genres_uq",
            postgresql_nulls_not_distinct=True,
        ),
    )
    track_genre_id: Mapped[int] = mapped_column(
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
    genre_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("genres.genre_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_provider_id: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("providers.provider_id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
