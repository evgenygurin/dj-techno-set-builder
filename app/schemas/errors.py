from typing import Any

from pydantic import ConfigDict

from app.schemas.base import BaseSchema


class ErrorResponse(BaseSchema):
    model_config = ConfigDict(from_attributes=False, extra="allow")

    code: str
    message: str
    details: dict[str, Any] | None = None
