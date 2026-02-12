from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """created_at + updated_at (for tables with UPDATE triggers in DDL)."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CreatedAtMixin:
    """created_at only (for append-only tables like sections, embeddings, feedback)."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
