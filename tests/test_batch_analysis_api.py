from unittest.mock import patch

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.audio import (  # noqa: E402
    BandEnergyResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SpectralResult,
    TrackFeatures,
)


def _fake_features() -> TrackFeatures:
    return TrackFeatures(
        bpm=BpmResult(bpm=140.0, confidence=0.9, stability=0.95, is_variable=False),
        key=KeyResult(
            key="A",
            scale="minor",
            key_code=18,
            confidence=0.85,
            is_atonal=False,
            chroma=np.zeros(12, dtype=np.float32),
            chroma_entropy=0.5,
        ),
        loudness=LoudnessResult(
            lufs_i=-8.0,
            lufs_s_mean=-7.5,
            lufs_m_max=-5.0,
            rms_dbfs=-10.0,
            true_peak_db=-1.0,
            crest_factor_db=9.0,
            lra_lu=6.0,
        ),
        band_energy=BandEnergyResult(
            sub=0.3,
            low=0.7,
            low_mid=0.5,
            mid=0.4,
            high_mid=0.2,
            high=0.1,
            low_high_ratio=7.0,
            sub_lowmid_ratio=0.6,
            energy_slope_mean=-0.001,
        ),
        spectral=SpectralResult(
            centroid_mean_hz=1500.0,
            rolloff_85_hz=5000.0,
            rolloff_95_hz=8000.0,
            flatness_mean=0.3,
            flux_mean=0.5,
            flux_std=0.1,
            contrast_mean_db=20.0,
            slope_db_per_oct=-4.2,
            hnr_mean_db=12.5,
        ),
    )


async def test_batch_analyze_rejects_empty(client):
    resp = await client.post(
        "/api/v1/tracks/batch-analyze",
        json={"track_ids": [], "audio_dir": "/tmp"},
    )
    assert resp.status_code == 422


async def test_batch_analyze_endpoint_exists(client):
    resp = await client.post(
        "/api/v1/tracks/batch-analyze",
        json={"track_ids": [999], "audio_dir": "/nonexistent"},
    )
    # Route exists (not 404), may be 404 for track or other error
    assert resp.status_code != 404


@patch("app.services.track_analysis.extract_all_features")
async def test_batch_analyze_counts_skipped(mock_extract, client, tmp_path):
    """Tracks with no audio file should be counted as skipped, not completed."""
    mock_extract.return_value = _fake_features()

    # Create tracks
    ids = []
    for i in range(3):
        r = await client.post(
            "/api/v1/tracks",
            json={"title": f"Batch Track {i}", "duration_ms": 300000},
        )
        ids.append(r.json()["track_id"])

    resp = await client.post(
        "/api/v1/tracks/batch-analyze",
        json={"track_ids": ids, "audio_dir": str(tmp_path)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["skipped"] == 3
    assert body["completed"] == 0
    assert body["failed"] == 0


@patch("app.services.track_analysis.extract_all_features")
async def test_batch_failed_analysis_not_counted_as_completed(mock_extract, client, tmp_path):
    """When extraction raises, status=failed — must count as failed, not completed."""
    mock_extract.side_effect = RuntimeError("essentia crash")

    r = await client.post(
        "/api/v1/tracks",
        json={"title": "Failing Track", "duration_ms": 300000},
    )
    tid = r.json()["track_id"]

    # Create a dummy audio file so it's not skipped
    audio = tmp_path / f"{tid:03d}_failing.mp3"
    audio.write_bytes(b"fake")

    resp = await client.post(
        "/api/v1/tracks/batch-analyze",
        json={"track_ids": [tid], "audio_dir": str(tmp_path)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["completed"] == 0
    assert body["failed"] == 1
