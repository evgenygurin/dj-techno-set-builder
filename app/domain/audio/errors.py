"""Domain errors for the audio analysis layer."""

from __future__ import annotations


class AudioError(Exception):
    """Base error for audio utilities."""


class AudioValidationError(AudioError):
    """Audio signal failed validation (silence, too short, corrupt)."""


class AudioAnalysisError(AudioError):
    """An audio analysis stage failed unexpectedly.

    Attributes:
        stage: Which analysis step failed (e.g. 'bpm', 'key', 'loudness').
        path: Path to the audio file being analyzed.
    """

    def __init__(self, stage: str, path: str, cause: Exception) -> None:
        self.stage = stage
        self.path = path
        self.cause = cause
        super().__init__(f"Audio analysis failed at '{stage}' for {path}: {cause}")
