import pytest
from pydantic import ValidationError

from app.schemas.imports import (
    YandexEnrichRequest,
    YandexEnrichResponse,
    YandexPlaylistImportRequest,
)


def test_playlist_import_request():
    req = YandexPlaylistImportRequest(
        user_id="250905515",
        playlist_kind="1259",
        download_audio=True,
        audio_dest_dir="/path/to/library/tracks",
    )
    assert req.user_id == "250905515"
    assert req.prefer_bitrate == 320


def test_playlist_import_request_rejects_extra():
    with pytest.raises(ValidationError):
        YandexPlaylistImportRequest(
            user_id="123", playlist_kind="1", bogus="field"
        )


def test_enrich_request():
    req = YandexEnrichRequest(track_ids=[1, 2, 3])
    assert len(req.track_ids) == 3


def test_enrich_request_rejects_empty():
    with pytest.raises(ValidationError):
        YandexEnrichRequest(track_ids=[])


def test_enrich_response():
    resp = YandexEnrichResponse(
        total=10, enriched=8, not_found=2, errors=["Track 5: no match"]
    )
    assert resp.enriched == 8
    assert len(resp.errors) == 1
