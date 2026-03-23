"""Workflow result types for DJ MCP tools."""

from __future__ import annotations

from pydantic import BaseModel

# Re-exported from domain layer (source of truth: app.services.transition_types)
from app.services.transition_types import TransitionScoreResult as TransitionScoreResult
from app.services.transition_types import TransitionSummary as TransitionSummary

__all__ = [
    "AdjustmentPlan",
    "DeliveryResult",
    "ExportResult",
    "ReorderSuggestion",
    "SearchStrategy",
    "SetBuildResult",
    "SetCheatSheet",
    "SetTrackItem",
    "SetVersionSummary",
    "SimilarTracksResult",
    "SwapSuggestion",
    "TransitionScoreResult",
    "TransitionSummary",
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
    auto_rebuild_iterations: int = 0


class ExportResult(BaseModel):
    """Result of exporting a set."""

    set_id: int
    format: str
    track_count: int
    content: str


class SetVersionSummary(BaseModel):
    """Summary of a single DJ set version."""

    version_id: int
    version_label: str | None = None
    created_at: str | None = None  # ISO 8601
    track_count: int = 0
    score: float | None = None


class SetTrackItem(BaseModel):
    """Track with position and audio features for set view (~200 bytes)."""

    position: int  # 1-based play order
    track_id: int
    title: str
    artists: str = ""
    bpm: float | None = None
    key: str | None = None  # Camelot notation e.g. "8A", "11B"
    energy_lufs: float | None = None
    duration_s: int | None = None
    pinned: bool = False


class SetCheatSheet(BaseModel):
    """Structured cheat sheet for a DJ set version."""

    set_id: int
    version_id: int
    set_name: str
    tracks: list[SetTrackItem]
    transitions: list[TransitionScoreResult]
    summary: TransitionSummary
    bpm_range: tuple[float, float] | None = None
    harmonic_chain: list[str] = []
    duration_min: int = 0
    text: str  # Same content as cheat_sheet.txt


class DeliveryResult(BaseModel):
    """Result of delivering a DJ set to files and optionally YM."""

    set_id: int
    version_id: int
    set_name: str
    output_dir: str
    files_written: list[str]
    transitions: TransitionSummary
    mp3_copied: int = 0
    mp3_skipped: int = 0
    ym_playlist_kind: int | None = None
    status: str  # "ok" | "aborted" | "partial"
