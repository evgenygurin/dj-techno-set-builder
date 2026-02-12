from app.models.features import TrackAudioFeaturesComputed
from app.repositories.base import BaseRepository


class AudioFeaturesRepository(BaseRepository[TrackAudioFeaturesComputed]):
    model = TrackAudioFeaturesComputed
