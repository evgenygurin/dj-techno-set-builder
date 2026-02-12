from fastapi import APIRouter

from app.routers.v1 import tracks

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(tracks.router)
