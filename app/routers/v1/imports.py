"""Yandex Music import endpoints — playlists + batch enrich via ImportYandexService."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.dependencies import DbSession
from app.schemas.imports import (
    YandexEnrichRequest,
    YandexEnrichResponse,
    YandexPlaylistInfo,
)
from app.services.import_yandex import ImportYandexService
from app.services.yandex_music_client import YandexMusicClient

router = APIRouter(prefix="/imports/yandex", tags=["imports"])


def _ym_client() -> YandexMusicClient:
    return YandexMusicClient(
        token=settings.yandex_music_token,
        user_id=settings.yandex_music_user_id,
    )


@router.get(
    "/playlists",
    response_model=list[YandexPlaylistInfo],
    summary="List Yandex Music playlists",
    description="Fetch available playlists from the configured Yandex Music account.",
    response_description="List of playlists with track counts",
    operation_id="list_yandex_playlists",
)
async def list_playlists(db: DbSession) -> list[YandexPlaylistInfo]:
    ym = _ym_client()
    try:
        playlists = await ym.fetch_user_playlists(settings.yandex_music_user_id)
        return [
            YandexPlaylistInfo(
                kind=str(p.get("kind", "")),
                title=p.get("title", ""),
                track_count=p.get("trackCount", 0),
                owner_id=str(p.get("uid", settings.yandex_music_user_id)),
            )
            for p in playlists
        ]
    finally:
        await ym.close()


@router.post(
    "/enrich",
    response_model=YandexEnrichResponse,
    summary="Enrich tracks with Yandex Music metadata",
    description=(
        "Searches Yandex Music for each track by title, populates "
        "genres, artists, labels, releases, and provider IDs."
    ),
    response_description="Summary of enrichment results",
    operation_id="enrich_tracks_from_yandex",
)
async def enrich_tracks(data: YandexEnrichRequest, db: DbSession) -> YandexEnrichResponse:
    ym = _ym_client()
    try:
        svc = ImportYandexService(session=db, ym_client=ym)
        result = await svc.enrich_batch(data.track_ids)
        await db.commit()
        return YandexEnrichResponse(**result)
    finally:
        await ym.close()
