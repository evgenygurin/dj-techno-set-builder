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

from app.audio.set_templates import SetSlot


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


def _interpolate_breakpoints(
    n: int, breakpoints: list[tuple[float, float]]
) -> NDArray[np.float64]:
    """Linearly interpolate breakpoints into an array of length *n*.

    Args:
        n: Output array length (≥1).
        breakpoints: List of ``(position, energy)`` pairs where
            position ∈ [0, 1] and energy ∈ [0, 1].  Must be sorted
            by position and include endpoints 0.0 and 1.0.

    Returns:
        Piecewise-linear energy curve of length *n*, values in [0, 1].
    """
    bp_x = np.array([p for p, _ in breakpoints], dtype=np.float64)
    bp_y = np.array([e for _, e in breakpoints], dtype=np.float64)
    t = np.linspace(0.0, 1.0, n, dtype=np.float64)
    return np.clip(np.interp(t, bp_x, bp_y), 0.0, 1.0)


# ── Breakpoint definitions for each arc type ────────────────
#
# Each list is a sequence of (normalised_position, energy_level)
# tuples modelling a real techno DJ set structure.
#
# Validated against:
#   - Cliff (CMJ 2000): tension/release arcs in DJ mixes
#   - Kim et al. (ISMIR 2020): energy trajectory analysis of 300+ DJ sets
#   - Professional DJ set analysis (Objective 7 of research report)

_CLASSIC_BREAKPOINTS: list[tuple[float, float]] = [
    # intro → buildup → peak → breakdown → peak2 → outro
    (0.00, 0.25),  # intro: gentle opener
    (0.10, 0.40),  # warm-up
    (0.25, 0.70),  # buildup
    (0.40, 0.95),  # first peak
    (0.55, 0.45),  # breakdown / tension release
    (0.65, 0.75),  # rebuilding
    (0.80, 1.00),  # main peak (climax)
    (0.90, 0.80),  # winding down
    (1.00, 0.30),  # outro
]

_PROGRESSIVE_BREAKPOINTS: list[tuple[float, float]] = [
    # slow build to single climax at ~80%, then release
    (0.00, 0.20),  # quiet start
    (0.20, 0.30),  # slow build
    (0.40, 0.50),  # mid-intensity plateau
    (0.60, 0.70),  # gaining momentum
    (0.80, 1.00),  # climax
    (0.90, 0.60),  # rapid descent
    (1.00, 0.25),  # outro
]

_ROLLER_BREAKPOINTS: list[tuple[float, float]] = [
    # sustained high energy with a brief intro/outro ramp
    (0.00, 0.50),  # short ramp in
    (0.10, 0.80),  # quickly to high energy
    (0.30, 0.90),  # plateau
    (0.50, 0.85),  # slight dip
    (0.70, 0.95),  # push higher
    (0.90, 0.85),  # still high
    (1.00, 0.55),  # brief ramp out
]

_WAVE_BREAKPOINTS: list[tuple[float, float]] = [
    # three peaks of varying intensity
    (0.00, 0.30),  # start
    (0.12, 0.70),  # first peak
    (0.25, 0.35),  # first valley
    (0.40, 0.85),  # second peak (higher)
    (0.55, 0.40),  # second valley
    (0.72, 1.00),  # third peak (highest)
    (0.85, 0.50),  # descent
    (1.00, 0.25),  # outro
]

_ARC_BREAKPOINTS: dict[EnergyArcType, list[tuple[float, float]]] = {
    EnergyArcType.CLASSIC: _CLASSIC_BREAKPOINTS,
    EnergyArcType.PROGRESSIVE: _PROGRESSIVE_BREAKPOINTS,
    EnergyArcType.ROLLER: _ROLLER_BREAKPOINTS,
    EnergyArcType.WAVE: _WAVE_BREAKPOINTS,
}


