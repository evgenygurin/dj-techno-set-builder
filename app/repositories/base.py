from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base


class BaseRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _pk_column(self) -> Any:
        pk = self.model.__table__.primary_key
        return next(iter(pk))

    async def get_by_id(self, pk: int) -> ModelT | None:
        stmt = select(self.model).where(self._pk_column() == pk)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        filters: list[Any] | None = None,
    ) -> tuple[list[ModelT], int]:
        base: Select[tuple[ModelT]] = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)

        if filters:
            for f in filters:
                base = base.where(f)
                count_stmt = count_stmt.where(f)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(offset).limit(limit).order_by(self._pk_column())
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        allowed = {c.name for c in self.model.__table__.columns}
        for key, value in kwargs.items():
            if key not in allowed:
                raise ValueError(f"Invalid column for {self.model.__name__}: {key}")
            if value is not None:
                setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()
