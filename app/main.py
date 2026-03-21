from __future__ import annotations

# Apply Python 3.13 compatibility patches BEFORE any other imports
from app._compat import apply_python313_compatibility

apply_python313_compatibility()

import logging  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402

from app.config import settings  # noqa: E402

logger = logging.getLogger(__name__)


def _init_sentry() -> None:
    """Initialize Sentry SDK if DSN is configured.

    MUST be called before importing FastMCP so that the OTEL TracerProvider
    is set up before FastMCP creates its tracer.
    """
    if not settings.sentry_dsn:
        logger.debug("Sentry DSN not set, skipping init")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations import Integration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except ImportError:
        logger.warning("sentry_sdk not available, skipping Sentry initialization")
        return

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

# Try to import MCP functionality, disable if not available (Python 3.13 compatibility)
try:
    from fastmcp.utilities.lifespan import combine_lifespans

    from app.mcp import create_dj_mcp

    MCP_AVAILABLE = True
except ImportError as e:
    logger.warning(f"MCP functionality disabled due to import error: {e}")
    MCP_AVAILABLE = False

from app.database import close_db, init_db  # noqa: E402
from app.errors import register_error_handlers  # noqa: E402
from app.middleware import apply_middleware  # noqa: E402
from app.routers import register_routers  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    if MCP_AVAILABLE:
        # Full MCP integration
        mcp = create_dj_mcp()
        mcp_app = mcp.http_app(path="/mcp")

        application = FastAPI(
            title=settings.app_name,
            debug=settings.debug,
            lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
        )
        application.mount("/mcp", mcp_app)
        logger.info("MCP functionality enabled")
    else:
        # Fallback without MCP
        application = FastAPI(
            title=settings.app_name,
            debug=settings.debug,
            lifespan=lifespan,
        )
        logger.warning("MCP functionality disabled - running without MCP endpoints")

    apply_middleware(application)
    register_error_handlers(application)
    register_routers(application)
    return application


app = create_app()
