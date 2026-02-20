"""MCP type definitions — entities, responses, workflows, curation.

Re-exports all types for backward-compatible ``from app.mcp.types import X``.
"""

from app.mcp.types.curation import (
    ClassifyResult,
    CurateCandidate,
    CurateSetResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
    SetReviewResult,
    WeakTransition,
)
from app.mcp.types.entities import (
    ArtistSummary,
    PlaylistDetail,
    PlaylistSummary,
    SetDetail,
    SetSummary,
    TrackDetail,
    TrackSummary,
)
from app.mcp.types.responses import (
    ActionResponse,
    EntityDetailResponse,
    EntityListResponse,
    FindResult,
    LibraryStats,
    MatchStats,
    PaginationInfo,
    SearchResponse,
)
from app.mcp.types.workflows import (
    AdjustmentPlan,
    ExportResult,
    ReorderSuggestion,
    SearchStrategy,
    SetBuildResult,
    SimilarTracksResult,
    SwapSuggestion,
    TransitionScoreResult,
)

__all__ = [
    "ActionResponse",
    "AdjustmentPlan",
    "ArtistSummary",
    "ClassifyResult",
    "CurateCandidate",
    "CurateSetResult",
    "EntityDetailResponse",
    "EntityListResponse",
    "ExportResult",
    "FindResult",
    "GapDescription",
    "LibraryGapResult",
    "LibraryStats",
    "MatchStats",
    "MoodDistribution",
    "PaginationInfo",
    "PlaylistDetail",
    "PlaylistSummary",
    "ReorderSuggestion",
    "SearchResponse",
    "SearchStrategy",
    "SetBuildResult",
    "SetDetail",
    "SetReviewResult",
    "SetSummary",
    "SimilarTracksResult",
    "SwapSuggestion",
    "TrackDetail",
    "TrackSummary",
    "TransitionScoreResult",
    "WeakTransition",
]
