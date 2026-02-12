"""Global exception handlers for FastAPI.

Converts ``AppError`` (and unexpected exceptions) into a unified
JSON response with ``request_id``.  No stack-trace leaking in prod.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError
from app.core.middleware.request_id import request_id_ctx

logger = logging.getLogger(__name__)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Handle all known application errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "request_id": request_id_ctx.get(""),
        },
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected / unhandled exceptions — never leak internals."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "details": {},
            },
            "request_id": request_id_ctx.get(""),
        },
    )
