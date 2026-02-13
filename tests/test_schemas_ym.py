from app.schemas.yandex_music import (
    YmBatchEnrichRequest,
    YmBatchEnrichResponse,
    YmEnrichRequest,
    YmSearchRequest,
    YmSearchResult,
)


def test_search_request() -> None:
    req = YmSearchRequest(query="Jouska Octopus")
    assert req.query == "Jouska Octopus"
    assert req.page == 0


def test_search_result() -> None:
    item = YmSearchResult(
        yandex_track_id="103119407",
        title="Octopus Neuroplasticity",
        artists=["Jouska"],
        album_title="Techgnosis, Vol. 6",
        genre="techno",
        label="Techgnosis",
        duration_ms=347150,
    )
    assert item.yandex_track_id == "103119407"


def test_enrich_request() -> None:
    req = YmEnrichRequest(yandex_track_id="103119407")
    assert req.yandex_track_id == "103119407"


def test_batch_enrich_request() -> None:
    req = YmBatchEnrichRequest(track_ids=[1, 2, 3])
    assert len(req.track_ids) == 3


def test_batch_enrich_response() -> None:
    resp = YmBatchEnrichResponse(total=10, enriched=8, skipped=1, failed=1)
    assert resp.total == 10
    assert resp.enriched == 8
