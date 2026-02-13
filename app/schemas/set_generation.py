from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class SetGenerationRequest(BaseSchema):
    population_size: int = Field(default=100, ge=10, le=1000)
    generations: int = Field(default=200, ge=10, le=5000)
    mutation_rate: float = Field(default=0.15, ge=0.0, le=1.0)
    crossover_rate: float = Field(default=0.8, ge=0.0, le=1.0)
    tournament_size: int = Field(default=5, ge=2, le=50)
    elitism_count: int = Field(default=2, ge=0, le=50)
    track_count: int | None = Field(default=None, ge=2, description="Subset size (None = all)")
    energy_arc_type: str = Field(
        default="classic",
        description="Energy arc shape: classic, progressive, roller, wave",
    )
    seed: int | None = Field(default=None, description="RNG seed for reproducibility")
    version_label: str | None = Field(default=None, max_length=100)
    w_transition: float = Field(default=0.50, ge=0.0, le=1.0)
    w_energy_arc: float = Field(default=0.30, ge=0.0, le=1.0)
    w_bpm_smooth: float = Field(default=0.20, ge=0.0, le=1.0)


class SetGenerationResponse(BaseSchema):
    set_version_id: int
    score: float
    track_ids: list[int]
    transition_scores: list[float]
    fitness_history: list[float]
    energy_arc_score: float
    bpm_smoothness_score: float
    generator_run: dict[str, Any]
