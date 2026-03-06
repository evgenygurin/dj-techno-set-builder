from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger(__name__)


def _init_sentry() -> None:
    """Initialize Sentry SDK if DSN is configured.

    MUST be called before importing FastMCP so that the OTEL TracerProvider
    is set up before FastMCP creates its tracer.
    """
    if sentry_sdk is None:
        logger.debug("Sentry SDK not installed, skipping init")
        return

    if not settings.sentry_dsn:
        logger.debug("Sentry DSN not set, skipping init")
        return

    from sentry_sdk.integrations import Integration
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    integrations: list[Integration] = [FastApiIntegration()]

    try:
        from sentry_sdk.integrations.mcp import MCPIntegration

        integrations.append(MCPIntegration())
    except ImportError:
        logger.warning("sentry_sdk.integrations.mcp not available, skipping MCPIntegration")

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=settings.sentry_send_pii,
        environment=settings.environment,
        integrations=integrations,
    )
    logger.info("Sentry initialized", extra={"environment": settings.environment})


# Initialize Sentry BEFORE importing FastMCP
_init_sentry()

from fastmcp.utilities.lifespan import combine_lifespans  # noqa: E402

from app.database import close_db, init_db  # noqa: E402
from app.errors import register_error_handlers  # noqa: E402
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
