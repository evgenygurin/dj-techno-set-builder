"""Set curation service — classify tracks and select by template slots.

Orchestrates mood classification and greedy slot-based selection.
No DB dependency — works with feature objects passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.audio.mood_classifier import TrackMood, classify_track
from app.utils.audio.set_templates import SetSlot, TemplateName, get_template


@dataclass(frozen=True, slots=True)
class CandidateTrack:
    """A track selected for a set with slot scoring metadata."""

    track_id: int
    mood: TrackMood
    slot_score: float
    bpm: float
    lufs_i: float
    key_code: int


class SetCurationService:
    """Classify tracks by mood and select candidates for set templates."""

    def classify_features(
        self,
        features: list[Any],
    ) -> dict[int, TrackMood]:
        """Classify a list of ORM feature objects by mood.

        Args:
            features: List of TrackAudioFeaturesComputed-like objects.

        Returns:
            Mapping of track_id -> TrackMood.
        """
        result: dict[int, TrackMood] = {}
        for feat in features:
            classification = classify_track(
                bpm=feat.bpm,
                lufs_i=feat.lufs_i,
                kick_prominence=feat.kick_prominence or 0.5,
                spectral_centroid_mean=feat.centroid_mean_hz or 2500.0,
                onset_rate=feat.onset_rate_mean or 5.0,
                hp_ratio=feat.hp_ratio or 0.5,
            )
            result[feat.track_id] = classification.mood
        return result

    def mood_distribution(
        self,
        classified: dict[int, TrackMood],
    ) -> dict[TrackMood, int]:
        """Count tracks per mood category."""
        dist: dict[TrackMood, int] = {m: 0 for m in TrackMood}
        for mood in classified.values():
            dist[mood] += 1
        return dist

    def select_candidates(
        self,
        features: list[Any],
        template_name: str,
        exclude_ids: set[int] | None = None,
        target_count: int | None = None,
    ) -> list[CandidateTrack]:
        """Select tracks for a template using greedy slot matching.

        Args:
            features: ORM feature objects with audio attributes.
            template_name: Template name string (e.g. "classic_60").
            exclude_ids: Track IDs to exclude from selection.
            target_count: Override template's target count.

        Returns:
            Ordered list of CandidateTrack.
        """
        template = get_template(TemplateName(template_name))
        excluded = exclude_ids or set()

        # Classify all tracks
        classified = self.classify_features(features)

        # Build feature lookup
        feat_map: dict[int, Any] = {f.track_id: f for f in features}

        # Use template slots or generate simple slots for full library
        slots = template.slots
        if not slots:
            # FULL_LIBRARY: no slots, return all tracks sorted by mood intensity
            candidates = []
            for feat in features:
                tid: int = feat.track_id
                if tid in excluded:
                    continue
                mood = classified.get(tid, TrackMood.DRIVING)
                candidates.append(
                    CandidateTrack(
                        track_id=tid,
                        mood=mood,
                        slot_score=0.5,
                        bpm=feat.bpm,
                        lufs_i=feat.lufs_i,
                        key_code=feat.key_code or 0,
                    )
                )
            candidates.sort(key=lambda c: c.mood.intensity)
            return candidates

        # Greedy slot filling
        used_ids: set[int] = set()
        selected: list[CandidateTrack] = []

        for slot in slots:
            best_score = -1.0
            best_tid: int | None = None

            for feat in features:
                tid = feat.track_id
                if tid in used_ids or tid in excluded:
                    continue

                score = self._score_candidate_for_slot(
                    feat,
                    slot,
                    classified.get(tid, TrackMood.DRIVING),
                )
                if score > best_score:
                    best_score = score
                    best_tid = tid

            if best_tid is not None:
                feat_obj = feat_map[best_tid]
                mood = classified.get(best_tid, TrackMood.DRIVING)
                selected.append(
                    CandidateTrack(
                        track_id=best_tid,
                        mood=mood,
                        slot_score=best_score,
                        bpm=feat_obj.bpm,
                        lufs_i=feat_obj.lufs_i,
                        key_code=feat_obj.key_code or 0,
                    )
                )
                used_ids.add(best_tid)

        return selected

    def _score_candidate_for_slot(
        self,
        feat: Any,
        slot: SetSlot,
        track_mood: TrackMood,
    ) -> float:
        """Score a single track against a slot.

        Components:
        - Mood match (40%): exact=1.0, adjacent=0.5, other=0.0
        - Energy fit (30%): closeness of LUFS to target
        - BPM fit (20%): whether BPM falls in slot range
        - Variety (10%): baseline bonus
        """
        bpm: float = feat.bpm
        lufs: float = feat.lufs_i

        # Mood match
        if track_mood == slot.mood:
            mood_score = 1.0
        elif abs(track_mood.intensity - slot.mood.intensity) == 1:
            mood_score = 0.5
        else:
            mood_score = 0.0

        # Energy fit
        energy_diff = abs(lufs - slot.energy_target)
        energy_score = max(0.0, 1.0 - energy_diff / 8.0)

        # BPM fit
        bpm_low, bpm_high = slot.bpm_range
        if bpm_low <= bpm <= bpm_high:
            bpm_score = 1.0
        else:
            bpm_dist = min(abs(bpm - bpm_low), abs(bpm - bpm_high))
            bpm_score = max(0.0, 1.0 - bpm_dist / 10.0)

        # Flexibility adjustment
        mood_weight = 0.40 * (1.0 - slot.flexibility * 0.3)
        energy_weight = 0.30
        bpm_weight = 0.20
        variety_weight = 0.10

        return (
            mood_weight * mood_score
            + energy_weight * energy_score
            + bpm_weight * bpm_score
            + variety_weight * 0.5  # baseline variety
        )
