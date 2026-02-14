"""Pydantic models for MCP tool structured output."""

from __future__ import annotations

from pydantic import BaseModel


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


class ExportResult(BaseModel):
    """Result of exporting a set."""

    set_id: int
    format: str
    track_count: int
    content: str
