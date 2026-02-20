"""Workflow result types for DJ MCP tools."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = [
    "AdjustmentPlan",
    "ExportResult",
    "ReorderSuggestion",
    "SearchStrategy",
    "SetBuildResult",
    "SimilarTracksResult",
    "SwapSuggestion",
    "TransitionScoreResult",
]


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
