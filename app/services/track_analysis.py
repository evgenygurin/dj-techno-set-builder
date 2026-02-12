from __future__ import annotations

from pathlib import Path

from app.errors import NotFoundError
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.services.base import BaseService
from app.utils.audio import TrackFeatures
from app.utils.audio.pipeline import extract_all_features


class TrackAnalysisService(BaseService):
    """Orchestrates audio analysis: extract features via utils, persist via repos."""

    def __init__(
        self,
        track_repo: TrackRepository,
        features_repo: AudioFeaturesRepository,
    ) -> None:
        super().__init__()
        self.track_repo = track_repo
        self.features_repo = features_repo

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

        # Persist via repository
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
            chroma=",".join(f"{v:.6f}" for v in features.key.chroma),
        )

        self.logger.info("Features persisted for track %d, run %d", track_id, run_id)
        return features
