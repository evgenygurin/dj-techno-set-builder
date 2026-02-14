from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp.utilities.lifespan import combine_lifespans

from app.config import settings
from app.database import close_db, init_db
from app.errors import register_error_handlers
from app.mcp import create_dj_mcp
from app.middleware import apply_middleware
from app.routers import register_routers


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    mcp = create_dj_mcp()
    mcp_app = mcp.http_app(path="/mcp")

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
    )
    application.mount("/mcp", mcp_app)
    apply_middleware(application)
    register_error_handlers(application)
    register_routers(application)
    return application


app = create_app()
