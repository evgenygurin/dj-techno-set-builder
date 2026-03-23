from app.models.catalog import Genre
from app.infrastructure.repositories.base import BaseRepository


class GenreRepository(BaseRepository[Genre]):
    model = Genre
