import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Import core routers (no audio dependencies)
from app.routers.v1 import (  # noqa: E402
    artists,
    genres,
    imports,
    keys,
    labels,
    playlists,
    releases,
    runs,
    tracks,
    yandex_music,
)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(tracks.router)
v1_router.include_router(artists.router)
v1_router.include_router(labels.router)
v1_router.include_router(releases.router)
v1_router.include_router(genres.router)
v1_router.include_router(playlists.router)
v1_router.include_router(keys.router)
v1_router.include_router(runs.router)
v1_router.include_router(yandex_music.router)
v1_router.include_router(imports.router)

# Conditionally import audio-dependent routers
try:
    from app.routers.v1 import analysis, features, sections, sets, transitions
    v1_router.include_router(sets.router)
    v1_router.include_router(transitions.router)
    v1_router.include_router(features.router)
    v1_router.include_router(sections.router)
    v1_router.include_router(analysis.router)
    logger.info("Audio analysis routers enabled")
except ImportError as e:
    logger.warning(f"Audio analysis routers disabled: {e}")
    # Create placeholder routers for missing functionality
    analysis_router = APIRouter(prefix="/tracks", tags=["analysis"])
    features_router = APIRouter(prefix="/features", tags=["features"])
    sections_router = APIRouter(prefix="/sections", tags=["sections"])
    sets_router = APIRouter(prefix="/sets", tags=["sets"])
    transitions_router = APIRouter(prefix="/transitions", tags=["transitions"])

    @analysis_router.get("/analyze/{track_id}")
    async def analyze_track_placeholder(track_id: int) -> dict[str, str]:
        return {"error": "Audio analysis disabled - missing dependencies"}

    @features_router.get("/")
    async def get_features_placeholder() -> dict[str, str]:
        return {"error": "Audio features disabled - missing dependencies"}

    @sections_router.get("/")
    async def get_sections_placeholder() -> dict[str, str]:
        return {"error": "Audio sections disabled - missing dependencies"}

    @sets_router.get("/")
    async def get_sets_placeholder() -> dict[str, str]:
        return {"error": "Set generation disabled - missing dependencies"}

    @transitions_router.get("/")
    async def get_transitions_placeholder() -> dict[str, str]:
        return {"error": "Transition analysis disabled - missing dependencies"}

    v1_router.include_router(analysis_router)
    v1_router.include_router(features_router)
    v1_router.include_router(sections_router)
    v1_router.include_router(sets_router)
    v1_router.include_router(transitions_router)
