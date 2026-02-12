from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin


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


class TrackArtist(CreatedAtMixin, Base):
    __tablename__ = "track_artists"
    __table_args__ = (CheckConstraint("role BETWEEN 0 AND 2", name="ck_track_artists_role"),)

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.artist_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[int] = mapped_column(SmallInteger, primary_key=True)


class Label(TimestampMixin, Base):
    __tablename__ = "labels"

    label_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    name_sort: Mapped[str | None] = mapped_column(String(300))


class Release(TimestampMixin, Base):
    __tablename__ = "releases"

    release_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    label_id: Mapped[int | None] = mapped_column(
        ForeignKey("labels.label_id", ondelete="SET NULL"),
    )
    release_date: Mapped[date | None]
    release_date_precision: Mapped[str | None] = mapped_column(
        String(5),
        CheckConstraint(
            "release_date_precision IN ('year','month','day')",
            name="ck_releases_date_precision",
        ),
    )


class TrackRelease(CreatedAtMixin, Base):
    __tablename__ = "track_releases"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    release_id: Mapped[int] = mapped_column(
        ForeignKey("releases.release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    track_number: Mapped[int | None] = mapped_column(SmallInteger)
    disc_number: Mapped[int | None] = mapped_column(SmallInteger)


class Genre(Base):
    __tablename__ = "genres"

    genre_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    parent_genre_id: Mapped[int | None] = mapped_column(
        ForeignKey("genres.genre_id", ondelete="SET NULL"),
    )


class TrackGenre(CreatedAtMixin, Base):
    __tablename__ = "track_genres"
    __table_args__ = (
        UniqueConstraint(
            "track_id",
            "genre_id",
            "source_provider_id",
            name="uq_track_genres_composite",
        ),
    )

    track_genre_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.genre_id", ondelete="CASCADE"),
    )
    source_provider_id: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("providers.provider_id", ondelete="SET NULL"),
    )
