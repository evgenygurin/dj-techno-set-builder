from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import close_db, init_db
from app.errors import register_error_handlers
from app.middleware import apply_middleware
from app.routers import register_routers


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    apply_middleware(application)
    register_error_handlers(application)
    register_routers(application)
    return application


app = create_app()
