"""Yandex Music search & enrichment endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.clients.yandex_music import YandexMusicClient
from app.config import settings
from app.dependencies import DbSession
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.yandex_music import (
    YmBatchEnrichRequest,
    YmBatchEnrichResponse,
    YmEnrichRequest,
    YmEnrichResponse,
    YmSearchRequest,
    YmSearchResponse,
    YmSearchResult,
)
from app.services.yandex_music_enrichment import YandexMusicEnrichmentService

router = APIRouter(tags=["yandex-music"])

_ym_client: YandexMusicClient | None = None


def _get_client() -> YandexMusicClient:
    global _ym_client
    if _ym_client is None:
        _ym_client = YandexMusicClient(
            token=settings.yandex_music_token,
            base_url=settings.yandex_music_base_url,
        )
    return _ym_client


def _service(db: DbSession) -> YandexMusicEnrichmentService:
    return YandexMusicEnrichmentService(session=db, ym_client=_get_client())


@router.post(
    "/yandex-music/search",
    response_model=YmSearchResponse,
    summary="Search Yandex Music tracks",
    description="Search for tracks on Yandex Music by query string.",
    response_description="List of matching tracks with metadata",
    operation_id="search_yandex_music",
)
async def search_yandex_music(data: YmSearchRequest) -> YmSearchResponse:
    raw_results = await _get_client().search_tracks(data.query, page=data.page)
    items: list[YmSearchResult] = []
    for r in raw_results:
        artists = [a["name"] for a in r.get("artists", []) if not a.get("various")]
        albums = r.get("albums", [])
        album = albums[0] if albums else {}
        labels = album.get("labels", [])
        label = labels[0] if labels else None
        if isinstance(label, dict):
            label = label.get("name")
        items.append(
            YmSearchResult(
                yandex_track_id=str(r["id"]),
                title=r.get("title", ""),
                artists=artists,
                album_title=album.get("title"),
                genre=album.get("genre"),
                label=label,
                duration_ms=r.get("durationMs"),
                year=album.get("year"),
                release_date=album.get("releaseDate"),
                cover_uri=r.get("coverUri"),
            )
        )
    return YmSearchResponse(results=items, total=len(items), page=data.page)


@router.post(
    "/tracks/{track_id}/enrich/yandex-music",
    response_model=YmEnrichResponse,
    summary="Enrich track from Yandex Music",
    description=(
        "Link a track to a Yandex Music track ID and enrich metadata: "
        "genre, artists, label, release. Idempotent — skips if already linked."
    ),
    response_description="Enrichment result with extracted metadata",
    responses=RESPONSES_GET,
    operation_id="enrich_track_yandex_music",
)
async def enrich_track(
    track_id: int,
    data: YmEnrichRequest,
    db: DbSession,
) -> YmEnrichResponse:
    result = await _service(db).enrich_track(track_id, yandex_track_id=data.yandex_track_id)
    await db.commit()
    return result


@router.post(
    "/yandex-music/enrich/batch",
    response_model=YmBatchEnrichResponse,
    summary="Batch enrich tracks from Yandex Music",
    description=(
        "Auto-search and enrich multiple tracks. For each track, parses "
        "'Artist — Title' from track.title, searches YM, enriches with "
        "best match."
    ),
    response_description="Aggregate enrichment results",
    operation_id="batch_enrich_yandex_music",
)
async def batch_enrich(
    data: YmBatchEnrichRequest,
    db: DbSession,
) -> YmBatchEnrichResponse:
    svc = _service(db)
    total = len(data.track_ids)
    enriched = 0
    skipped = 0

    results = await svc.enrich_batch(data.track_ids)
    for r in results:
        if r.already_linked:
            skipped += 1
        else:
            enriched += 1

    await db.commit()
    return YmBatchEnrichResponse(
        total=total,
        enriched=enriched,
        skipped=skipped,
        failed=total - len(results),
    )
