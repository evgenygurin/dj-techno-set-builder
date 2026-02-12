"""SQLAlchemy ORM models generated from schema_v6.sql."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base
from app.models.common import ensure_float_range, ensure_int_range, ensure_one_of


class ProviderTrackId(Base):
    __tablename__ = "provider_track_ids"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "provider_track_id",
            "provider_country",
            name="provider_track_ids_uq",
            postgresql_nulls_not_distinct=True,
        ),
        Index("idx_provider_track_ids_track", "track_id"),
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("providers.provider_id"),
        nullable=False,
    )
    provider_track_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    provider_country: Mapped[str | None] = mapped_column(
        String(2),
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
    __mapper_args__ = {
        # Table has no physical PK in schema; use stable unique business key for ORM identity.
        "primary_key": [provider_id, provider_track_id, provider_country],
    }

    @validates("provider_country")
    def _validate_provider_country(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if len(normalized) != 2:
            raise ValueError(f"{key} must be an ISO-3166 alpha-2 code")
        return normalized


class RawProviderResponse(Base):
    __tablename__ = "raw_provider_responses"
    __table_args__ = (
        Index("idx_raw_provider_track", "track_id", "provider_id"),
        {"postgresql_partition_by": "RANGE (ingested_at)"},
    )
    id: Mapped[int] = mapped_column(
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
    provider_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("providers.provider_id"),
        nullable=False,
    )
    provider_track_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    endpoint: Mapped[str | None] = mapped_column(
        Text,
    )
    payload: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=func.now(),
    )


class SpotifyAlbumMetadata(Base):
    __tablename__ = "spotify_album_metadata"
    spotify_album_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        nullable=False,
    )
    album_type: Mapped[str | None] = mapped_column(
        Text,
    )
    name: Mapped[str | None] = mapped_column(
        Text,
    )
    label: Mapped[str | None] = mapped_column(
        Text,
    )
    popularity: Mapped[int | None] = mapped_column(
        Integer,
    )
    release_date: Mapped[str | None] = mapped_column(
        Text,
    )
    total_tracks: Mapped[int | None] = mapped_column(
        Integer,
    )
    extra: Mapped[Any] = mapped_column(
        JSON,
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


class SpotifyMetadata(Base):
    __tablename__ = "spotify_metadata"
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    spotify_track_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    spotify_album_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("spotify_album_metadata.spotify_album_id", ondelete="SET NULL"),
    )
    explicit: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    popularity: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    preview_url: Mapped[str | None] = mapped_column(
        Text,
    )
    release_date: Mapped[date | None] = mapped_column(
        Date,
    )
    release_date_precision: Mapped[str | None] = mapped_column(
        Text,
    )
    extra: Mapped[Any] = mapped_column(
        JSON,
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

    @validates("popularity")
    def _validate_popularity(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=0, max_value=100)

    @validates("release_date_precision")
    def _validate_release_date_precision(
        self, key: str, value: str | None
    ) -> str | None:
        return ensure_one_of(key, value, ("year", "month", "day"))


class SpotifyAudioFeature(Base):
    __tablename__ = "spotify_audio_features"
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    danceability: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    energy: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    loudness: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    speechiness: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    acousticness: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    instrumentalness: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    liveness: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    valence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    tempo: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    time_signature: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    key: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    mode: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
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

    @validates(
        "danceability",
        "energy",
        "speechiness",
        "acousticness",
        "instrumentalness",
        "liveness",
        "valence",
    )
    def _validate_unit_float(self, key: str, value: float) -> float:
        checked = ensure_float_range(key, value, min_value=0.0, max_value=1.0)
        assert checked is not None
        return checked

    @validates("mode")
    def _validate_mode(self, key: str, value: int) -> int:
        checked = ensure_one_of(key, value, (0, 1))
        assert checked is not None
        return checked


class SpotifyArtistMetadata(Base):
    __tablename__ = "spotify_artist_metadata"
    spotify_artist_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(
        Text,
    )
    popularity: Mapped[int | None] = mapped_column(
        Integer,
    )
    genres: Mapped[Any] = mapped_column(
        JSON,
    )
    extra: Mapped[Any] = mapped_column(
        JSON,
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


class SpotifyPlaylistMetadata(Base):
    __tablename__ = "spotify_playlist_metadata"
    spotify_playlist_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(
        Text,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
    )
    public: Mapped[bool | None] = mapped_column(
        Boolean,
    )
    snapshot_id: Mapped[str | None] = mapped_column(
        Text,
    )
    owner: Mapped[Any] = mapped_column(
        JSON,
    )
    extra: Mapped[Any] = mapped_column(
        JSON,
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


class SoundcloudMetadata(Base):
    __tablename__ = "soundcloud_metadata"
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    soundcloud_track_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    soundcloud_user_id: Mapped[str | None] = mapped_column(
        Text,
    )
    bpm: Mapped[int | None] = mapped_column(
        Integer,
    )
    key_signature: Mapped[str | None] = mapped_column(
        Text,
    )
    genre: Mapped[str | None] = mapped_column(
        Text,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    playback_count: Mapped[int | None] = mapped_column(
        Integer,
    )
    favoritings_count: Mapped[int | None] = mapped_column(
        Integer,
    )
    reposts_count: Mapped[int | None] = mapped_column(
        Integer,
    )
    comment_count: Mapped[int | None] = mapped_column(
        Integer,
    )
    downloadable: Mapped[bool | None] = mapped_column(
        Boolean,
    )
    streamable: Mapped[bool | None] = mapped_column(
        Boolean,
    )
    permalink_url: Mapped[str | None] = mapped_column(
        Text,
    )
    artwork_url: Mapped[str | None] = mapped_column(
        Text,
    )
    label_name: Mapped[str | None] = mapped_column(
        Text,
    )
    release_date: Mapped[date | None] = mapped_column(
        Date,
    )
    is_explicit: Mapped[bool | None] = mapped_column(
        Boolean,
    )
    extra: Mapped[Any] = mapped_column(
        JSON,
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


class BeatportMetadata(Base):
    __tablename__ = "beatport_metadata"
    __table_args__ = (
        ForeignKeyConstraint(
            ["key_code"], ["keys.key_code"], name="fk_beatport_key", ondelete="SET NULL"
        ),
    )
    track_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    beatport_track_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    beatport_release_id: Mapped[str | None] = mapped_column(
        Text,
    )
    bpm: Mapped[float | None] = mapped_column(
        Float,
    )
    key_code: Mapped[int | None] = mapped_column(
        SmallInteger,
    )
    length_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    label_name: Mapped[str | None] = mapped_column(
        Text,
    )
    genre_name: Mapped[str | None] = mapped_column(
        Text,
    )
    subgenre_name: Mapped[str | None] = mapped_column(
        Text,
    )
    release_date: Mapped[date | None] = mapped_column(
        Date,
    )
    preview_url: Mapped[str | None] = mapped_column(
        Text,
    )
    image_url: Mapped[str | None] = mapped_column(
        Text,
    )
    extra: Mapped[Any] = mapped_column(
        JSON,
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

    @validates("key_code")
    def _validate_key_code(self, key: str, value: int | None) -> int | None:
        return ensure_int_range(key, value, min_value=0, max_value=23)
