from app.utils.audio._errors import AudioAnalysisError, AudioError, AudioValidationError
from app.utils.audio._types import (
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
from app.utils.audio.beats import detect_beats
from app.utils.audio.camelot import camelot_distance, is_compatible, key_code_to_camelot
from app.utils.audio.greedy_chain import GreedyChainResult, build_greedy_chain
from app.utils.audio.groove import groove_similarity
from app.utils.audio.loader import load_audio, validate_audio
from app.utils.audio.pipeline import extract_all_features
from app.utils.audio.set_generator import (
    EnergyArcType,
    GAConfig,
    GAResult,
    GeneticSetGenerator,
    TrackData,
    target_energy_curve,
)
from app.utils.audio.structure import segment_structure

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
    "segment_structure",
    "target_energy_curve",
    "validate_audio",
]
