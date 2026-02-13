from fastapi import APIRouter

from app.routers.v1 import (
    artists,
    features,
    genres,
    keys,
    labels,
    playlists,
    releases,
    runs,
    sections,
    sets,
    tracks,
    transitions,
)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(tracks.router)
v1_router.include_router(artists.router)
v1_router.include_router(labels.router)
v1_router.include_router(releases.router)
v1_router.include_router(genres.router)
v1_router.include_router(sets.router)
v1_router.include_router(playlists.router)
v1_router.include_router(keys.router)
v1_router.include_router(transitions.router)
v1_router.include_router(runs.router)
v1_router.include_router(features.router)
v1_router.include_router(sections.router)
