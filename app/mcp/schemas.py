"""Pydantic models for MCP tool structured output.

Consolidates all MCP response types: DJ workflow models, curation models,
and structured output envelopes. This is the single source of truth for
MCP tool return types.
"""

from __future__ import annotations

from pydantic import BaseModel

# ── DJ Workflow Models ──────────────────────────────────────────────────


class PlaylistStatus(BaseModel):
    """Status of a DJ playlist including analysis progress."""

    playlist_id: int
    name: str
    total_tracks: int
    analyzed_tracks: int
    bpm_range: tuple[float, float] | None = None
    keys: list[str] = []
    avg_energy: float | None = None
    duration_minutes: float = 0.0


class TrackDetails(BaseModel):
    """Full track details with audio features."""

    track_id: int
    title: str
    artists: str
    duration_ms: int | None = None
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None
    has_features: bool = False


class ImportResult(BaseModel):
    """Result of a playlist/track import operation."""

    playlist_id: int
    imported_count: int
    skipped_count: int
    enriched_count: int


class AnalysisResult(BaseModel):
    """Result of audio analysis on a playlist."""

    playlist_id: int
    analyzed_count: int
    failed_count: int
    bpm_range: tuple[float, float] | None = None
    keys: list[str] = []


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


class SwapSuggestion(BaseModel):
    """Suggestion to swap a track at a given position."""

    position: int
    reason: str


class ReorderSuggestion(BaseModel):
    """Suggestion to move a track to a new position."""

    from_position: int
    to_position: int
    reason: str


class AdjustmentPlan(BaseModel):
    """LLM-generated plan for adjusting a DJ set."""

    reasoning: str
    swap_suggestions: list[SwapSuggestion] = []
    reorder_suggestions: list[ReorderSuggestion] = []


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
    structure: float = 0.5
    recommended_type: str | None = None
    type_confidence: float | None = None
    reason: str | None = None
    alt_type: str | None = None


class ExportResult(BaseModel):
    """Result of exporting a set."""

    set_id: int
    format: str
    track_count: int
    content: str


# ── Curation Models ─────────────────────────────────────────────────────


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
