"""Set curation service — classify tracks and select by template slots.

Orchestrates mood classification and greedy slot-based selection.
No DB dependency — works with feature objects passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.audio.mood_classifier import TrackMood, classify_track
from app.audio.set_templates import SetSlot, SetTemplate, TemplateName, get_template


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

    TECHNO_LUFS_RANGE_DB = 8.0  # Full dynamic range for techno (-14 to -6 LUFS)

    @staticmethod
    def _normalize_lufs_error(actual: float, expected: float) -> float:
        """Return normalized LUFS error in [0.0, 1.0]."""
        return min(1.0, abs(actual - expected) / SetCurationService.TECHNO_LUFS_RANGE_DB)

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
                hp_ratio=feat.hp_ratio or 2.0,
                flux_mean=getattr(feat, "flux_mean", None) or 0.18,
                flux_std=getattr(feat, "flux_std", None) or 0.10,
                energy_std=getattr(feat, "energy_std", None) or 0.13,
                energy_mean=getattr(feat, "energy_mean", None) or 0.22,
                lra_lu=getattr(feat, "lra_lu", None) or 6.6,
                crest_factor_db=getattr(feat, "crest_factor_db", None) or 13.3,
                flatness_mean=getattr(feat, "flatness_mean", None) or 0.06,
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

    def compute_energy_arc_adherence(
        self,
        track_lufs_values: list[float],
        template_name: str = "classic_60",
    ) -> float:
        """Compare actual energy curve against template expected curve.

        Computes how well the ordered LUFS values of a set follow the
        energy arc defined by a template's slots.

        Args:
            track_lufs_values: LUFS values for tracks in set order.
            template_name: Template to compare against.

        Returns:
            Adherence score [0.0, 1.0] where 1.0 = perfect match.
        """
        n = len(track_lufs_values)
        if n < 2:
            return 0.0

        template = get_template(TemplateName(template_name))
        if not template.slots:
            return 1.0  # FULL_LIBRARY — no arc to adhere to

        total_error = 0.0
        for i, lufs in enumerate(track_lufs_values):
            pos = i / (n - 1)
            expected_lufs = self._interpolate_template_energy(template, pos)
            error = self._normalize_lufs_error(lufs, expected_lufs)
            total_error += error

        return round(max(0.0, 1.0 - total_error / n), 3)

    def compute_energy_arc_adherence_with_gaps(
        self,
        track_lufs_values: list[float | None],
        template_name: str = "classic_60",
    ) -> float:
        """Compare actual energy curve against template, handling missing features.

        Similar to compute_energy_arc_adherence but accepts None values for
        tracks without extracted features. Preserves original set positions
        and penalizes missing features appropriately.

        Args:
            track_lufs_values: LUFS values or None for tracks in set order.
            template_name: Template to compare against.

        Returns:
            Adherence score [0.0, 1.0] where 1.0 = perfect match.
        """
        n = len(track_lufs_values)
        if n < 2:
            return 0.0

        template = get_template(TemplateName(template_name))
        if not template.slots:
            return 1.0  # FULL_LIBRARY — no arc to adhere to

        total_error = 0.0
        valid_tracks = 0

        for i, lufs in enumerate(track_lufs_values):
            pos = i / (n - 1)
            expected_lufs = self._interpolate_template_energy(template, pos)

            if lufs is not None:
                # Track has features - compute normal error
                error = self._normalize_lufs_error(lufs, expected_lufs)
                total_error += error
                valid_tracks += 1
            else:
                # Missing features - apply penalty
                # Use max error (1.0) to discourage gaps
                total_error += 1.0

        # Score based on all positions (including gaps)
        return round(max(0.0, 1.0 - total_error / n), 3)

    @staticmethod
    def _interpolate_template_energy(template: SetTemplate, pos: float) -> float:
        """Interpolate expected energy (LUFS) at a normalized position.

        Finds the two template slots bracketing the position and
        linearly interpolates the energy_target between them.
        """
        slots = template.slots
        # Edge cases: clamp to first/last slot
        if pos <= slots[0].position:
            return slots[0].energy_target
        if pos >= slots[-1].position:
            return slots[-1].energy_target

        # Find bracketing slots
        for j in range(len(slots) - 1):
            if slots[j].position <= pos <= slots[j + 1].position:
                span = slots[j + 1].position - slots[j].position
                if span == 0:
                    return slots[j].energy_target
                t = (pos - slots[j].position) / span
                return slots[j].energy_target + t * (
                    slots[j + 1].energy_target - slots[j].energy_target
                )

        return slots[-1].energy_target  # fallback

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
        energy_score = max(0.0, 1.0 - self._normalize_lufs_error(lufs, slot.energy_target))

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
