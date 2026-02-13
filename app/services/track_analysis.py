from __future__ import annotations

import json
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

        # Utils layer — pure computation, no DB
        features = extract_all_features(audio_path)

        # Validate no NaN/Inf before persisting
        self._validate_features(features)

        # Persist via repository
        await self._persist_features(track_id, run_id, features)

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

        signal = load_audio(audio_path)
        validate_audio(signal)

        # Phase 1 features (always computed)
        from app.utils.audio.bpm import estimate_bpm
        from app.utils.audio.energy import compute_band_energies
        from app.utils.audio.key_detect import detect_key
        from app.utils.audio.loudness import measure_loudness
        from app.utils.audio.spectral import extract_spectral_features

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
            self.logger.warning(
                "Beat detection failed for track %d", track_id, exc_info=True
            )

        features = TrackFeatures(
            bpm=bpm_result,
            key=key_result,
            loudness=loudness_result,
            band_energy=band_energy_result,
            spectral=spectral_result,
            beats=beats_result,
        )

        self._validate_features(features)
        await self._persist_features(track_id, run_id, features)

        # Phase 2: persist structure sections
        if beats_result and self.sections_repo:
            try:
                from app.utils.audio.structure import segment_structure

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

    async def _persist_features(
        self,
        track_id: int,
        run_id: int,
        features: TrackFeatures,
    ) -> None:
        """Persist feature extraction results to DB."""
        beats = features.beats
        await self.features_repo.create(
            track_id=track_id,
            run_id=run_id,
            # Tempo
            bpm=features.bpm.bpm,
            tempo_confidence=features.bpm.confidence,
            bpm_stability=features.bpm.stability,
            is_variable_tempo=features.bpm.is_variable,
            # Loudness
            lufs_i=features.loudness.lufs_i,
            lufs_s_mean=features.loudness.lufs_s_mean,
            lufs_m_max=features.loudness.lufs_m_max,
            rms_dbfs=features.loudness.rms_dbfs,
            true_peak_db=features.loudness.true_peak_db,
            crest_factor_db=features.loudness.crest_factor_db,
            lra_lu=features.loudness.lra_lu,
            # Energy (global: use band_energy as proxy)
            energy_mean=features.band_energy.mid,
            energy_max=max(
                features.band_energy.sub,
                features.band_energy.low,
                features.band_energy.low_mid,
                features.band_energy.mid,
                features.band_energy.high_mid,
                features.band_energy.high,
            ),
            energy_std=0.0,  # TODO: compute from frame-level data
            # Band energies
            sub_energy=features.band_energy.sub,
            low_energy=features.band_energy.low,
            lowmid_energy=features.band_energy.low_mid,
            mid_energy=features.band_energy.mid,
            highmid_energy=features.band_energy.high_mid,
            high_energy=features.band_energy.high,
            low_high_ratio=features.band_energy.low_high_ratio,
            sub_lowmid_ratio=features.band_energy.sub_lowmid_ratio,
            # Spectral
            centroid_mean_hz=features.spectral.centroid_mean_hz,
            rolloff_85_hz=features.spectral.rolloff_85_hz,
            rolloff_95_hz=features.spectral.rolloff_95_hz,
            flatness_mean=features.spectral.flatness_mean,
            flux_mean=features.spectral.flux_mean,
            flux_std=features.spectral.flux_std,
            contrast_mean_db=features.spectral.contrast_mean_db,
            # Key
            key_code=features.key.key_code,
            key_confidence=features.key.confidence,
            is_atonal=features.key.is_atonal,
            chroma=json.dumps([float(v) for v in features.key.chroma]),
            # Phase 2: beats (optional)
            onset_rate_mean=beats.onset_rate_mean if beats else None,
            onset_rate_max=beats.onset_rate_max if beats else None,
            pulse_clarity=beats.pulse_clarity if beats else None,
            kick_prominence=beats.kick_prominence if beats else None,
            hp_ratio=beats.hp_ratio if beats else None,
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
