from datetime import date
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SpotifyAlbumMetadata(TimestampMixin, Base):
    __tablename__ = "spotify_album_metadata"

    spotify_album_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    album_type: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(500))
    label: Mapped[str | None] = mapped_column(String(300))
    popularity: Mapped[int | None]
    release_date: Mapped[str | None] = mapped_column(String(50))
    total_tracks: Mapped[int | None]
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SpotifyMetadata(TimestampMixin, Base):
    __tablename__ = "spotify_metadata"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    spotify_track_id: Mapped[str] = mapped_column(String(100), unique=True)
    spotify_album_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("spotify_album_metadata.spotify_album_id", ondelete="SET NULL"),
    )
    explicit: Mapped[bool] = mapped_column(Boolean, default=False)
    popularity: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("popularity BETWEEN 0 AND 100", name="ck_spotify_metadata_popularity"),
    )
    duration_ms: Mapped[int | None]
    preview_url: Mapped[str | None] = mapped_column(String(500))
    release_date: Mapped[date | None]
    release_date_precision: Mapped[str | None] = mapped_column(
        String(5),
        CheckConstraint(
            "release_date_precision IN ('year','month','day')",
            name="ck_spotify_metadata_date_precision",
        ),
    )
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SpotifyAudioFeatures(TimestampMixin, Base):
    __tablename__ = "spotify_audio_features"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
    )
    danceability: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("danceability BETWEEN 0 AND 1", name="ck_saf_danceability"),
    )
    energy: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("energy BETWEEN 0 AND 1", name="ck_saf_energy"),
    )
    loudness: Mapped[float] = mapped_column(Float)
    speechiness: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("speechiness BETWEEN 0 AND 1", name="ck_saf_speechiness"),
    )
    acousticness: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("acousticness BETWEEN 0 AND 1", name="ck_saf_acousticness"),
    )
    instrumentalness: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("instrumentalness BETWEEN 0 AND 1", name="ck_saf_instrumentalness"),
    )
    liveness: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("liveness BETWEEN 0 AND 1", name="ck_saf_liveness"),
    )
    valence: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("valence BETWEEN 0 AND 1", name="ck_saf_valence"),
    )
    tempo: Mapped[float] = mapped_column(Float)
    time_signature: Mapped[int] = mapped_column(SmallInteger)
    key: Mapped[int] = mapped_column(SmallInteger)
    mode: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("mode IN (0, 1)", name="ck_saf_mode"),
    )


class SpotifyArtistMetadata(TimestampMixin, Base):
    __tablename__ = "spotify_artist_metadata"

    spotify_artist_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(300))
    popularity: Mapped[int | None]
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SpotifyPlaylistMetadata(TimestampMixin, Base):
    __tablename__ = "spotify_playlist_metadata"

    spotify_playlist_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None]
    public: Mapped[bool | None] = mapped_column(Boolean)
    snapshot_id: Mapped[str | None] = mapped_column(String(100))
    owner: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)