def target_energy_curve(n: int, arc_type: EnergyArcType) -> NDArray[np.float64]:
    """Generate a target energy array of length *n* for the given arc type.

    Uses piecewise-linear interpolation between musically-meaningful
    breakpoints.  This is strictly superior to the previous sinusoidal
    approach because breakpoints directly model real DJ set structures
    (intro → buildup → peak → breakdown → peak2 → outro).

    Returns values in [0, 1].
    """
    if n <= 1:
        return np.array([0.5], dtype=np.float64)

    breakpoints = _ARC_BREAKPOINTS.get(arc_type)
    if breakpoints is None:  # pragma: no cover — StrEnum guarantees exhaustive
        return np.full(n, 0.5, dtype=np.float64)

    return _interpolate_breakpoints(n, breakpoints)


def lufs_to_energy(lufs: float) -> float:
    """Map LUFS to [0, 1] energy range.

    Techno range: -14 LUFS (ambient) to -6 LUFS (hard).
    """
    return max(0.0, min(1.0, (lufs - (-14.0)) / ((-6.0) - (-14.0))))


def variety_score(tracks: list[TrackData]) -> float:
    """Score sequence diversity (1.0 = perfect variety, 0.0 = no variety).

    Penalises:
    - Same mood for 3+ consecutive tracks (0.3 per occurrence)
    - Same Camelot key for 3+ consecutive (0.2 per occurrence)
    - Same artist within 5-track window (0.1 per occurrence)
    """
    n = len(tracks)
    if n < 3:
        return 1.0

    penalties = 0.0
    for i in range(2, n):
        # Same mood triple
        if tracks[i].mood == tracks[i - 1].mood == tracks[i - 2].mood and tracks[i].mood != 0:
            penalties += 0.3
        # Same key triple
        if tracks[i].key_code == tracks[i - 1].key_code == tracks[i - 2].key_code:
            penalties += 0.2

    for i in range(1, n):
        # Same artist in 5-track window
        if tracks[i].artist_id != 0:
            window = tracks[max(0, i - 4) : i]
            if any(t.artist_id == tracks[i].artist_id for t in window):
                penalties += 0.1

    return max(0.0, 1.0 - penalties / n)


