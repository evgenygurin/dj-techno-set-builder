"""Application error hierarchy.

Framework-free exception classes with structured error data.
Used by services and MCP tools.
"""

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        message: str = "Internal server error",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str = "Resource", **kwargs: Any) -> None:
        super().__init__(
            status_code=404,
            code="NOT_FOUND",
            message=f"{resource} not found",
            details=kwargs or None,
        )


class ValidationError(AppError):
    def __init__(self, message: str = "Validation error", **kwargs: Any) -> None:
        super().__init__(
            status_code=422,
            code="VALIDATION_ERROR",
            message=message,
            details=kwargs or None,
        )


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", **kwargs: Any) -> None:
        super().__init__(
            status_code=409,
            code="CONFLICT",
            message=message,
            details=kwargs or None,
        )
