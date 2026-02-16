from sqlalchemy import select

from app.models.harmony import Key
from app.repositories.base import BaseRepository


class KeyRepository(BaseRepository[Key]):
    model = Key

    async def get_key_names(
        self,
        key_codes: list[int],
    ) -> dict[int, str]:
        """Batch-load musical key names for given key codes.

        Returns dict[key_code] -> name (e.g. 18 -> "Am").
        """
        if not key_codes:
            return {}
        stmt = select(Key.key_code, Key.name).where(Key.key_code.in_(key_codes))
        result = await self.session.execute(stmt)
        return dict(result.all())
