from app.errors import NotFoundError
from app.repositories.artists import ArtistRepository
from app.schemas.artists import ArtistCreate, ArtistList, ArtistRead, ArtistUpdate
from app.services.base import BaseService


class ArtistService(BaseService):
    def __init__(self, repo: ArtistRepository) -> None:
        super().__init__()
        self.repo = repo

    async def get(self, artist_id: int) -> ArtistRead:
        artist = await self.repo.get_by_id(artist_id)
        if not artist:
            raise NotFoundError("Artist", artist_id=artist_id)
        return ArtistRead.model_validate(artist)

    async def list(
        self, *, offset: int = 0, limit: int = 50, search: str | None = None
    ) -> ArtistList:
        if search:
            items, total = await self.repo.search_by_name(search, offset=offset, limit=limit)
        else:
            items, total = await self.repo.list(offset=offset, limit=limit)
        return ArtistList(
            items=[ArtistRead.model_validate(a) for a in items],
            total=total,
        )

    async def create(self, data: ArtistCreate) -> ArtistRead:
        artist = await self.repo.create(**data.model_dump())
        return ArtistRead.model_validate(artist)

    async def update(self, artist_id: int, data: ArtistUpdate) -> ArtistRead:
        artist = await self.repo.get_by_id(artist_id)
        if not artist:
            raise NotFoundError("Artist", artist_id=artist_id)
        updated = await self.repo.update(artist, **data.model_dump(exclude_unset=True))
        return ArtistRead.model_validate(updated)

    async def delete(self, artist_id: int) -> None:
        artist = await self.repo.get_by_id(artist_id)
        if not artist:
            raise NotFoundError("Artist", artist_id=artist_id)
        await self.repo.delete(artist)
