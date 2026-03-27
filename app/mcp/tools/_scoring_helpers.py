"""Shared scoring helpers extracted from delivery / setbuilder / curation tools.

Avoids duplication of the score-consecutive-transitions loop and
filesystem-safe name sanitisation across multiple MCP tools.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from app.errors import NotFoundError
from app.mcp.types.workflows import TransitionScoreResult
from app.models.enums import SectionType
from app.services.features import AudioFeaturesService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.utils.audio.camelot import key_code_to_camelot

# ── Section mix-point extraction ──────────────────────────────────────────────


def _get_mix_points(
    sections: list[tuple[int, int, int]],
) -> tuple[int | None, int | None]:
    """Extract mix-in (intro start) and mix-out (outro start) from sections.

    Args:
        sections: List of (section_type, start_ms, end_ms) tuples.

    Returns:
        (mix_in_ms, mix_out_ms) — None if section not found.
    """
    mix_in: int | None = None
    mix_out: int | None = None
    for sec_type, start_ms, _end_ms in sections:
        if sec_type == SectionType.INTRO and mix_in is None:
            mix_in = start_ms
        if sec_type == SectionType.OUTRO and (mix_out is None or start_ms > mix_out):
            mix_out = start_ms
    return mix_in, mix_out


# ── Path sanitisation ─────────────────────────────────────────────────────────

_BAD_PATH_RE = re.compile(r'[<>:"/\\|?*]')


def sanitize_filename(name: str) -> str:
    """Replace characters forbidden on Windows/macOS with ``_``."""
    return _BAD_PATH_RE.sub("_", name).strip()


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

    # Batch-load sections for mix points (single query, not N+1)
    from app.repositories.sections import SectionsRepository

    section_map: dict[int, list[tuple[int, int, int]]] = {}
    try:
        session = features_svc._repo._session  # type: ignore[attr-defined]
        sections_repo = SectionsRepository(session)
        all_track_ids = [item.track_id for item in items]
        raw_map = await sections_repo.get_latest_by_track_ids(
            all_track_ids,
        )
        section_map = {
            tid: [(s.section_type, s.start_ms, s.end_ms) for s in secs]
            for tid, secs in raw_map.items()
        }
    except Exception:
        pass  # sections are optional enrichment

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

        # djay Pro AI fields
        djay_bars_val: int | None = None
        djay_bpm_mode_val: str | None = None
        mix_out_ms_val: int | None = getattr(from_item, "mix_out_ms", None)
        mix_in_ms_val: int | None = getattr(to_item, "mix_in_ms", None)

        # Fallback: populate from section data if not set on item
        if mix_out_ms_val is None and from_item.track_id in section_map:
            _, mix_out_ms_val = _get_mix_points(
                section_map[from_item.track_id],
            )
        if mix_in_ms_val is None and to_item.track_id in section_map:
            mix_in_ms_val, _ = _get_mix_points(
                section_map[to_item.track_id],
            )

        try:
            from app.services.transition_type import recommend_transition
            from app.utils.audio.camelot import camelot_distance
            from app.utils.audio.feature_conversion import orm_features_to_track_features

            feat_a = await features_svc.get_latest(from_item.track_id)
            feat_b = await features_svc.get_latest(to_item.track_id)
            tf_a = orm_features_to_track_features(feat_a)  # type: ignore[arg-type]
            tf_b = orm_features_to_track_features(feat_b)  # type: ignore[arg-type]
            cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)

            # Compute set_position (0.0 = first transition, 1.0 = last)
            n_transitions = len(items) - 1
            set_pos = i / n_transitions if n_transitions > 0 else 0.5

            # Compute energy_direction from LUFS (more positive = louder)
            lufs_diff = tf_b.energy_lufs - tf_a.energy_lufs
            energy_dir = "up" if lufs_diff > 0.5 else "down" if lufs_diff < -0.5 else "stable"

            rec = recommend_transition(
                tf_a,
                tf_b,
                camelot_dist=cam_dist,
                set_position=set_pos,
                energy_direction=energy_dir,
            )
            rec_type = str(rec.transition_type)
            rec_confidence = rec.confidence
            rec_reason = rec.reason
            rec_alt = str(rec.alt_type) if rec.alt_type else None
            djay_bars_val = rec.djay_bars
            djay_bpm_mode_val = rec.djay_bpm_mode

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
                djay_bars=djay_bars_val,
                djay_bpm_mode=djay_bpm_mode_val,
                mix_out_ms=mix_out_ms_val,
                mix_in_ms=mix_in_ms_val,
            )
        )

    return results
