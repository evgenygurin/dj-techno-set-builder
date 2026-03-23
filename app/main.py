from __future__ import annotations

# Note: TypeForm compat patch applied in app/__init__.py (runs before this module)
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings

# Sentry/OTEL init moved to app.mcp.observability.init_observability()
from app.mcp.observability import init_observability

init_observability()

logger = logging.getLogger(__name__)

from fastmcp.utilities.lifespan import combine_lifespans  # noqa: E402

from app.infrastructure.database import close_db, init_db  # noqa: E402
from app.core.errors import register_error_handlers  # noqa: E402
from app.mcp import create_dj_mcp  # noqa: E402
from app.middleware import apply_middleware  # noqa: E402
from app.routers import register_routers  # noqa: E402


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
