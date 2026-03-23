"""Genetic algorithm package for DJ set track ordering.

Re-exports all public API from submodules so existing imports from
``app.domain.setbuilder.genetic.engine`` continue to work.
"""

from app.domain.setbuilder.genetic.engine import (
    EnergyArcType,
    GAConfig,
    GAConstraints,
    GAResult,
    GeneticSetGenerator,
    TrackData,
)
from app.domain.setbuilder.genetic.fitness import (
    lufs_to_energy,
    target_energy_curve,
    template_slot_fit,
    variety_score,
)
from app.domain.setbuilder.genetic.local_search import relocate_worst, two_opt
from app.domain.setbuilder.genetic.operators import mutate, mutate_replace, order_crossover

__all__ = [
    "EnergyArcType",
    "GAConfig",
    "GAConstraints",
    "GAResult",
    "GeneticSetGenerator",
    "TrackData",
    "lufs_to_energy",
    "mutate",
    "mutate_replace",
    "order_crossover",
    "relocate_worst",
    "target_energy_curve",
    "template_slot_fit",
    "two_opt",
    "variety_score",
]
