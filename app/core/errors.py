from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


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


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)
