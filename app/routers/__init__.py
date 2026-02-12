from fastapi import FastAPI

from app.routers import health
from app.routers.v1 import v1_router


def register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(v1_router)
