"""Pydantic models for curation MCP tool structured output."""

from __future__ import annotations

from pydantic import BaseModel


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


class WeakTransition(BaseModel):
    """A weak transition identified during review."""

    position: int
    from_track_id: int
    to_track_id: int
    score: float
    reason: str


class SetReviewResult(BaseModel):
    """Result of reviewing a set version."""

    overall_score: float
    energy_arc_adherence: float
    variety_score: float
    weak_transitions: list[WeakTransition]
    suggestions: list[str]


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
