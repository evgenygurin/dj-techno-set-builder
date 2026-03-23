"""Genetic algorithm for DJ set track ordering.

Optimises the sequence of tracks in a DJ set by maximising a fitness function
that combines transition quality, energy arc adherence, and BPM smoothness.

Pure computation — no DB or ORM dependencies.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from app.domain.setbuilder.templates import SetSlot


class EnergyArcType(StrEnum):
    """Predefined energy arc shapes for techno sets."""

    CLASSIC = "classic"  # intro → buildup → peak → breakdown → peak2 → outro
    PROGRESSIVE = "progressive"  # slow linear rise to a single peak, then drop
    ROLLER = "roller"  # sustained high energy with minimal valleys
    WAVE = "wave"  # multiple peaks and troughs


@dataclass(frozen=True, slots=True)
class GAConfig:
    """Configuration for the genetic algorithm."""

    population_size: int = 100
    generations: int = 200
    mutation_rate: float = 0.15
    crossover_rate: float = 0.8
    tournament_size: int = 5
    elitism_count: int = 2
    track_count: int | None = None  # None = use all tracks
    energy_arc_type: EnergyArcType = EnergyArcType.CLASSIC
    seed: int | None = None
    # Fitness weights (should sum to ~1.0)
    # Without template: 0.40 + 0.25 + 0.15 + 0.20 + 0.00 = 1.0
    # With template:    0.35 + 0.20 + 0.10 + 0.10 + 0.25 = 1.0
    w_transition: float = 0.40
    w_energy_arc: float = 0.25
    w_bpm_smooth: float = 0.15
    w_variety: float = 0.20
    w_template: float = 0.0  # 0.0 = no template, 0.25 = recommended with template


@dataclass(frozen=True, slots=True)
class TrackData:
    """Lightweight track representation for the GA."""

    track_id: int
    bpm: float
    energy: float  # 0-1, global energy proxy (LUFS-mapped or energy_mean)
    key_code: int
    mood: int = 0  # TrackMood.intensity (1-6), 0 = unclassified
    artist_id: int = 0  # for variety scoring


@dataclass(frozen=True, slots=True)
class GAConstraints:
    """Constraints for rebuild — pinned tracks must stay, excluded are banned."""

    pinned_ids: frozenset[int] = frozenset()
    excluded_ids: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class GAResult:
    """Result of a GA run."""

    track_ids: list[int]
    score: float  # best fitness
    transition_scores: list[float]  # quality between consecutive pairs
    fitness_history: list[float]  # best fitness per generation
    energy_arc_score: float
    bpm_smoothness_score: float
    generations_run: int


# Re-export fitness functions at module level for backward compatibility.
# These were originally defined here; now they live in fitness.py.
from app.domain.setbuilder.genetic.fitness import (  # noqa: E402
    lufs_to_energy,
    target_energy_curve,
    template_slot_fit,
    variety_score,
)

# Sets larger than this use lightweight local search instead of full 2-opt
# in the GA loop. Full 2-opt is O(n³) — 1.2s per pass at n=214, called
# 19,650 times → 73,000+ seconds. _relocate_worst is O(n) → ~0.1ms.
_LARGE_SET_THRESHOLD = 40


class GeneticSetGenerator:
    """Genetic algorithm that orders tracks to maximise set quality.

    Args:
        tracks: Available tracks with features.
        transition_matrix: Pre-computed NxN quality matrix (indexed by track position
            in *tracks* list). ``transition_matrix[i][j]`` = quality of i→j transition.
        config: GA hyperparameters.
    """

    def __init__(
        self,
        tracks: list[TrackData],
        transition_matrix: NDArray[np.float64],
        config: GAConfig | None = None,
        template_slots: list[SetSlot] | None = None,
        constraints: GAConstraints | None = None,
    ) -> None:
        self.config = config or GAConfig()
        self._rng = random.Random(self.config.seed)
        self._np_rng = np.random.default_rng(self.config.seed)
        self._constraints = constraints or GAConstraints()

        # Determine working set
        n = len(tracks)
        use_n = min(self.config.track_count, n) if self.config.track_count else n

        self._all_tracks = tracks
        self._n = use_n
        self._matrix = transition_matrix.astype(np.float64)
        self._energies = np.array([t.energy for t in tracks], dtype=np.float64)
        self._bpms = np.array([t.bpm for t in tracks], dtype=np.float64)
        self._target = target_energy_curve(use_n, self.config.energy_arc_type)
        self._template_slots = template_slots or []

        # Pre-compute pinned track indices for constraint enforcement
        pinned_track_ids = self._constraints.pinned_ids
        self._pinned_indices: frozenset[int] = frozenset(
            i for i, t in enumerate(tracks) if t.track_id in pinned_track_ids
        )
        excluded_track_ids = self._constraints.excluded_ids
        self._excluded_indices: frozenset[int] = frozenset(
            i for i, t in enumerate(tracks) if t.track_id in excluded_track_ids
        )

    def run(self) -> GAResult:
        """Execute the genetic algorithm. Returns the best solution found.

        Adaptive local search strategy based on set size:

        - **n ≤ 40**: Full ``_two_opt()`` on every child (original behaviour).
        - **n > 40**: ``_relocate_worst()`` per child in the GA loop, then
          ``_two_opt(max_passes=5)`` on the single best solution at the end.
          This drops 214-track runtime from 73,000s → ~9s.
        """
        from app.domain.setbuilder.genetic.local_search import relocate_worst, two_opt
        from app.domain.setbuilder.genetic.operators import (
            mutate,
            mutate_replace,
            order_crossover,
        )

        n_all = len(self._all_tracks)
        cfg = self.config
        large = self._n > _LARGE_SET_THRESHOLD

        # Initial population
        population = self._init_population(n_all, self._n, cfg.population_size)
        fitnesses = np.array([self._fitness(ch) for ch in population])

        best_idx = int(np.argmax(fitnesses))
        best_chromosome = population[best_idx].copy()
        best_fitness = fitnesses[best_idx]
        fitness_history: list[float] = [float(best_fitness)]

        for _gen in range(cfg.generations):
            new_pop: list[NDArray[np.int32]] = []

            # Elitism: carry over top individuals
            elite_indices = np.argsort(fitnesses)[-cfg.elitism_count :]
            for ei in elite_indices:
                new_pop.append(population[ei].copy())

            # Fill rest via selection + crossover + mutation
            while len(new_pop) < cfg.population_size:
                p1 = self._tournament_select(population, fitnesses)
                p2 = self._tournament_select(population, fitnesses)

                if self._rng.random() < cfg.crossover_rate:
                    child = order_crossover(p1, p2, self._rng, self._pinned_indices)
                else:
                    child = p1.copy()

                if self._rng.random() < cfg.mutation_rate:
                    mutate(child, self._rng, self._pinned_indices)

                # Track replacement mutation (5% chance)
                mutate_replace(
                    child,
                    self._rng,
                    n_all,
                    self._pinned_indices,
                    self._excluded_indices,
                )

                # Local search: lightweight for large sets, full 2-opt for small
                if large:
                    relocate_worst(child, self._matrix)
                else:
                    two_opt(child, self._fitness)

                new_pop.append(child)

            population = new_pop[: cfg.population_size]
            fitnesses = np.array([self._fitness(ch) for ch in population])

            gen_best_idx = int(np.argmax(fitnesses))
            if fitnesses[gen_best_idx] > best_fitness:
                best_fitness = fitnesses[gen_best_idx]
                best_chromosome = population[gen_best_idx].copy()

            fitness_history.append(float(best_fitness))

        # Final polish: full 2-opt on best solution only (capped for large sets)
        if large:
            two_opt(best_chromosome, self._fitness, max_passes=5)
            best_fitness = self._fitness(best_chromosome)
            fitness_history.append(float(best_fitness))

        # Build result from best chromosome
        track_ids = [self._all_tracks[i].track_id for i in best_chromosome]
        transition_scores = self._get_transition_scores(best_chromosome)
        energy_arc = self._energy_arc_score(best_chromosome)
        bpm_smooth = self._bpm_smoothness_score(best_chromosome)

        return GAResult(
            track_ids=track_ids,
            score=float(best_fitness),
            transition_scores=transition_scores,
            fitness_history=fitness_history,
            energy_arc_score=float(energy_arc),
            bpm_smoothness_score=float(bpm_smooth),
            generations_run=cfg.generations,
        )

    # ── Population ──────────────────────────────────────────

    def _nearest_neighbor_path(
        self, start: int, candidates: NDArray[np.int32]
    ) -> NDArray[np.int32]:
        """Build a greedy path starting from *start*, picking best neighbor.

        Args:
            start: Index of starting track in self._all_tracks.
            candidates: Array of track indices to visit.

        Returns:
            Ordered path as array of track indices.
        """
        n = len(candidates)
        visited = np.zeros(len(self._all_tracks), dtype=bool)
        path = np.empty(n, dtype=np.int32)

        current = start
        path[0] = current
        visited[current] = True

        for step in range(1, n):
            best_score = -1.0
            best_next = candidates[0]
            for c in candidates:
                if not visited[c] and self._matrix[current, c] > best_score:
                    best_score = self._matrix[current, c]
                    best_next = c
            path[step] = best_next
            visited[best_next] = True
            current = best_next

        return path

    def _make_valid_subset(self, n_all: int, n_select: int) -> NDArray[np.int32]:
        """Create a random subset that includes all pinned and excludes all excluded."""
        # Start with pinned indices (must be included)
        pinned = list(self._pinned_indices)
        # Available pool: not excluded and not already pinned
        available = [
            i
            for i in range(n_all)
            if i not in self._excluded_indices and i not in self._pinned_indices
        ]
        self._rng.shuffle(available)

        # Fill remaining slots from available pool
        need = n_select - len(pinned)
        if need < 0:
            need = 0
        filler = available[:need]
        subset = np.array(pinned + filler, dtype=np.int32)
        self._np_rng.shuffle(subset)
        return subset

    def _nn_anchored_spread(self, subset: NDArray[np.int32]) -> NDArray[np.int32]:
        """Build NN path with multiple pinned tracks spread as segment anchors.

        When there are ≥2 pinned tracks, divides the subset into K equal segments
        (K = number of pinned tracks) and seeds each segment from its designated
        pinned anchor.  This prevents pinned tracks from clustering together in the
        initial population and gives the GA a better starting point.

        Falls back to a single-anchor NN path when there are 0-1 pinned tracks.

        Args:
            subset: Array of track indices to arrange (all tracks for this chromosome).

        Returns:
            Ordered chromosome with pinned tracks distributed across segments.
        """
        pinned_in_subset = [i for i in subset if i in self._pinned_indices]
        k = len(pinned_in_subset)

        if k < 2:
            # Standard NN: single starting point
            start = int(self._np_rng.choice(subset))
            return self._nearest_neighbor_path(start, subset)

        # Shuffle pinned anchors so segment assignment varies across individuals
        self._rng.shuffle(pinned_in_subset)

        # Non-pinned tracks to distribute across segments
        non_pinned = [i for i in subset if i not in self._pinned_indices]
        self._rng.shuffle(non_pinned)

        # Distribute non-pinned roughly evenly across k segments
        n_non = len(non_pinned)
        base_size = n_non // k
        remainder = n_non % k

        segments: list[NDArray[np.int32]] = []
        pos = 0
        for seg_idx, anchor in enumerate(pinned_in_subset):
            extra = 1 if seg_idx < remainder else 0
            seg_non_pinned = non_pinned[pos : pos + base_size + extra]
            pos += base_size + extra

            seg_array = np.array([anchor, *seg_non_pinned], dtype=np.int32)
            seg_path = self._nearest_neighbor_path(anchor, seg_array)
            segments.append(seg_path)

        return np.concatenate(segments)

    def _init_population(
        self, n_all: int, n_select: int, pop_size: int
    ) -> list[NDArray[np.int32]]:
        """Create initial population: 50% NN-seeded (+ local search), 50% random.

        For large sets (n > ``_LARGE_SET_THRESHOLD``), NN-seeded individuals get
        ``_relocate_worst`` instead of full ``_two_opt`` to avoid O(n³) cost.

        If constraints are set, every individual includes all pinned track
        indices and excludes all excluded indices.

        When multiple pinned tracks are present, NN-seeded individuals are
        initialised using ``_nn_anchored_spread`` so that pinned tracks act as
        segment anchors and are distributed across the chromosome rather than
        clustering at the start.
        """
        from app.domain.setbuilder.genetic.local_search import relocate_worst, two_opt

        population: list[NDArray[np.int32]] = []
        large = n_select > _LARGE_SET_THRESHOLD
        has_constraints = bool(self._pinned_indices or self._excluded_indices)
        spread_pinned = len(self._pinned_indices) >= 2

        nn_count = pop_size // 2

        # NN-seeded individuals
        for _ in range(nn_count):
            if has_constraints:
                subset = self._make_valid_subset(n_all, n_select)
            else:
                indices = np.arange(n_all, dtype=np.int32)
                perm = self._np_rng.permutation(indices)
                subset = perm[:n_select].copy()

            if spread_pinned:
                # Anchor each pinned track to its own segment, fill via NN
                path = self._nn_anchored_spread(subset)
            else:
                start_idx = int(self._np_rng.choice(subset))
                path = self._nearest_neighbor_path(start_idx, subset)

            if large:
                for _r in range(min(n_select, 50)):
                    relocate_worst(path, self._matrix)
            else:
                two_opt(path, self._fitness)
            population.append(path)

        # Random individuals
        for _ in range(pop_size - nn_count):
            if has_constraints:
                subset = self._make_valid_subset(n_all, n_select)
            else:
                indices = np.arange(n_all, dtype=np.int32)
                perm = self._np_rng.permutation(indices)
                subset = perm[:n_select].copy()
            population.append(subset)

        return population

    # ── Fitness ─────────────────────────────────────────────

    def _pinned_spread_score(self, chromosome: NDArray[np.int32]) -> float:
        """Score how well pinned tracks are spread throughout the set (1.0 = ideal).

        With K pinned tracks in a set of N, the ideal gap between consecutive
        pinned positions is N/K.  Scores 1.0 when no two pinned tracks are
        adjacent (gap ≥ 2); approaches 0.0 when all pinned tracks cluster
        together.

        Returns 1.0 when there are fewer than 2 pinned tracks (no spread
        requirement with a single mandatory track).
        """
        k = len(self._pinned_indices)
        if k < 2:
            return 1.0

        n = len(chromosome)
        positions = [i for i in range(n) if chromosome[i] in self._pinned_indices]
        if len(positions) < 2:
            return 1.0

        adjacent_pairs = sum(
            1 for i in range(len(positions) - 1) if positions[i + 1] - positions[i] <= 1
        )
        return max(0.0, 1.0 - adjacent_pairs / (len(positions) - 1))

    def _fitness(self, chromosome: NDArray[np.int32]) -> float:
        """Evaluate fitness of a chromosome (higher = better).

        When pinned constraints are present a multiplicative spread bonus is
        applied so that configurations where pinned tracks cluster together are
        penalised relative to configurations where they are well-distributed:

        * perfect spread (no adjacent pinned) -> x1.00 (no penalty)
        * all pinned adjacent -> x0.85 (15 % penalty)
        """
        cfg = self.config
        transition = self._mean_transition_quality(chromosome)
        arc = self._energy_arc_score(chromosome)
        bpm = self._bpm_smoothness_score(chromosome)
        var = self._variety_score(chromosome)

        tmpl = 0.5  # neutral if no template
        if self._template_slots:
            ordered_tracks = [self._all_tracks[i] for i in chromosome]
            tmpl = template_slot_fit(ordered_tracks, self._template_slots)

        score = (
            cfg.w_transition * transition
            + cfg.w_template * tmpl
            + cfg.w_energy_arc * arc
            + cfg.w_bpm_smooth * bpm
            + cfg.w_variety * var
        )

        # Multiplicative spread bonus: encourages pinned tracks to be
        # distributed throughout the set rather than clustered.
        # Adjacent pinned pair -> 15% discount; all spread -> no discount.
        if self._pinned_indices:
            spread = self._pinned_spread_score(chromosome)
            score *= 0.85 + 0.15 * spread

        return score

    def _mean_transition_quality(self, chromosome: NDArray[np.int32]) -> float:
        """Average transition quality across consecutive pairs."""
        if len(chromosome) < 2:
            return 0.0
        total = 0.0
        for k in range(len(chromosome) - 1):
            total += self._matrix[chromosome[k], chromosome[k + 1]]
        return total / (len(chromosome) - 1)

    def _energy_arc_score(self, chromosome: NDArray[np.int32]) -> float:
        """1 - RMSE(actual_energy, target_curve). Higher = better match."""
        actual = self._energies[chromosome]
        rmse = float(np.sqrt(np.mean((actual - self._target) ** 2)))
        return max(0.0, 1.0 - rmse)

    def _bpm_smoothness_score(self, chromosome: NDArray[np.int32]) -> float:
        """Penalise large BPM jumps between consecutive tracks.

        Score = 1 - mean_delta / 20.0, clamped to [0, 1].
        """
        if len(chromosome) < 2:
            return 1.0
        bpms = self._bpms[chromosome]
        deltas = np.abs(np.diff(bpms))
        mean_delta = float(np.mean(deltas))
        return max(0.0, min(1.0, 1.0 - mean_delta / 20.0))

    def _variety_score(self, chromosome: NDArray[np.int32]) -> float:
        """Wrapper for variety_score using chromosome track data."""
        tracks = [self._all_tracks[i] for i in chromosome]
        return variety_score(tracks)

    def _get_transition_scores(self, chromosome: NDArray[np.int32]) -> list[float]:
        """Extract per-pair transition quality for the final result."""
        scores: list[float] = []
        for k in range(len(chromosome) - 1):
            scores.append(float(self._matrix[chromosome[k], chromosome[k + 1]]))
        return scores

    # ── Selection ───────────────────────────────────────────

    def _tournament_select(
        self, population: list[NDArray[np.int32]], fitnesses: NDArray[np.float64]
    ) -> NDArray[np.int32]:
        """Tournament selection: pick best from random subset."""
        size = min(self.config.tournament_size, len(population))
        indices = self._rng.sample(range(len(population)), size)
        best = max(indices, key=lambda i: fitnesses[i])
        return population[best]

    # ── Compatibility proxies for extracted functions ─────────

    def _mutate(self, chromosome: NDArray[np.int32]) -> None:
        """Proxy: delegate to operators.mutate()."""
        from app.domain.setbuilder.genetic.operators import mutate

        mutate(chromosome, self._rng, self._pinned_indices)

    def _mutate_replace(self, chromosome: NDArray[np.int32]) -> None:
        """Proxy: delegate to operators.mutate_replace()."""
        from app.domain.setbuilder.genetic.operators import mutate_replace

        mutate_replace(
            chromosome,
            self._rng,
            len(self._all_tracks),
            self._pinned_indices,
            self._excluded_indices,
        )

    def _order_crossover(self, p1: NDArray[np.int32], p2: NDArray[np.int32]) -> NDArray[np.int32]:
        """Proxy: delegate to operators.order_crossover()."""
        from app.domain.setbuilder.genetic.operators import order_crossover

        return order_crossover(p1, p2, self._rng, self._pinned_indices)

    def _two_opt(self, chromosome: NDArray[np.int32], max_passes: int | None = None) -> None:
        """Proxy: delegate to local_search.two_opt()."""
        from app.domain.setbuilder.genetic.local_search import two_opt

        two_opt(chromosome, self._fitness, max_passes=max_passes)

    def _relocate_worst(self, chromosome: NDArray[np.int32]) -> None:
        """Proxy: delegate to local_search.relocate_worst()."""
        from app.domain.setbuilder.genetic.local_search import relocate_worst

        relocate_worst(chromosome, self._matrix)
