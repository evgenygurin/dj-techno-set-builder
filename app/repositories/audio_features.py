from __future__ import annotations

import json

from app.models.features import TrackAudioFeaturesComputed
from app.repositories.base import BaseRepository
from app.utils.audio._types import TrackFeatures


class AudioFeaturesRepository(BaseRepository[TrackAudioFeaturesComputed]):
    model = TrackAudioFeaturesComputed

    async def save_features(
        self,
        track_id: int,
        run_id: int,
        features: TrackFeatures,
    ) -> TrackAudioFeaturesComputed:
        """Map TrackFeatures → ORM fields and persist."""
        beats = features.beats
        return await self.create(
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
            # Energy
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
