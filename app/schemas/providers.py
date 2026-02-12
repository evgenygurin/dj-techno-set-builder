"""Pydantic DTOs for provider ingestion/metadata entities."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field

from app.common.dto import BaseDTO
from app.schemas.common import (
    BpmFloat,
    KeyCode,
    ProviderCountryCode,
    UnitFloat,
)


class ProviderTrackIdDTO(BaseDTO):
    track_id: int
    provider_id: int
    provider_track_id: str = Field(min_length=1)
    provider_country: ProviderCountryCode | None = None


class SpotifyMetadataDTO(BaseDTO):
    track_id: int
    spotify_track_id: str = Field(min_length=1)
    spotify_album_id: str | None = None
    explicit: bool = False
    popularity: int | None = Field(default=None, ge=0, le=100)
    duration_ms: int | None = Field(default=None, gt=0)
    preview_url: str | None = None
    release_date: date | None = None
    release_date_precision: Literal["year", "month", "day"] | None = None
    extra: Any | None = None


class SpotifyAudioFeatureDTO(BaseDTO):
    track_id: int
    danceability: UnitFloat
    energy: UnitFloat
    loudness: float
    speechiness: UnitFloat
    acousticness: UnitFloat
    instrumentalness: UnitFloat
    liveness: UnitFloat
    valence: UnitFloat
    tempo: float
    time_signature: int
    key: int
    mode: Literal[0, 1]


class BeatportMetadataDTO(BaseDTO):
    track_id: int
    beatport_track_id: str = Field(min_length=1)
    beatport_release_id: str | None = None
    bpm: BpmFloat | None = None
    key_code: KeyCode | None = None
    length_ms: int | None = Field(default=None, gt=0)
    label_name: str | None = None
    genre_name: str | None = None
    subgenre_name: str | None = None
    release_date: date | None = None
    preview_url: str | None = None
    image_url: str | None = None
    extra: Any | None = None
