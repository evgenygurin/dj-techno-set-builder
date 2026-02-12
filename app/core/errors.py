"""Centralized application error hierarchy.

All domain errors MUST inherit from ``AppError``.
The global exception handler in ``handlers.py`` converts them
into a unified JSON envelope automatically — no try/except
duplication in business code.
"""

from __future__ import annotations


class AppError(Exception):
    """Base application error."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "Internal server error", *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, message: str = "Resource not found", **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, message: str = "Validation failed", **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"

    def __init__(self, message: str = "Resource conflict", **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"

    def __init__(self, message: str = "Authentication required", **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"

    def __init__(self, message: str = "Forbidden", **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]


class InternalError(AppError):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str = "Internal server error", **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]
