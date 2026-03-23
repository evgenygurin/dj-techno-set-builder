from app.core.errors import NotFoundError
from app.infrastructure.repositories.genres import GenreRepository
from app.schemas.genres import GenreCreate, GenreList, GenreRead, GenreUpdate
from app.services.base import BaseService


class GenreService(BaseService):
    def __init__(self, repo: GenreRepository) -> None:
        super().__init__()
        self.repo = repo

    async def get(self, genre_id: int) -> GenreRead:
        genre = await self.repo.get_by_id(genre_id)
        if not genre:
            raise NotFoundError("Genre", genre_id=genre_id)
        return GenreRead.model_validate(genre)

    async def list(self, *, offset: int = 0, limit: int = 50) -> GenreList:
        items, total = await self.repo.list(offset=offset, limit=limit)
        return GenreList(
            items=[GenreRead.model_validate(g) for g in items],
            total=total,
        )

    async def create(self, data: GenreCreate) -> GenreRead:
        genre = await self.repo.create(**data.model_dump())
        return GenreRead.model_validate(genre)

    async def update(self, genre_id: int, data: GenreUpdate) -> GenreRead:
        genre = await self.repo.get_by_id(genre_id)
        if not genre:
            raise NotFoundError("Genre", genre_id=genre_id)
        updated = await self.repo.update(genre, **data.model_dump(exclude_unset=True))
        return GenreRead.model_validate(updated)

    async def delete(self, genre_id: int) -> None:
        genre = await self.repo.get_by_id(genre_id)
        if not genre:
            raise NotFoundError("Genre", genre_id=genre_id)
        await self.repo.delete(genre)
