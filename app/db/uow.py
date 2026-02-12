"""Unit of Work — thin wrapper around ``AsyncSession`` lifecycle.

Usage::

    async with UnitOfWork(session) as uow:
        repo = SomeRepository(uow.session)
        repo.add(entity)
        await uow.commit()
    # auto-rollback if commit() was not called
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    """Async context-manager that owns a single DB transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._committed = False

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def commit(self) -> None:
        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self._session.rollback()

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if not self._committed:
            await self.rollback()
        await self._session.close()
