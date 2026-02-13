from __future__ import annotations

import asyncio
import math
from pathlib import Path

from app.errors import NotFoundError
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.services.base import BaseService
from app.utils.audio import TrackFeatures
from app.utils.audio._types import BeatsResult
from app.utils.audio.loader import load_audio, validate_audio
from app.utils.audio.pipeline import extract_all_features


class TrackAnalysisService(BaseService):
    """Orchestrates audio analysis: extract features via utils, persist via repos."""

    def __init__(
        self,
        track_repo: TrackRepository,
        features_repo: AudioFeaturesRepository,
        sections_repo: SectionsRepository | None = None,
    ) -> None:
        super().__init__()
        self.track_repo = track_repo
        self.features_repo = features_repo
        self.sections_repo = sections_repo

    async def analyze_track(
        self,
        track_id: int,
        audio_path: str | Path,
        run_id: int,
    ) -> TrackFeatures:
        """Extract all audio features and persist to DB.

        Returns the extracted TrackFeatures for immediate use.
        """
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)

        self.logger.info("Analyzing track %d from %s", track_id, audio_path)

        # CPU-bound — run off the event loop
        features = await asyncio.to_thread(extract_all_features, audio_path)

        # Validate no NaN/Inf before persisting
        self._validate_features(features)

        # Persist via repository (mapping lives in repo)
        await self.features_repo.save_features(track_id, run_id, features)

        self.logger.info("Features persisted for track %d, run %d", track_id, run_id)
        return features

    async def analyze_track_full(
        self,
        track_id: int,
        audio_path: str | Path,
        run_id: int,
    ) -> TrackFeatures:
        """Full analysis including beats and structure (Phase 2).

        Falls back to Phase 1 features if beat/structure extraction fails.
        """
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)

        self.logger.info("Full analysis for track %d from %s", track_id, audio_path)

        # CPU-bound — run off the event loop
        features = await asyncio.to_thread(self._extract_full_sync, audio_path, track_id)

        self._validate_features(features)
        await self.features_repo.save_features(track_id, run_id, features)

        # Phase 2: persist structure sections
        if features.beats and self.sections_repo:
            try:
                from app.utils.audio.structure import segment_structure

                signal = load_audio(audio_path)
                sections = segment_structure(signal)
                for section in sections:
                    await self.sections_repo.create(
                        track_id=track_id,
                        run_id=run_id,
                        start_ms=int(section.start_s * 1000),
                        end_ms=int(section.end_s * 1000),
                        section_type=section.section_type,
                        section_duration_ms=int(section.duration_s * 1000),
                        section_energy_mean=section.energy_mean,
                        section_energy_max=section.energy_max,
                        section_energy_slope=section.energy_slope,
                        boundary_confidence=section.boundary_confidence,
                    )
            except Exception:
                self.logger.warning(
                    "Structure segmentation failed for track %d",
                    track_id,
                    exc_info=True,
                )

        self.logger.info("Full analysis persisted for track %d, run %d", track_id, run_id)
        return features

    def _extract_full_sync(self, audio_path: str | Path, track_id: int) -> TrackFeatures:
        """Synchronous CPU-bound extraction of all features (Phase 1 + 2)."""
        from app.utils.audio.bpm import estimate_bpm
        from app.utils.audio.energy import compute_band_energies
        from app.utils.audio.key_detect import detect_key
        from app.utils.audio.loudness import measure_loudness
        from app.utils.audio.spectral import extract_spectral_features

        signal = load_audio(audio_path)
        validate_audio(signal)

        bpm_result = estimate_bpm(signal)
        key_result = detect_key(signal)
        loudness_result = measure_loudness(signal)
        band_energy_result = compute_band_energies(signal)
        spectral_result = extract_spectral_features(signal)

        # Phase 2: beat detection (optional, graceful failure)
        beats_result: BeatsResult | None = None
        try:
            from app.utils.audio.beats import detect_beats

            beats_result = detect_beats(signal)
        except Exception:
            self.logger.warning("Beat detection failed for track %d", track_id, exc_info=True)

        return TrackFeatures(
            bpm=bpm_result,
            key=key_result,
            loudness=loudness_result,
            band_energy=band_energy_result,
            spectral=spectral_result,
            beats=beats_result,
        )

    @staticmethod
    def _validate_features(features: TrackFeatures) -> None:
        """Check that no NaN/Inf values leak into DB columns."""
        checks = [
            ("bpm", features.bpm.bpm),
            ("confidence", features.bpm.confidence),
            ("lufs_i", features.loudness.lufs_i),
            ("rms_dbfs", features.loudness.rms_dbfs),
            ("centroid_mean_hz", features.spectral.centroid_mean_hz),
        ]
        for name, val in checks:
            if math.isnan(val) or math.isinf(val):
                msg = f"Feature '{name}' is NaN or Inf — cannot persist"
                raise ValueError(msg)
