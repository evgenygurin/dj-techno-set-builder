"""Domain types for transition scoring — framework-agnostic.

These types are the source of truth. MCP types re-export them for
backward compatibility. Services use these directly.
"""

from __future__ import annotations

from pydantic import BaseModel


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
    from_bpm: float | None = None
    to_bpm: float | None = None
    from_key: str | None = None
    to_key: str | None = None
    camelot_distance: int | None = None
    bpm_delta: float | None = None


class TransitionSummary(BaseModel):
    """High-level summary of transition quality for a set version."""

    total: int
    hard_conflicts: int
    weak: int
    avg_score: float
    min_score: float


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
