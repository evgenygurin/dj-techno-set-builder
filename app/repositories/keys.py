from app.models.harmony import Key
from app.repositories.base import BaseRepository


class KeyRepository(BaseRepository[Key]):
    model = Key
