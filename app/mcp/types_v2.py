"""Pydantic models for MCP tool structured output (v2).

Consolidated from legacy types.py and types_curation.py.
Dead-code types removed: PlaylistStatus, TrackDetails, ImportResult,
AnalysisResult, SwapSuggestion, ReorderSuggestion, AdjustmentPlan,
CurateCandidate, CurateSetResult.
"""

from __future__ import annotations

from pydantic import BaseModel

# --- Set builder types ---


class SetBuildResult(BaseModel):
    """Result of building/optimizing a DJ set."""

    set_id: int
    version_id: int
    track_count: int
    total_score: float
    avg_transition_score: float
    energy_curve: list[float] = []


class TransitionScoreResult(BaseModel):
    """Transition score between two tracks."""

    from_track_id: int
    to_track_id: int
    from_title: str
    to_title: str
    total: float
    bpm: float
    harmonic: float
    energy: float
    spectral: float
    groove: float
    structure: float = 0.5  # Phase 3: section-aware score
    recommended_type: str | None = None  # Phase 3: TransitionType value
    type_confidence: float | None = None
    reason: str | None = None
    alt_type: str | None = None


class ExportResult(BaseModel):
    """Result of exporting a set."""

    set_id: int
    format: str
    track_count: int
    content: str


# --- Discovery types ---


class SimilarTracksResult(BaseModel):
    """Result of finding similar tracks."""

    playlist_id: int
    candidates_found: int
    candidates_selected: int
    added_count: int


class SearchStrategy(BaseModel):
    """LLM-generated search strategy for finding similar tracks."""

    queries: list[str]
    target_bpm_range: tuple[float, float]
    target_keys: list[str]
    target_energy_range: tuple[float, float]
    reasoning: str


# --- Curation types ---


class MoodDistribution(BaseModel):
    """Distribution of tracks across mood categories."""

    mood: str
    count: int
    percentage: float


class ClassifyResult(BaseModel):
    """Result of classifying tracks by mood."""

    total_classified: int
    distribution: list[MoodDistribution]


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
