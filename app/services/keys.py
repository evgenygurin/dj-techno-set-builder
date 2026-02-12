from app.errors import NotFoundError
from app.repositories.keys import KeyRepository
from app.schemas.keys import KeyList, KeyRead
from app.services.base import BaseService


class KeyService(BaseService):
    def __init__(self, repo: KeyRepository) -> None:
        super().__init__()
        self.repo = repo

    async def get(self, key_code: int) -> KeyRead:
        key = await self.repo.get_by_id(key_code)
        if not key:
            raise NotFoundError("Key", key_code=key_code)
        return KeyRead.model_validate(key)

    async def list(self, *, offset: int = 0, limit: int = 50) -> KeyList:
        items, total = await self.repo.list(offset=offset, limit=limit)
        return KeyList(
            items=[KeyRead.model_validate(k) for k in items],
            total=total,
        )
