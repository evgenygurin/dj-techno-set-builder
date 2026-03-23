"""Shared scoring helpers extracted from delivery / setbuilder / curation tools.

Avoids duplication of the score-consecutive-transitions loop and
filesystem-safe name sanitisation across multiple MCP tools.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.errors import NotFoundError
from app.services.features import AudioFeaturesService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.services.transition_types import TransitionScoreResult
from app.utils.audio.camelot import key_code_to_camelot
from app.utils.text_sort import sanitize_filename as sanitize_filename

# ── Transition scoring ────────────────────────────────────────────────────────


async def score_consecutive_transitions(
    items: list[Any],
    unified_svc: UnifiedTransitionScoringService,
    track_svc: TrackService,
    features_svc: AudioFeaturesService,
) -> list[TransitionScoreResult]:
    """Score all consecutive track pairs in a set version.

    Parameters
    ----------
    items:
        ``DjSetItemRead`` objects **already sorted by sort_index**.
    unified_svc:
        The unified transition scoring service (injected via DI).
    track_svc:
        Track service for title lookup.
    features_svc:
        Audio-features service for transition-type recommendation
        and audio-context fields (BPM, key, camelot distance).

    Returns
    -------
    list[TransitionScoreResult]
        One result per consecutive pair.  When scoring fails the
        result has ``total=0.0`` and all sub-scores zeroed.
    """
    if len(items) < 2:
        return []

    # Build track title lookup
    title_map: dict[int, str] = {}
    for item in items:
        with contextlib.suppress(NotFoundError):
            track = await track_svc.get(item.track_id)
            title_map[item.track_id] = track.title

    results: list[TransitionScoreResult] = []
    for i in range(len(items) - 1):
        from_item = items[i]
        to_item = items[i + 1]
        from_title = title_map.get(from_item.track_id, f"Track {from_item.track_id}")
        to_title = title_map.get(to_item.track_id, f"Track {to_item.track_id}")

        try:
            components = await unified_svc.score_components_by_ids(
                from_item.track_id,
                to_item.track_id,
            )
        except ValueError:
            results.append(
                TransitionScoreResult(
                    from_track_id=from_item.track_id,
                    to_track_id=to_item.track_id,
                    from_title=from_title,
                    to_title=to_title,
                    total=0.0,
                    bpm=0.0,
                    harmonic=0.0,
                    energy=0.0,
                    spectral=0.0,
                    groove=0.0,
                )
            )
            continue

        # Transition type recommendation + audio context
        rec_type: str | None = None
        rec_confidence: float | None = None
        rec_reason: str | None = None
        rec_alt: str | None = None
        from_bpm_val: float | None = None
        to_bpm_val: float | None = None
        from_key_val: str | None = None
        to_key_val: str | None = None
        cam_dist_val: int | None = None
        bpm_delta_val: float | None = None

        try:
            from app.services.transition_type import recommend_transition
            from app.utils.audio.camelot import camelot_distance
            from app.utils.audio.feature_conversion import orm_features_to_track_features

            feat_a = await features_svc.get_latest(from_item.track_id)
            feat_b = await features_svc.get_latest(to_item.track_id)
            tf_a = orm_features_to_track_features(feat_a)  # type: ignore[arg-type]
            tf_b = orm_features_to_track_features(feat_b)  # type: ignore[arg-type]
            cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)

            rec = recommend_transition(tf_a, tf_b, camelot_compatible=cam_dist <= 1)
            rec_type = str(rec.transition_type)
            rec_confidence = rec.confidence
            rec_reason = rec.reason
            rec_alt = str(rec.alt_type) if rec.alt_type else None

            # Audio context fields
            from_bpm_val = tf_a.bpm
            to_bpm_val = tf_b.bpm
            with contextlib.suppress(ValueError):
                from_key_val = key_code_to_camelot(tf_a.key_code)
                to_key_val = key_code_to_camelot(tf_b.key_code)
            cam_dist_val = cam_dist
            if tf_a.bpm and tf_b.bpm:
                bpm_delta_val = abs(tf_a.bpm - tf_b.bpm)
        except (NotFoundError, ValueError):
            pass

        results.append(
            TransitionScoreResult(
                from_track_id=from_item.track_id,
                to_track_id=to_item.track_id,
                from_title=from_title,
                to_title=to_title,
                total=components["total"],
                bpm=components["bpm"],
                harmonic=components["harmonic"],
                energy=components["energy"],
                spectral=components["spectral"],
                groove=components["groove"],
                structure=components.get("structure", 0.5),
                recommended_type=rec_type,
                type_confidence=rec_confidence,
                reason=rec_reason,
                alt_type=rec_alt,
                from_bpm=from_bpm_val,
                to_bpm=to_bpm_val,
                from_key=from_key_val,
                to_key=to_key_val,
                camelot_distance=cam_dist_val,
                bpm_delta=bpm_delta_val,
            )
        )

    return results
