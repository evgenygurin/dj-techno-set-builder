"""Generic async repository base class."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Executable, Result, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    """Provides basic CRUD helpers over a single SQLAlchemy model.

    Subclasses must set ``model`` to the concrete ORM class::

        class TrackRepository(BaseRepository[Track]):
            model = Track
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get_by_id(self, entity_id: object) -> ModelT | None:
        return await self._session.get(self.model, entity_id)

    async def list_all(self, *, offset: int = 0, limit: int = 100) -> Sequence[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    def add(self, entity: ModelT) -> None:
        self._session.add(entity)

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)

    async def execute(self, stmt: Executable) -> Result[Any]:
        """Execute an arbitrary SQLAlchemy statement."""
        return await self._session.execute(stmt)
