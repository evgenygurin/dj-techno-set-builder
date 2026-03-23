"""Local search operators for the genetic algorithm.

Two-opt and relocate-worst strategies for post-crossover improvement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from collections.abc import Callable


def relocate_worst(
    chromosome: NDArray[np.int32],
    matrix: NDArray[np.float64],
) -> None:
    """Find worst transition edge, relocate that track to best position.

    O(n) per call — finds the lowest-scoring transition, removes the second
    track, and reinserts it at the position that maximises local transition
    quality.  Much faster than ``two_opt()`` for large sets.

    Args:
        chromosome: Permutation to optimise (modified in-place).
        matrix: Pre-computed NxN transition quality matrix.
    """
    n = len(chromosome)
    if n < 3:
        return

    # Find worst transition (lowest matrix score between consecutive tracks)
    worst_score = matrix[chromosome[0], chromosome[1]]
    worst_pos = 1
    for k in range(1, n - 1):
        score = matrix[chromosome[k], chromosome[k + 1]]
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
            gain += matrix[remaining[pos - 1], track_idx]
        if pos < m:
            gain += matrix[track_idx, remaining[pos]]
        # Lost edge that gets split by insertion
        if 0 < pos < m:
            gain -= matrix[remaining[pos - 1], remaining[pos]]

        if gain > best_gain:
            best_gain = gain
            best_pos = pos

    # Reconstruct in-place
    new_ch = np.empty(n, dtype=np.int32)
    new_ch[:best_pos] = remaining[:best_pos]
    new_ch[best_pos] = track_idx
    new_ch[best_pos + 1 :] = remaining[best_pos:]
    chromosome[:] = new_ch


def two_opt(
    chromosome: NDArray[np.int32],
    fitness_fn: Callable[[NDArray[np.int32]], float],
    max_passes: int | None = None,
) -> None:
    """Apply 2-opt local search using full composite fitness (in-place).

    Unlike simple 2-opt that only considers transition matrix edges,
    this version evaluates the complete fitness function (transition +
    energy arc + BPM smoothness) for segment reversal decisions.

    Slower per iteration (~50ms for 40 tracks) but significantly better
    energy arc adherence.

    Args:
        chromosome: Permutation to optimize (modified in-place).
        fitness_fn: Full fitness evaluation function.
        max_passes: Maximum number of full O(n^2) passes. ``None`` uses
            the legacy default of ``n * 2``. Use 0 for a no-op.
    """
    n = len(chromosome)
    if n < 4:
        return

    limit = max_passes if max_passes is not None else n * 2
    if limit <= 0:
        return

    current_fitness = fitness_fn(chromosome)
    improved = True

    iteration = 0
    while improved and iteration < limit:
        improved = False
        iteration += 1

        for i in range(n - 2):
            for j in range(i + 2, n):
                # Try reversing segment [i+1:j+1]
                chromosome[i + 1 : j + 1] = chromosome[i + 1 : j + 1][::-1]
                new_fitness = fitness_fn(chromosome)

                if new_fitness > current_fitness:
                    # Keep the reversal
                    current_fitness = new_fitness
                    improved = True
                else:
                    # Undo the reversal
                    chromosome[i + 1 : j + 1] = chromosome[i + 1 : j + 1][::-1]