def template_slot_fit(
    tracks: list[TrackData],
    slots: list[SetSlot],
) -> float:
    """Score how well tracks match template slots (0.0-1.0).

    For each position i, compares track[i] against slot[i]:
    - Mood match (50%): exact=1.0, adjacent intensity=0.5, else 0.0
    - Energy match (30%): 1.0 - |energy - slot_energy_mapped| / 1.0
    - BPM match (20%): 1.0 if in range, else penalty by distance

    Returns 0.5 (neutral) if no slots provided.
    """
    if not slots:
        return 0.5

    n = min(len(tracks), len(slots))
    if n == 0:
        return 0.5

    total = 0.0
    for i in range(n):
        track = tracks[i]
        slot = slots[i]

        # Mood match: compare intensity levels (1-6)
        track_intensity = track.mood
        slot_intensity = slot.mood.intensity
        if track_intensity == slot_intensity:
            mood_score = 1.0
        elif abs(track_intensity - slot_intensity) == 1:
            mood_score = 0.5
        else:
            mood_score = 0.0

        # Energy match: slot.energy_target is LUFS (-14..-6), track.energy is 0-1
        slot_energy = max(0.0, min(1.0, (slot.energy_target + 14.0) / 8.0))
        energy_score = max(0.0, 1.0 - abs(track.energy - slot_energy))

        # BPM match: in-range = 1.0, else linear penalty up to 10 BPM away
        bpm_low, bpm_high = slot.bpm_range
        if bpm_low <= track.bpm <= bpm_high:
            bpm_score = 1.0
        else:
            bpm_dist = min(abs(track.bpm - bpm_low), abs(track.bpm - bpm_high))
            bpm_score = max(0.0, 1.0 - bpm_dist / 10.0)

        total += 0.5 * mood_score + 0.3 * energy_score + 0.2 * bpm_score

    return total / n


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
                    child = self._order_crossover(p1, p2)
                else:
                    child = p1.copy()

                if self._rng.random() < cfg.mutation_rate:
                    self._mutate(child)

                # Track replacement mutation (5% chance)
                self._mutate_replace(child)

                # Local search: lightweight for large sets, full 2-opt for small
                if large:
                    self._relocate_worst(child)
                else:
                    self._two_opt(child)

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
            self._two_opt(best_chromosome, max_passes=5)
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
                    self._relocate_worst(path)
            else:
                self._two_opt(path)
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

    # ── Crossover ───────────────────────────────────────────

    def _order_crossover(self, p1: NDArray[np.int32], p2: NDArray[np.int32]) -> NDArray[np.int32]:
        """Order Crossover (OX): preserves relative order from both parents.

        Suitable for permutation-based chromosomes (no duplicate tracks).

        When ``track_count < n_all`` (subset GA), OX can silently drop pinned
        tracks that appear late in p2's ordering because ``p2_filtered`` has
        more elements than the remaining slots.  A repair step re-inserts any
        missing pinned indices by replacing random non-pinned positions.
        """
        n = len(p1)
        start, end = sorted(self._rng.sample(range(n), 2))

        child = np.full(n, -1, dtype=np.int32)
        # Copy segment from p1
        child[start : end + 1] = p1[start : end + 1]

        # Fill remaining from p2 in order, skipping genes already in child
        in_child = set(child[start : end + 1].tolist())
        p2_filtered = [g for g in p2 if g not in in_child]

        pos = 0
        for i in range(n):
            if child[i] == -1:
                child[i] = p2_filtered[pos]
                pos += 1

        # Repair: re-insert pinned indices that were dropped (subset GA case).
        # Both parents always contain all pinned indices; the child may lose some
        # when parents have different filler sets and p2_filtered is longer than
        # the remaining slots (OX fills only the first n-segment elements).
        if self._pinned_indices:
            child_set = set(child.tolist())
            missing = [p for p in self._pinned_indices if p not in child_set]
            if missing:
                replaceable = [pos for pos in range(n) if child[pos] not in self._pinned_indices]
                self._rng.shuffle(replaceable)
                for i, pinned_idx in enumerate(missing):
                    if i < len(replaceable):
                        child[replaceable[i]] = pinned_idx

        return child

    # ── Mutation ────────────────────────────────────────────

    def _mutate(self, chromosome: NDArray[np.int32]) -> None:
        """Apply swap + insert mutation (in-place).

        When pinned tracks are present, only **swap** mutation is applied.
        Insert (relocate) mutation is skipped because it shifts all intermediate
        elements between src and dst — this indirectly moves pinned tracks even
        when neither src nor dst is a pinned position.

        Without pinned constraints both swap and insert are applied as before.
        """
        n = len(chromosome)
        if n < 2:
            return

        # Free positions: not occupied by a pinned track
        free = [p for p in range(n) if chromosome[p] not in self._pinned_indices]

        # Swap mutation: exchange two free positions (always safe for pinned tracks)
        if len(free) >= 2:
            i, j = self._rng.sample(free, 2)
            chromosome[i], chromosome[j] = chromosome[j], chromosome[i]

        # Insert mutation: only when no pinned constraints.
        # With pinned tracks, insert shifts intermediate positions and would
        # move pinned tracks — swap-only is used instead.
        if not self._pinned_indices and self._rng.random() < 0.5 and n > 2:
            src = self._rng.randrange(n)
            dst = self._rng.randrange(n)
            if src != dst:
                gene = chromosome[src]
                chromosome_list = chromosome.tolist()
                chromosome_list.pop(src)
                chromosome_list.insert(dst, gene)
                chromosome[:] = chromosome_list

    def _mutate_replace(self, chromosome: NDArray[np.int32]) -> None:
        """Replace one track with an unused track from the pool (in-place).

        Only effective when track_count < len(all_tracks).
        5% probability per call.

        Constraints: never replace pinned tracks, never insert excluded tracks.

        Args:
            chromosome: Permutation to modify (in-place).
        """
        n_all = len(self._all_tracks)
        n_select = len(chromosome)

        if n_select >= n_all:
            return  # No unused tracks available

        if self._rng.random() > 0.05:
            return  # 5% probability gate

        # Find unused tracks (excluding banned tracks)
        used = set(chromosome.tolist())
        unused = [i for i in range(n_all) if i not in used and i not in self._excluded_indices]
        if not unused:
            return

        # Replaceable positions: not pinned
        replaceable = [p for p in range(n_select) if chromosome[p] not in self._pinned_indices]
        if not replaceable:
            return

        pos = self._rng.choice(replaceable)
        replacement = self._rng.choice(unused)
        chromosome[pos] = replacement

    def _relocate_worst(self, chromosome: NDArray[np.int32]) -> None:
        """Find worst transition edge, relocate that track to best position.

        O(n) per call — finds the lowest-scoring transition, removes the second
        track, and reinserts it at the position that maximises local transition
        quality.  Much faster than ``_two_opt()`` for large sets.

        Args:
            chromosome: Permutation to optimise (modified in-place).
        """
        n = len(chromosome)
        if n < 3:
            return

        # Find worst transition (lowest matrix score between consecutive tracks)
        worst_score = self._matrix[chromosome[0], chromosome[1]]
        worst_pos = 1
        for k in range(1, n - 1):
            score = self._matrix[chromosome[k], chromosome[k + 1]]
            if score < worst_score:
                worst_score = score
                worst_pos = k + 1

        # Remove track at worst_pos
        track_idx = int(chromosome[worst_pos])
        remaining = np.delete(chromosome, worst_pos)
        m = len(remaining)

        # Try all insertion positions, pick the one maximising transition gain
        best_gain = -np.inf
        best_pos = 0

        for pos in range(m + 1):
            gain = 0.0
            # Gained edges from inserting track_idx at pos
            if pos > 0:
                gain += self._matrix[remaining[pos - 1], track_idx]
            if pos < m:
                gain += self._matrix[track_idx, remaining[pos]]
            # Lost edge that gets split by insertion
            if 0 < pos < m:
                gain -= self._matrix[remaining[pos - 1], remaining[pos]]

            if gain > best_gain:
                best_gain = gain
                best_pos = pos

        # Reconstruct in-place
        new_ch = np.empty(n, dtype=np.int32)
        new_ch[:best_pos] = remaining[:best_pos]
        new_ch[best_pos] = track_idx
        new_ch[best_pos + 1 :] = remaining[best_pos:]
        chromosome[:] = new_ch

    def _two_opt(self, chromosome: NDArray[np.int32], max_passes: int | None = None) -> None:
        """Apply 2-opt local search using full composite fitness (in-place).

        Unlike simple 2-opt that only considers transition matrix edges,
        this version evaluates the complete fitness function (transition +
        energy arc + BPM smoothness) for segment reversal decisions.

        Slower per iteration (~50ms for 40 tracks) but significantly better
        energy arc adherence.

        Args:
            chromosome: Permutation to optimize (modified in-place).
            max_passes: Maximum number of full O(n²) passes. ``None`` uses
                the legacy default of ``n * 2``. Use 0 for a no-op.
        """
        n = len(chromosome)
        if n < 4:
            return

        limit = max_passes if max_passes is not None else n * 2
        if limit <= 0:
            return

        current_fitness = self._fitness(chromosome)
        improved = True

        iteration = 0
        while improved and iteration < limit:
            improved = False
            iteration += 1

            for i in range(n - 2):
                for j in range(i + 2, n):
                    # Try reversing segment [i+1:j+1]
                    chromosome[i + 1 : j + 1] = chromosome[i + 1 : j + 1][::-1]
                    new_fitness = self._fitness(chromosome)

                    if new_fitness > current_fitness:
                        # Keep the reversal
                        current_fitness = new_fitness
                        improved = True
                    else:
                        # Undo the reversal
                        chromosome[i + 1 : j + 1] = chromosome[i + 1 : j + 1][::-1]
