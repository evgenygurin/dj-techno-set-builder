"""Crossover and mutation operators for the genetic algorithm.

All operators work in-place on numpy int32 chromosome arrays.
"""

from __future__ import annotations

import random

import numpy as np
from numpy.typing import NDArray


def order_crossover(
    p1: NDArray[np.int32],
    p2: NDArray[np.int32],
    rng: random.Random,
    pinned_indices: frozenset[int],
) -> NDArray[np.int32]:
    """Order Crossover (OX): preserves relative order from both parents.

    Suitable for permutation-based chromosomes (no duplicate tracks).

    When ``track_count < n_all`` (subset GA), OX can silently drop pinned
    tracks that appear late in p2's ordering because ``p2_filtered`` has
    more elements than the remaining slots.  A repair step re-inserts any
    missing pinned indices by replacing random non-pinned positions.
    """
    n = len(p1)
    start, end = sorted(rng.sample(range(n), 2))

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
    if pinned_indices:
        child_set = set(child.tolist())
        missing = [p for p in pinned_indices if p not in child_set]
        if missing:
            replaceable = [pos for pos in range(n) if child[pos] not in pinned_indices]
            rng.shuffle(replaceable)
            for i, pinned_idx in enumerate(missing):
                if i < len(replaceable):
                    child[replaceable[i]] = pinned_idx

    return child


def mutate(
    chromosome: NDArray[np.int32],
    rng: random.Random,
    pinned_indices: frozenset[int],
) -> None:
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
    free = [p for p in range(n) if chromosome[p] not in pinned_indices]

    # Swap mutation: exchange two free positions (always safe for pinned tracks)
    if len(free) >= 2:
        i, j = rng.sample(free, 2)
        chromosome[i], chromosome[j] = chromosome[j], chromosome[i]

    # Insert mutation: only when no pinned constraints.
    # With pinned tracks, insert shifts intermediate positions and would
    # move pinned tracks — swap-only is used instead.
    if not pinned_indices and rng.random() < 0.5 and n > 2:
        src = rng.randrange(n)
        dst = rng.randrange(n)
        if src != dst:
            gene = chromosome[src]
            chromosome_list = chromosome.tolist()
            chromosome_list.pop(src)
            chromosome_list.insert(dst, gene)
            chromosome[:] = chromosome_list


def mutate_replace(
    chromosome: NDArray[np.int32],
    rng: random.Random,
    all_tracks_len: int,
    pinned_indices: frozenset[int],
    excluded_indices: frozenset[int],
) -> None:
    """Replace one track with an unused track from the pool (in-place).

    Only effective when track_count < len(all_tracks).
    5% probability per call.

    Constraints: never replace pinned tracks, never insert excluded tracks.

    Args:
        chromosome: Permutation to modify (in-place).
        rng: Random number generator.
        all_tracks_len: Total number of available tracks.
        pinned_indices: Indices of pinned tracks (must stay).
        excluded_indices: Indices of excluded tracks (must not appear).
    """
    n_all = all_tracks_len
    n_select = len(chromosome)

    if n_select >= n_all:
        return  # No unused tracks available

    if rng.random() > 0.05:
        return  # 5% probability gate

    # Find unused tracks (excluding banned tracks)
    used = set(chromosome.tolist())
    unused = [i for i in range(n_all) if i not in used and i not in excluded_indices]
    if not unused:
        return

    # Replaceable positions: not pinned
    replaceable = [p for p in range(n_select) if chromosome[p] not in pinned_indices]
    if not replaceable:
        return

    pos = rng.choice(replaceable)
    replacement = rng.choice(unused)
    chromosome[pos] = replacement
