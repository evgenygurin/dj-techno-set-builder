"""Set review service — analyze DJ set quality, transitions, variety, arc.

Extracted from app/mcp/tools/curation.py review_set function.
"""

from __future__ import annotations

from typing import Any

from app.mcp.tools._scoring_helpers import score_consecutive_transitions
from app.mcp.types import SetReviewResult, WeakTransition
from app.services.features import AudioFeaturesService
from app.services.set_curation import SetCurationService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.utils.audio.feature_conversion import orm_to_track_data
from app.utils.audio.set_generator import variety_score


async def review_set_version(
    *,
    set_id: int,
    version_id: int,
    template: str,
    set_svc: DjSetService,
    unified_svc: UnifiedTransitionScoringService,
    features_svc: AudioFeaturesService,
    track_svc: TrackService,
) -> SetReviewResult:
    """Review a DJ set version — transition quality, variety, energy arc.

    Returns SetReviewResult with overall_score, weak transitions, suggestions.
    """
    set_obj = await set_svc.get(set_id)
    items_list = await set_svc.list_items(version_id, offset=0, limit=500)

    actual_template = set_obj.template_name or template
    items = sorted(items_list.items, key=lambda i: i.sort_index)

    if len(items) < 2:
        return SetReviewResult(
            overall_score=0.0,
            energy_arc_adherence=0.0,
            variety_score=0.0,
            weak_transitions=[],
            suggestions=["Set too short"],
        )

    svc = SetCurationService()

    # Score all transitions
    score_results = await score_consecutive_transitions(
        items, unified_svc, track_svc, features_svc
    )

    weak: list[WeakTransition] = []
    scores: list[float] = []
    for i, sr in enumerate(score_results):
        scores.append(sr.total)
        if sr.total < 0.4:
            weak.append(
                WeakTransition(
                    position=i,
                    from_track_id=sr.from_track_id,
                    to_track_id=sr.to_track_id,
                    score=round(sr.total, 3),
                    reason=(
                        "Low transition quality" if sr.total > 0
                        else "Missing features"
                    ),
                )
            )

    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Variety scoring
    all_features = await features_svc.list_all()
    feat_map: dict[int, Any] = {f.track_id: f for f in all_features}

    track_data_list = [
        orm_to_track_data(feat_map[item.track_id])
        for item in items
        if item.track_id in feat_map
    ]
    var_score = variety_score(track_data_list) if track_data_list else 0.0

    # Energy arc adherence
    track_lufs: list[float | None] = []
    for item in items:
        if item.track_id in feat_map:
            track_lufs.append(feat_map[item.track_id].lufs_i)
        else:
            track_lufs.append(None)

    arc_score = 0.0
    if sum(1 for x in track_lufs if x is not None) >= 2:
        arc_score = svc.compute_energy_arc_adherence_with_gaps(
            track_lufs, actual_template
        )

    suggestions: list[str] = []
    if weak:
        suggestions.append(f"{len(weak)} weak transitions (score < 0.4)")
    if var_score < 0.7:
        suggestions.append(
            "Low variety — consider diversifying mood/key sequences"
        )
    if arc_score < 0.5:
        suggestions.append(
            f"Energy arc adherence is low ({arc_score:.1%}) — "
            f"set does not follow {actual_template} template energy curve"
        )

    return SetReviewResult(
        overall_score=round(avg_score, 3),
        energy_arc_adherence=arc_score,
        variety_score=round(var_score, 3),
        weak_transitions=weak,
        suggestions=suggestions,
    )
