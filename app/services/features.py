from app.errors import NotFoundError
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.schemas.features import AudioFeaturesList, AudioFeaturesRead
from app.services.base import BaseService


class AudioFeaturesService(BaseService):
    def __init__(
        self,
        features_repo: AudioFeaturesRepository,
        track_repo: TrackRepository,
    ) -> None:
        super().__init__()
        self.features_repo = features_repo
        self.track_repo = track_repo

    async def get_latest(self, track_id: int) -> AudioFeaturesRead:
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        features = await self.features_repo.get_by_track(track_id)
        if not features:
            raise NotFoundError("AudioFeatures", track_id=track_id)
        return AudioFeaturesRead.model_validate(features)

    async def list_all(self) -> list[AudioFeaturesRead]:
        """Get latest features for every track (one row per track_id)."""
        rows = await self.features_repo.list_all()
        return [AudioFeaturesRead.model_validate(r) for r in rows]

    async def list_for_track(
        self,
        track_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> AudioFeaturesList:
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        items, total = await self.features_repo.list_by_track(
            track_id,
            offset=offset,
            limit=limit,
        )
        return AudioFeaturesList(
            items=[AudioFeaturesRead.model_validate(f) for f in items],
            total=total,
        )
