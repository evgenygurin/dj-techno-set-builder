from app.audio._errors import AudioAnalysisError, AudioError, AudioValidationError
from app.audio._types import (
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
from app.audio.beats import detect_beats
from app.audio.camelot import camelot_distance, is_compatible, key_code_to_camelot
from app.audio.greedy_chain import GreedyChainResult, build_greedy_chain
from app.audio.groove import groove_similarity
from app.audio.loader import load_audio, validate_audio
from app.audio.pipeline import extract_all_features
from app.audio.set_generator import (
    EnergyArcType,
    GAConfig,
    GAResult,
    GeneticSetGenerator,
    TrackData,
    target_energy_curve,
)
from app.audio.structure import segment_structure
from app.audio.transition_score import score_transition

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
