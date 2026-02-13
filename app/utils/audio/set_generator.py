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
    w_transition: float = 0.50
    w_energy_arc: float = 0.30
    w_bpm_smooth: float = 0.20


@dataclass(frozen=True, slots=True)
class TrackData:
    """Lightweight track representation for the GA."""

    track_id: int
    bpm: float
    energy: float  # 0-1, global energy proxy
    key_code: int


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


def target_energy_curve(n: int, arc_type: EnergyArcType) -> NDArray[np.float64]:
    """Generate a target energy array of length *n* for the given arc type.

    Returns values in [0, 1].
    """
    if n <= 1:
        return np.array([0.5], dtype=np.float64)

    t = np.linspace(0.0, 1.0, n, dtype=np.float64)

    if arc_type == EnergyArcType.CLASSIC:
        # Two-peak wave: intro(0.3) → build → peak(1.0) → breakdown(0.4) → peak2(0.9) → outro(0.3)
        curve = (
            0.3
            + 0.7 * np.sin(np.pi * t) ** 1.5  # main arc
            - 0.15 * np.exp(-((t - 0.55) ** 2) / 0.01)  # breakdown dip at ~55%
        )
    elif arc_type == EnergyArcType.PROGRESSIVE:
        # Slow rise to single peak at ~80%, then sharp drop
        curve = 0.2 + 0.8 * np.sin(np.pi * t * 0.55) ** 2
    elif arc_type == EnergyArcType.ROLLER:
        # High sustained energy with gentle variation
        curve = 0.6 + 0.3 * np.sin(2 * np.pi * t) ** 2
    elif arc_type == EnergyArcType.WAVE:
        # Three peaks of increasing then decreasing intensity
        curve = 0.3 + 0.6 * np.abs(np.sin(2.5 * np.pi * t)) * np.sin(np.pi * t) ** 0.5
    else:  # pragma: no cover — StrEnum guarantees exhaustive
        curve = np.full(n, 0.5, dtype=np.float64)

    return np.clip(curve, 0.0, 1.0)


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
    ) -> None:
        self.config = config or GAConfig()
        self._rng = random.Random(self.config.seed)
        self._np_rng = np.random.default_rng(self.config.seed)

        # Determine working set
        n = len(tracks)
        use_n = min(self.config.track_count, n) if self.config.track_count else n

        self._all_tracks = tracks
        self._n = use_n
        self._matrix = transition_matrix.astype(np.float64)
        self._energies = np.array([t.energy for t in tracks], dtype=np.float64)
        self._bpms = np.array([t.bpm for t in tracks], dtype=np.float64)
        self._target = target_energy_curve(use_n, self.config.energy_arc_type)

    def run(self) -> GAResult:
        """Execute the genetic algorithm. Returns the best solution found."""
        n_all = len(self._all_tracks)
        cfg = self.config

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

                new_pop.append(child)

            population = new_pop[: cfg.population_size]
            fitnesses = np.array([self._fitness(ch) for ch in population])

            gen_best_idx = int(np.argmax(fitnesses))
            if fitnesses[gen_best_idx] > best_fitness:
                best_fitness = fitnesses[gen_best_idx]
                best_chromosome = population[gen_best_idx].copy()

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

    def _init_population(
        self, n_all: int, n_select: int, pop_size: int
    ) -> list[NDArray[np.int32]]:
        """Create initial population of random permutations."""
        population: list[NDArray[np.int32]] = []
        indices = np.arange(n_all, dtype=np.int32)
        for _ in range(pop_size):
            perm = self._np_rng.permutation(indices)
            population.append(perm[:n_select].copy())
        return population

    # ── Fitness ─────────────────────────────────────────────

    def _fitness(self, chromosome: NDArray[np.int32]) -> float:
        """Evaluate fitness of a chromosome (higher = better)."""
        cfg = self.config
        transition = self._mean_transition_quality(chromosome)
        arc = self._energy_arc_score(chromosome)
        bpm = self._bpm_smoothness_score(chromosome)
        return cfg.w_transition * transition + cfg.w_energy_arc * arc + cfg.w_bpm_smooth * bpm

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

        return child

    # ── Mutation ────────────────────────────────────────────

    def _mutate(self, chromosome: NDArray[np.int32]) -> None:
        """Apply swap + insert mutation (in-place)."""
        n = len(chromosome)
        if n < 2:
            return

        # Swap mutation: exchange two random positions
        i, j = self._rng.sample(range(n), 2)
        chromosome[i], chromosome[j] = chromosome[j], chromosome[i]

        # Insert mutation: move a random element to a random position
        if self._rng.random() < 0.5 and n > 2:
            src = self._rng.randrange(n)
            dst = self._rng.randrange(n)
            if src != dst:
                gene = chromosome[src]
                chromosome_list = chromosome.tolist()
                chromosome_list.pop(src)
                chromosome_list.insert(dst, gene)
                chromosome[:] = chromosome_list
