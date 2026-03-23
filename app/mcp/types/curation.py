"""Pydantic models for curation MCP tool structured output."""

from __future__ import annotations

from pydantic import BaseModel

# Re-exported from domain layer (source of truth: app.services.transition_types)
from app.services.transition_types import SetReviewResult as SetReviewResult
from app.services.transition_types import WeakTransition as WeakTransition

__all__ = [
    "ClassifyResult",
    "CurateCandidate",
    "CurateSetResult",
    "DistributeResult",
    "GapDescription",
    "LibraryGapResult",
    "MoodDistribution",
    "SetReviewResult",
    "WeakTransition",
]


class MoodDistribution(BaseModel):
    """Distribution of tracks across mood categories."""

    mood: str
    count: int
    percentage: float


class ClassifyResult(BaseModel):
    """Result of classifying tracks by mood."""

    total_classified: int
    distribution: list[MoodDistribution]


class CurateCandidate(BaseModel):
    """A candidate track selected for a set."""

    track_id: int
    mood: str
    slot_score: float
    bpm: float
    lufs_i: float


class CurateSetResult(BaseModel):
    """Result of curating tracks for a set template."""

    template: str
    target_count: int
    selected_count: int
    candidates: list[CurateCandidate]
    mood_distribution: list[MoodDistribution]
    warnings: list[str]


class GapDescription(BaseModel):
    """Description of a library gap."""

    mood: str
    needed: int
    available: int
    deficit: int


class LibraryGapResult(BaseModel):
    """Result of analyzing library gaps."""

    total_tracks: int
    tracks_with_features: int
    mood_distribution: list[MoodDistribution]
    gaps: list[GapDescription]
    recommendations: list[str]


class DistributeResult(BaseModel):
    """Result of distributing tracks to subgenre playlists."""

    total_classified: int
    no_features: int
    distribution: dict[str, int]
    added_to_playlists: int
    already_in_playlist: int
