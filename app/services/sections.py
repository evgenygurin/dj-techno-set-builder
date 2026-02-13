from app.errors import NotFoundError
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.schemas.sections import SectionList, SectionRead
from app.services.base import BaseService


class SectionsService(BaseService):
    def __init__(
        self,
        sections_repo: SectionsRepository,
        track_repo: TrackRepository,
    ) -> None:
        super().__init__()
        self.sections_repo = sections_repo
        self.track_repo = track_repo

    async def list_for_track(
        self,
        track_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> SectionList:
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        items, total = await self.sections_repo.list_by_track(
            track_id,
            offset=offset,
            limit=limit,
        )
        return SectionList(
            items=[SectionRead.model_validate(s) for s in items],
            total=total,
        )
