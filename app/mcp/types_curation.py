"""Backward-compatibility re-exports — use app.mcp.schemas instead."""

from app.mcp.schemas import (
    ClassifyResult,
    CurateCandidate,
    CurateSetResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
    SetReviewResult,
    WeakTransition,
)

__all__ = [
    "ClassifyResult",
    "CurateCandidate",
    "CurateSetResult",
    "GapDescription",
    "LibraryGapResult",
    "MoodDistribution",
    "SetReviewResult",
    "WeakTransition",
]
