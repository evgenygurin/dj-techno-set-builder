from __future__ import annotations

from pathlib import Path

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import TrackFeatures  # noqa: E402
from app.utils.audio.pipeline import extract_all_features  # noqa: E402


class TestExtractAllFeatures:
    def test_returns_track_features(self, wav_file_path: Path) -> None:
        result = extract_all_features(wav_file_path)
        assert isinstance(result, TrackFeatures)

    def test_all_sub_results_present(self, wav_file_path: Path) -> None:
        result = extract_all_features(wav_file_path)
        assert result.bpm is not None
        assert result.key is not None
        assert result.loudness is not None
        assert result.band_energy is not None
        assert result.spectral is not None

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            extract_all_features(Path("/nonexistent/audio.wav"))

    def test_raises_on_silence(self, tmp_path: Path) -> None:
        import numpy as np
        import soundfile as sf

        silence_path = tmp_path / "silence.wav"
        sf.write(str(silence_path), np.zeros(44100, dtype="float32"), 44100)
        with pytest.raises(ValueError, match="silence"):
            extract_all_features(silence_path)
