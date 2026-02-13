from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


class YandexPlaylistImportRequest(BaseSchema):
    """Import a Yandex Music playlist into the DJ library."""

    user_id: str
    playlist_kind: str
    download_audio: bool = False
    audio_dest_dir: str | None = None
    analyze_after_download: bool = False
    prefer_bitrate: int = Field(default=320, ge=128, le=320)


class YandexPlaylistImportResponse(BaseSchema):
    """Result of a playlist import."""

    tracks_imported: int = 0
    tracks_skipped: int = 0
    tracks_failed: int = 0
    tracks_downloaded: int = 0
    tracks_analyzed: int = 0
    errors: list[str] = Field(default_factory=list)


class YandexEnrichRequest(BaseSchema):
    """Enrich existing tracks with Yandex Music metadata."""

    track_ids: list[int] = Field(min_length=1, max_length=500)


class YandexEnrichResponse(BaseSchema):
    """Result of batch enrichment."""

    total: int = 0
    enriched: int = 0
    not_found: int = 0
    errors: list[str] = Field(default_factory=list)


class YandexPlaylistInfo(BaseSchema):
    """Summary of a Yandex Music playlist."""

    kind: str
    title: str
    track_count: int
    owner_id: str
