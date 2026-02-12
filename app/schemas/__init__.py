"""Pydantic schema package."""

from __future__ import annotations

from app.schemas.catalog import ReleaseDTO, TrackArtistDTO, TrackDTO
from app.schemas.dj import (
    DjAppExportDTO,
    DjBeatgridChangePointDTO,
    DjBeatgridDTO,
    DjCuePointDTO,
    DjPlaylistItemDTO,
    DjSavedLoopDTO,
)
from app.schemas.features import (
    AudioAssetDTO,
    FeatureExtractionRunDTO,
    KeyDTO,
    TrackAudioFeatureComputedDTO,
    TrackSectionDTO,
    TransitionCandidateDTO,
    TransitionDTO,
    TransitionRunDTO,
)
from app.schemas.providers import (
    BeatportMetadataDTO,
    ProviderTrackIdDTO,
    SpotifyAudioFeatureDTO,
    SpotifyMetadataDTO,
)
from app.schemas.sets import DjSetDTO, DjSetFeedbackDTO, DjSetItemDTO, DjSetVersionDTO

__all__ = [
    "AudioAssetDTO",
    "BeatportMetadataDTO",
    "DjAppExportDTO",
    "DjBeatgridChangePointDTO",
    "DjBeatgridDTO",
    "DjCuePointDTO",
    "DjPlaylistItemDTO",
    "DjSavedLoopDTO",
    "DjSetDTO",
    "DjSetFeedbackDTO",
    "DjSetItemDTO",
    "DjSetVersionDTO",
    "FeatureExtractionRunDTO",
    "KeyDTO",
    "ProviderTrackIdDTO",
    "ReleaseDTO",
    "SpotifyAudioFeatureDTO",
    "SpotifyMetadataDTO",
    "TrackArtistDTO",
    "TrackAudioFeatureComputedDTO",
    "TrackDTO",
    "TrackSectionDTO",
    "TransitionCandidateDTO",
    "TransitionDTO",
    "TransitionRunDTO",
]
