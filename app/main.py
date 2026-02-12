"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.common.router import ModuleRegistry
from app.core.config import settings
from app.core.errors import AppError
from app.core.handlers import app_error_handler, unhandled_error_handler
from app.core.logging import setup_logging
from app.core.middleware.logging import LoggingMiddleware
from app.core.middleware.monitoring import MonitoringMiddleware
from app.core.middleware.request_id import RequestIdMiddleware
from app.db.session import close_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle hook."""
    # ── startup ──
    json_output = settings.app_env in ("staging", "prod")
    setup_logging(log_level=settings.log_level, json_output=json_output)
    yield
    # ── shutdown ──
    await close_engine()


def create_app(*, registry: ModuleRegistry | None = None) -> FastAPI:
    """Build and return the configured ``FastAPI`` instance."""

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
    )

    # ── Middleware (order matters: first added = outermost) ──
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(MonitoringMiddleware)

    # ── Exception handlers ──
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── Routes ──
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Domain modules ──
    if registry is not None:
        registry.wire(app)

    return app


app = create_app()
