"""Shared ORM model utilities and custom SQL types."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from sqlalchemy.types import UserDefinedType

T = TypeVar("T")


class VectorType(UserDefinedType):
    """Minimal pgvector column type.

    Keeps model definitions dialect-agnostic for import-time usage.
    """

    cache_ok = True

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim

    def get_col_spec(self, **_: object) -> str:
        if self.dim is None:
            return "vector"
        return f"vector({self.dim})"


class Int4RangeType(UserDefinedType):
    """PostgreSQL int4range type representation."""

    cache_ok = True

    def get_col_spec(self, **_: object) -> str:
        return "int4range"


def ensure_int_range(
    name: str, value: int | None, *, min_value: int, max_value: int
) -> int | None:
    if value is None:
        return None
    if value < min_value or value > max_value:
        raise ValueError(f"{name} must be between {min_value} and {max_value}")
    return value


def ensure_float_range(
    name: str, value: float | None, *, min_value: float, max_value: float
) -> float | None:
    if value is None:
        return None
    if value < min_value or value > max_value:
        raise ValueError(f"{name} must be between {min_value} and {max_value}")
    return value


def ensure_non_negative_float(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def ensure_non_negative(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def ensure_positive(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def ensure_one_of(name: str, value: T | None, options: Iterable[T]) -> T | None:
    if value is None:
        return None
    allowed = tuple(options)
    if value not in allowed:
        raise ValueError(f"{name} must be one of {allowed}")
    return value
