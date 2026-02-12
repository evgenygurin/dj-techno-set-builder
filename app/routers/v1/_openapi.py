"""Shared OpenAPI response definitions for v1 routers."""

from typing import Any

from app.schemas.errors import ErrorResponse

_NOT_FOUND: dict[str, Any] = {
    "description": "Resource not found",
    "model": ErrorResponse,
}
_CONFLICT: dict[str, Any] = {
    "description": "Resource conflict",
    "model": ErrorResponse,
}

RESPONSES_GET: dict[int | str, dict[str, Any]] = {404: _NOT_FOUND}
RESPONSES_CREATE: dict[int | str, dict[str, Any]] = {409: _CONFLICT}
RESPONSES_UPDATE: dict[int | str, dict[str, Any]] = {404: _NOT_FOUND, 409: _CONFLICT}
RESPONSES_DELETE: dict[int | str, dict[str, Any]] = {404: _NOT_FOUND}
