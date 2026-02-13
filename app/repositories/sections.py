from app.models.sections import TrackSection
from app.repositories.base import BaseRepository


class SectionsRepository(BaseRepository[TrackSection]):
    model = TrackSection
