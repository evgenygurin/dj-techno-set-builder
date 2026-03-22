from __future__ import annotations

from pathlib import Path

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioAnalysisError, AudioValidationError, TrackFeatures  # noqa: E402
from app.utils.audio.pipeline import _run_stage, extract_all_features  # noqa: E402


@pytest.fixture(scope="module")
def pipeline_result(wav_file_path: Path) -> TrackFeatures:
    """Run full pipeline once for all tests in this module."""
    return extract_all_features(wav_file_path)


class TestExtractAllFeatures:
    def test_returns_track_features(self, pipeline_result: TrackFeatures) -> None:
        assert isinstance(pipeline_result, TrackFeatures)

    def test_all_sub_results_present(self, pipeline_result: TrackFeatures) -> None:
        assert pipeline_result.bpm is not None
        assert pipeline_result.key is not None
        assert pipeline_result.loudness is not None
        assert pipeline_result.band_energy is not None
        assert pipeline_result.spectral is not None

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            extract_all_features(Path("/nonexistent/audio.wav"))

    def test_raises_on_silence(self, tmp_path: Path) -> None:
        import numpy as np
        import soundfile as sf

        silence_path = tmp_path / "silence.wav"
        sf.write(str(silence_path), np.zeros(44100, dtype="float32"), 44100)
        with pytest.raises(AudioValidationError, match="silence"):
            extract_all_features(silence_path)


class TestRunStage:
    def test_wraps_unexpected_error(self) -> None:
        """Unexpected exceptions are wrapped in AudioAnalysisError."""
        from app.utils.audio import AudioSignal

        dummy = AudioSignal(
            samples=__import__("numpy").zeros(100, dtype="float32"),
            sample_rate=44100,
            duration_s=0.01,
        )

        def _failing(_sig: AudioSignal) -> None:
            msg = "boom"
            raise RuntimeError(msg)

        with pytest.raises(AudioAnalysisError, match="boom") as exc_info:
            _run_stage("test_stage", "/fake.wav", _failing, dummy)

        assert exc_info.value.stage == "test_stage"
        assert isinstance(exc_info.value.cause, RuntimeError)

    def test_passthrough_file_not_found(self) -> None:
        """FileNotFoundError should not be wrapped."""
        from app.utils.audio import AudioSignal

        dummy = AudioSignal(
            samples=__import__("numpy").zeros(100, dtype="float32"),
            sample_rate=44100,
            duration_s=0.01,
        )

        def _raise_fnf(_sig: AudioSignal) -> None:
            raise FileNotFoundError("gone")

        with pytest.raises(FileNotFoundError, match="gone"):
            _run_stage("test_stage", "/fake.wav", _raise_fnf, dummy)
