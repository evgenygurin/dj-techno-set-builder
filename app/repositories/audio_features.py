from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.models.features import TrackAudioFeaturesComputed
from app.repositories.base import BaseRepository
from app.utils.audio._types import TrackFeatures


class AudioFeaturesRepository(BaseRepository[TrackAudioFeaturesComputed]):
    model = TrackAudioFeaturesComputed

    async def get_by_track(
        self,
        track_id: int,
        run_id: int | None = None,
    ) -> TrackAudioFeaturesComputed | None:
        """Get features for a track, optionally filtered by run."""
        stmt = select(self.model).where(self.model.track_id == track_id)
        if run_id is not None:
            stmt = stmt.where(self.model.run_id == run_id)
        stmt = stmt.order_by(self.model.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_track(
        self,
        track_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TrackAudioFeaturesComputed], int]:
        filters: list[Any] = [self.model.track_id == track_id]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def list_all(self) -> list[TrackAudioFeaturesComputed]:
        """Get latest features for every track (one row per track_id)."""
        from sqlalchemy import func as sa_func

        # Subquery: max(created_at) per track_id
        latest = (
            select(
                self.model.track_id,
                sa_func.max(self.model.created_at).label("max_created"),
            )
            .group_by(self.model.track_id)
            .subquery()
        )
        stmt = select(self.model).join(
            latest,
            (self.model.track_id == latest.c.track_id)
            & (self.model.created_at == latest.c.max_created),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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
            energy_std=features.band_energy.energy_std,
            # Band energies
            sub_energy=features.band_energy.sub,
            low_energy=features.band_energy.low,
            lowmid_energy=features.band_energy.low_mid,
            mid_energy=features.band_energy.mid,
            highmid_energy=features.band_energy.high_mid,
            high_energy=features.band_energy.high,
            low_high_ratio=features.band_energy.low_high_ratio,
            sub_lowmid_ratio=features.band_energy.sub_lowmid_ratio,
            # Energy slope
            energy_slope_mean=features.band_energy.energy_slope_mean,
            # Spectral
            centroid_mean_hz=features.spectral.centroid_mean_hz,
            rolloff_85_hz=features.spectral.rolloff_85_hz,
            rolloff_95_hz=features.spectral.rolloff_95_hz,
            flatness_mean=features.spectral.flatness_mean,
            flux_mean=features.spectral.flux_mean,
            flux_std=features.spectral.flux_std,
            slope_db_per_oct=features.spectral.slope_db_per_oct,
            contrast_mean_db=features.spectral.contrast_mean_db,
            hnr_mean_db=features.spectral.hnr_mean_db,
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
