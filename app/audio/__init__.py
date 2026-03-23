"""Compatibility shim — re-exports from app.domain.audio."""

from app.domain.audio.camelot import camelot_distance, is_compatible, key_code_to_camelot
from app.domain.audio.dsp.beats import detect_beats
from app.domain.audio.dsp.groove import groove_similarity
from app.domain.audio.dsp.loader import load_audio, validate_audio
from app.domain.audio.dsp.pipeline import extract_all_features
from app.domain.audio.dsp.structure import segment_structure
from app.domain.audio.errors import AudioAnalysisError, AudioError, AudioValidationError
from app.domain.audio.scoring.transition_score import score_transition
from app.domain.audio.types import (
    AudioSignal,
    BandEnergyResult,
    BeatsResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    MfccResult,
    SectionResult,
    SpectralResult,
    StemsResult,
    TrackFeatures,
    TransitionScore,
)
from app.domain.setbuilder.genetic.engine import (
    EnergyArcType,
    GAConfig,
    GAResult,
    GeneticSetGenerator,
    TrackData,
    target_energy_curve,
)
from app.domain.setbuilder.greedy import GreedyChainResult, build_greedy_chain

__all__ = [
    "AudioAnalysisError",
    "AudioError",
    "AudioSignal",
    "AudioValidationError",
    "BandEnergyResult",
    "BeatsResult",
    "BpmResult",
    "EnergyArcType",
    "GAConfig",
    "GAResult",
    "GeneticSetGenerator",
    "GreedyChainResult",
    "KeyResult",
    "LoudnessResult",
    "MfccResult",
    "SectionResult",
    "SpectralResult",
    "StemsResult",
    "TrackData",
    "TrackFeatures",
    "TransitionScore",
    "build_greedy_chain",
    "camelot_distance",
    "detect_beats",
    "extract_all_features",
    "groove_similarity",
    "is_compatible",
    "key_code_to_camelot",
    "load_audio",
    "score_transition",
    "segment_structure",
    "target_energy_curve",
    "validate_audio",
]
