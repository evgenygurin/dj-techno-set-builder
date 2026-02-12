from app.models.catalog import Genre
from app.repositories.base import BaseRepository


class GenreRepository(BaseRepository[Genre]):
    model = Genre
