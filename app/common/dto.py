"""Base DTO (Data Transfer Object) built on Pydantic v2."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BaseDTO(BaseModel):
    """All request / response schemas inherit from this class.

    * ``from_attributes`` — allows ``Model.model_validate(orm_obj)``
    * ``extra="forbid"`` — rejects unknown fields early
    * ``populate_by_name`` — accept both alias and field name
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        populate_by_name=True,
    )
