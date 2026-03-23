"""Service for GA-based DJ set generation."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.errors import NotFoundError, ValidationError
from app.models.features import TrackAudioFeaturesComputed
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.playlists import DjPlaylistItemRepository
from app.repositories.sections import SectionsRepository
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.schemas.set_generation import SetGenerationRequest, SetGenerationResponse
from app.services.base import BaseService
from app.services.transition_scoring import TrackFeatures, TransitionScoringService
from app.utils.audio.energy_arcs import EnergyArcType
from app.utils.audio.feature_conversion import orm_to_track_data
from app.utils.audio.set_generator import (
    GAConfig,
    GAConstraints,
    GeneticSetGenerator,
    TrackData,
)
from app.utils.audio.set_templates import SetSlot, TemplateName, get_template

# Default track count when neither template nor explicit count is provided.
# Prevents runaway GA on large playlists (O(n^3) complexity).
_DEFAULT_SET_SIZE = 20


def _build_matrix_two_tier(
    scorer: TransitionScoringService,
    features: list[TrackFeatures],
    tier1_threshold: float = 0.15,
) -> np.ndarray:
    """Build NxN transition matrix using two-tier scoring.

    Tier 1 (cheap): ``quick_score()`` — BPM + harmonic + energy only.
    Tier 2 (expensive): ``score_transition()`` — full 6-component with MFCC.

    Pairs where quick_score < tier1_threshold keep the cheap score (skip tier 2).
    When ``score_transition()`` returns 0.0 (hard-reject), the quick_score is
    used instead so **no pair ever gets zero** (Nina Kraviz principle).

    Args:
        scorer: Pre-configured TransitionScoringService instance.
        features: List of TrackFeatures for all tracks.
        tier1_threshold: Cutoff for tier 2 promotion. 0.0 = always full score.

    Returns:
        NxN numpy matrix of transition scores.
    """
    n = len(features)
    matrix = np.zeros((n, n), dtype=np.float64)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            quick = scorer.quick_score(features[i], features[j])
            if quick < tier1_threshold:
                matrix[i, j] = quick
            else:
                full = scorer.score_transition(features[i], features[j])
                matrix[i, j] = full if full > 0.0 else quick

    return matrix


class SetGenerationService(BaseService):
    """Orchestrates GA-based track ordering for DJ sets."""

    def __init__(
        self,
        set_repo: DjSetRepository,
        version_repo: DjSetVersionRepository,
        item_repo: DjSetItemRepository,
        features_repo: AudioFeaturesRepository,
        sections_repo: SectionsRepository | None = None,
        playlist_repo: DjPlaylistItemRepository | None = None,
    ) -> None:
        super().__init__()
        self.set_repo = set_repo
        self.version_repo = version_repo
        self.item_repo = item_repo
        self.features_repo = features_repo
        self.sections_repo = sections_repo
        self.playlist_repo = playlist_repo

    async def _load_artist_map(self, track_ids: list[int]) -> dict[int, int]:
        """Load primary artist_id for each track (role=0)."""
        from sqlalchemy import select

        from app.models.catalog import TrackArtist

        artist_map: dict[int, int] = {}
        if track_ids:
            stmt = (
                select(TrackArtist.track_id, TrackArtist.artist_id)
                .where(TrackArtist.track_id.in_(track_ids))
                .where(TrackArtist.role == 0)
            )
            rows = await self.features_repo.session.execute(stmt)
            for row in rows:
                artist_map[row.track_id] = row.artist_id
        return artist_map

    async def generate(self, set_id: int, data: SetGenerationRequest) -> SetGenerationResponse:
        """Generate optimal track ordering for a DJ set using genetic algorithm.

        Args:
            set_id: ID of the DJ set to generate tracklist for
            data: GA configuration and preferences

        Returns:
            SetGenerationResponse with the generated version and fitness details

        Raises:
            NotFoundError: If set_id doesn't exist
            ValidationError: If no tracks with features available
        """
        self.logger.info(
            "generate: set_id=%d, config=%s", set_id, data.model_dump(exclude_none=True)
        )

        # Verify set exists
        dj_set = await self.set_repo.get_by_id(set_id)
        if not dj_set:
            raise NotFoundError("DjSet", set_id=set_id)

        # Fetch all tracks with features
        features_list = await self.features_repo.list_all()
        if not features_list:
            raise ValidationError("No tracks with audio features available for set generation")

        # Filter to playlist tracks if specified
        if data.playlist_id is not None and self.playlist_repo is not None:
            items, _ = await self.playlist_repo.list_by_playlist(data.playlist_id, limit=1000)
            allowed_ids = {item.track_id for item in items}
            features_list = [f for f in features_list if f.track_id in allowed_ids]
            if not features_list:
                raise ValidationError(
                    f"No tracks with audio features in playlist {data.playlist_id}"
                )

        # Filter out excluded tracks BEFORE building any data structures (matrix, mood_map, etc.)
        # Must happen early so that matrix size matches the tracks list size exactly.
        if data.exclude_track_ids:
            excluded_early = set(data.exclude_track_ids)
            features_list = [f for f in features_list if f.track_id not in excluded_early]
            if not features_list:
                raise ValidationError("All tracks were excluded — cannot generate set")

        # Batch-load sections for structure scoring
        sections_map: dict[int, list[Any]] = {}
        if self.sections_repo is not None:
            track_ids = [f.track_id for f in features_list]
            sections_map = await self.sections_repo.get_latest_by_track_ids(track_ids)

        # Load primary artist_id for each track (for variety scoring in GA)
        artist_map = await self._load_artist_map([f.track_id for f in features_list])

        # Build TrackData list via unified converter (fixes hp_ratio default bug)
        tracks = [
            orm_to_track_data(f, artist_id=artist_map.get(f.track_id, 0))
            for f in features_list
        ]

        # Build features map once — reused by transition matrix builder
        features_map = {f.track_id: f for f in features_list}

        # Build transition matrix using two-tier scoring
        transition_matrix = await self._build_transition_matrix_scored(
            tracks,
            features_map=features_map,
            tier1_threshold=data.tier1_threshold,
            sections_map=sections_map,
        )

        # Load template slots if specified
        template_slots: list[SetSlot] = []
        data_track_count: int | None = data.track_count
        if data.template_name:
            template = get_template(TemplateName(data.template_name))
            template_slots = list(template.slots)
            # Set track_count from template if not explicitly specified
            if data.track_count is None and template.target_track_count > 0:
                data_track_count = template.target_track_count

        # Safety cap: without template or explicit track_count, default to 20
        # to prevent runaway GA on large playlists (O(n^3) complexity)
        if data_track_count is None and not template_slots:
            data_track_count = _DEFAULT_SET_SIZE
            self.logger.info(
                "No template/track_count — defaulting to %d tracks",
                data_track_count,
            )

        # Configure GA — rebalance weights when template is active
        config = GAConfig(
            population_size=data.population_size,
            generations=data.generations,
            mutation_rate=data.mutation_rate,
            crossover_rate=data.crossover_rate,
            tournament_size=data.tournament_size,
            elitism_count=data.elitism_count,
            track_count=data_track_count,
            energy_arc_type=EnergyArcType(data.energy_arc_type),
            seed=data.seed,
            w_template=0.25 if template_slots else 0.0,
            w_transition=0.35 if template_slots else data.w_transition,
            w_energy_arc=0.20 if template_slots else data.w_energy_arc,
            w_bpm_smooth=0.10 if template_slots else data.w_bpm_smooth,
            w_variety=0.10 if template_slots else 0.20,
        )

        # Build GA constraints from pinned/excluded
        constraints: GAConstraints | None = None
        if data.pinned_track_ids or data.exclude_track_ids:
            constraints = GAConstraints(
                pinned_ids=frozenset(data.pinned_track_ids or []),
                excluded_ids=frozenset(data.exclude_track_ids or []),
            )

        # Run GA
        gen = GeneticSetGenerator(
            tracks,
            transition_matrix,
            config,
            template_slots=template_slots,
            constraints=constraints,
        )
        result = gen.run()
        self.logger.info(
            "GA complete: score=%.4f, tracks=%d, generations=%d",
            result.score,
            len(result.track_ids),
            result.generations_run,
        )

        # Create set version
        version = await self.version_repo.create(
            set_id=set_id,
            version_label=data.version_label or f"GA-{result.generations_run}gen",
            generator_run={
                "algorithm": "genetic",
                "generations": result.generations_run,
                "config": {
                    "population_size": config.population_size,
                    "mutation_rate": config.mutation_rate,
                    "crossover_rate": config.crossover_rate,
                    "energy_arc_type": config.energy_arc_type,
                },
                "weights": {
                    "transition": config.w_transition,
                    "template": config.w_template,
                    "energy_arc": config.w_energy_arc,
                    "bpm_smooth": config.w_bpm_smooth,
                    "variety": config.w_variety,
                },
                "template_name": data.template_name,
            },
        )

        # Create set items
        for sort_index, track_id in enumerate(result.track_ids):
            await self.item_repo.create(
                set_version_id=version.set_version_id,
                track_id=track_id,
                sort_index=sort_index,
            )

        return SetGenerationResponse(
            set_version_id=version.set_version_id,
            score=result.score,
            track_ids=result.track_ids,
            transition_scores=result.transition_scores,
            fitness_history=result.fitness_history,
            energy_arc_score=result.energy_arc_score,
            bpm_smoothness_score=result.bpm_smoothness_score,
            generator_run=version.generator_run or {},
        )

    def _build_transition_matrix(self, tracks: list[TrackData]) -> np.ndarray:
        """Build a simple BPM+key transition matrix (lightweight fallback).

        The primary path uses ``_build_transition_matrix_scored`` which calls
        ``TransitionScoringService`` for full 6-component scoring. This method
        exists as a cheap fallback when features are unavailable.
        """
        n = len(tracks)
        matrix = np.zeros((n, n), dtype=np.float64)

        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i, j] = 0.0
                    continue

                # BPM similarity component (0-0.5)
                bpm_diff = abs(tracks[i].bpm - tracks[j].bpm)
                bpm_score = max(0.0, 0.5 - bpm_diff / 20.0)

                # Key compatibility component (0-0.5) — simple placeholder
                key_diff = abs(tracks[i].key_code - tracks[j].key_code)
                key_score = max(0.0, 0.5 - key_diff / 24.0)

                matrix[i, j] = bpm_score + key_score

        return matrix

    async def _build_transition_matrix_scored(
        self,
        tracks: list[TrackData],
        features_map: dict[int, TrackAudioFeaturesComputed],
        tier1_threshold: float = 0.15,
        sections_map: dict[int, list[Any]] | None = None,
    ) -> np.ndarray:
        """Build transition quality matrix using two-tier scoring.

        Uses ``_build_matrix_two_tier()`` for tracks with full features.
        Falls back to primitive BPM+key scoring for tracks missing features.

        Args:
            tracks: List of tracks with basic features (bpm, energy, key_code)
            features_map: Pre-built map of track_id → TrackAudioFeaturesComputed
            tier1_threshold: quick_score cutoff for full scoring (0.0 = always full)
            sections_map: Optional map of track_id → sections for structure scoring

        Returns:
            NxN matrix where [i, j] = quality of i→j transition
        """
        import logging
        import time

        from app.services.camelot_lookup import CamelotLookupService
        from app.utils.audio.feature_conversion import orm_features_to_track_features

        logger = logging.getLogger(__name__)

        n = len(tracks)

        # Build DB-backed Camelot lookup
        camelot_service = CamelotLookupService(self.features_repo.session)
        lookup_table = await camelot_service.build_lookup_table()
        scorer = TransitionScoringService(camelot_lookup=lookup_table)

        # Build feature objects via canonical conversion (with section data)
        smap = sections_map or {}
        track_features: list[TrackFeatures | None] = []
        for track in tracks:
            feat_db = features_map.get(track.track_id)
            if feat_db is None:
                track_features.append(None)
                continue
            secs = smap.get(track.track_id)
            track_features.append(orm_features_to_track_features(feat_db, secs))

        # Separate tracks with features from those without
        has_features = [f is not None for f in track_features]
        featured_indices = [i for i, h in enumerate(has_features) if h]
        # All items are non-None because we filtered via has_features
        featured_list: list[TrackFeatures] = [f for f in track_features if f is not None]

        t0 = time.perf_counter()

        # Two-tier scoring for tracks with features
        if featured_list:
            sub_matrix = _build_matrix_two_tier(
                scorer,
                featured_list,
                tier1_threshold=tier1_threshold,
            )
        else:
            sub_matrix = np.zeros((0, 0), dtype=np.float64)

        elapsed = time.perf_counter() - t0

        # Map sub-matrix back to full NxN
        matrix = np.zeros((n, n), dtype=np.float64)
        for si, gi in enumerate(featured_indices):
            for sj, gj in enumerate(featured_indices):
                matrix[gi, gj] = sub_matrix[si, sj]

        # Fallback for tracks without features
        for i in range(n):
            for j in range(n):
                if i == j or (has_features[i] and has_features[j]):
                    continue
                bpm_diff = abs(tracks[i].bpm - tracks[j].bpm)
                bpm_score = max(0.0, 0.5 - bpm_diff / 20.0)
                key_diff = abs(tracks[i].key_code - tracks[j].key_code)
                key_score = max(0.0, 0.5 - key_diff / 24.0)
                matrix[i, j] = bpm_score + key_score

        total_pairs = n * (n - 1)
        featured_pairs = len(featured_indices) * (len(featured_indices) - 1)
        logger.info(
            "Transition matrix %dx%d built in %.2fs "
            "(total_pairs=%d, featured_pairs=%d, tier1_threshold=%.2f)",
            n,
            n,
            elapsed,
            total_pairs,
            featured_pairs,
            tier1_threshold,
        )

        return matrix
