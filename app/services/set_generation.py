"""Service for GA-based DJ set generation."""

from __future__ import annotations

import numpy as np

from app.errors import NotFoundError, ValidationError
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.schemas.set_generation import SetGenerationRequest, SetGenerationResponse
from app.services.base import BaseService
from app.utils.audio.set_generator import (
    EnergyArcType,
    GAConfig,
    GeneticSetGenerator,
    TrackData,
)


class SetGenerationService(BaseService):
    """Orchestrates GA-based track ordering for DJ sets."""

    def __init__(
        self,
        set_repo: DjSetRepository,
        version_repo: DjSetVersionRepository,
        item_repo: DjSetItemRepository,
        features_repo: AudioFeaturesRepository,
    ) -> None:
        super().__init__()
        self.set_repo = set_repo
        self.version_repo = version_repo
        self.item_repo = item_repo
        self.features_repo = features_repo

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
        # Verify set exists
        dj_set = await self.set_repo.get_by_id(set_id)
        if not dj_set:
            raise NotFoundError("DjSet", set_id=set_id)

        # Fetch all tracks with features
        features_list = await self.features_repo.list_all()
        if not features_list:
            raise ValidationError("No tracks with audio features available for set generation")

        # Build TrackData list (using energy_mean as proxy for global_energy)
        tracks = [
            TrackData(
                track_id=f.track_id,
                bpm=f.bpm,
                energy=f.energy_mean or 0.5,
                key_code=f.key_code or 0,
            )
            for f in features_list
        ]

        # Build transition matrix using TransitionScoringService
        transition_matrix = await self._build_transition_matrix_scored(tracks)

        # Configure GA
        config = GAConfig(
            population_size=data.population_size,
            generations=data.generations,
            mutation_rate=data.mutation_rate,
            crossover_rate=data.crossover_rate,
            tournament_size=data.tournament_size,
            elitism_count=data.elitism_count,
            track_count=data.track_count,
            energy_arc_type=EnergyArcType(data.energy_arc_type),
            seed=data.seed,
            w_transition=data.w_transition,
            w_energy_arc=data.w_energy_arc,
            w_bpm_smooth=data.w_bpm_smooth,
        )

        # Run GA
        gen = GeneticSetGenerator(tracks, transition_matrix, config)
        result = gen.run()

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
                    "energy_arc": config.w_energy_arc,
                    "bpm_smooth": config.w_bpm_smooth,
                },
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
        """Build a simple transition quality matrix.

        TODO: Replace with TransitionScoringService for real scoring.

        For now: higher score if BPM difference is small and keys are compatible.
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
                # TODO: Use Camelot wheel distance
                key_diff = abs(tracks[i].key_code - tracks[j].key_code)
                key_score = max(0.0, 0.5 - key_diff / 24.0)

                matrix[i, j] = bpm_score + key_score

        return matrix

    async def _build_transition_matrix_scored(
        self, tracks: list[TrackData]
    ) -> np.ndarray:
        """Build transition quality matrix using TransitionScoringService.

        Replaces primitive linear scoring with research-backed multi-component formula.

        Args:
            tracks: List of tracks with basic features (bpm, energy, key_code)

        Returns:
            NxN matrix where [i, j] = quality of i→j transition
        """
        from app.services.camelot_lookup import CamelotLookupService
        from app.services.transition_scoring import TrackFeatures, TransitionScoringService

        n = len(tracks)
        matrix = np.zeros((n, n), dtype=np.float64)

        # Build Camelot lookup
        camelot_service = CamelotLookupService()  # No session = uses defaults
        await camelot_service.build_lookup_table()

        # Initialize scoring service
        scorer = TransitionScoringService()
        scorer.camelot_lookup = camelot_service._lookup

        # Fetch full features for all tracks
        features_list = await self.features_repo.list_all()
        features_map = {f.track_id: f for f in features_list}

        # Build feature objects
        track_features: list[TrackFeatures | None] = []
        for track in tracks:
            feat_db = features_map.get(track.track_id)
            if feat_db is None:
                # Fallback to basic TrackData
                track_features.append(None)
                continue

            # Compute harmonic density from chroma if available
            # TODO: Add chroma_entropy computation in audio analysis pipeline
            # For now, use placeholder based on key_confidence
            harmonic_density = feat_db.key_confidence or 0.5

            # Compute band ratios from energy bands
            # [low, mid, high] = [low_energy, mid_energy, high_energy]
            low = feat_db.low_energy or 0.33
            mid = feat_db.mid_energy or 0.33
            high = feat_db.high_energy or 0.34
            total = low + mid + high
            if total > 0:
                band_ratios = [low / total, mid / total, high / total]
            else:
                band_ratios = [0.33, 0.33, 0.34]

            track_features.append(
                TrackFeatures(
                    bpm=feat_db.bpm,
                    energy_lufs=feat_db.lufs_i,
                    key_code=feat_db.key_code or 0,
                    harmonic_density=harmonic_density,
                    centroid_hz=feat_db.centroid_mean_hz or 2000.0,
                    band_ratios=band_ratios,
                    onset_rate=feat_db.onset_rate_mean or 5.0,
                )
            )

        # Compute pairwise scores
        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i, j] = 0.0  # No self-transitions
                    continue

                feat_i = track_features[i]
                feat_j = track_features[j]

                if feat_i is None or feat_j is None:
                    # Fallback to primitive scoring
                    bpm_diff = abs(tracks[i].bpm - tracks[j].bpm)
                    bpm_score = max(0.0, 0.5 - bpm_diff / 20.0)
                    key_diff = abs(tracks[i].key_code - tracks[j].key_code)
                    key_score = max(0.0, 0.5 - key_diff / 24.0)
                    matrix[i, j] = bpm_score + key_score
                else:
                    # Use full scoring formula
                    matrix[i, j] = scorer.score_transition(feat_i, feat_j)

        return matrix
