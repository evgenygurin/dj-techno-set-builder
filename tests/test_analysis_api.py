from unittest.mock import patch

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import (  # noqa: E402
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


@patch("app.services.track_analysis.extract_all_features")
async def test_analyze_track_endpoint(mock_extract, client):
    mock_extract.return_value = _fake_features()

    # Create a track first
    track_resp = await client.post(
        "/api/v1/tracks",
        json={"title": "Test Track", "duration_ms": 360000},
    )
    track_id = track_resp.json()["track_id"]

    # Trigger analysis
    resp = await client.post(
        f"/api/v1/tracks/{track_id}/analyze",
        json={"audio_path": "/fake/path.wav"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["track_id"] == track_id
    assert body["status"] == "completed"
    assert body["bpm"] == 140.0
    assert body["key_code"] == 18


@patch("app.services.track_analysis.extract_all_features")
async def test_analyze_persists_new_fields(mock_extract, client, session):
    """Verify newly added feature columns are persisted."""
    mock_extract.return_value = _fake_features()

    track_resp = await client.post(
        "/api/v1/tracks",
        json={"title": "Slope Test", "duration_ms": 300000},
    )
    track_id = track_resp.json()["track_id"]

    resp = await client.post(
        f"/api/v1/tracks/{track_id}/analyze",
        json={"audio_path": "/fake/path.wav"},
    )
    assert resp.status_code == 201

    from sqlalchemy import text

    row = (
        await session.execute(
            text(
                "SELECT energy_slope_mean, hnr_mean_db, slope_db_per_oct"
                " FROM track_audio_features_computed"
                " WHERE track_id = :tid"
            ),
            {"tid": track_id},
        )
    ).one()
    assert row.energy_slope_mean == pytest.approx(-0.001)
    assert row.hnr_mean_db == pytest.approx(12.5)
    assert row.slope_db_per_oct == pytest.approx(-4.2)


@patch("app.services.track_analysis.extract_all_features")
async def test_analyze_run_has_parameters(mock_extract, client, session):
    """Verify feature_extraction_runs gets parameters and code_ref."""
    mock_extract.return_value = _fake_features()

    track_resp = await client.post(
        "/api/v1/tracks",
        json={"title": "Params Test", "duration_ms": 300000},
    )
    track_id = track_resp.json()["track_id"]

    resp = await client.post(
        f"/api/v1/tracks/{track_id}/analyze",
        json={"audio_path": "/fake/path.wav"},
    )
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    from sqlalchemy import text

    row = (
        await session.execute(
            text("SELECT parameters, code_ref FROM feature_extraction_runs WHERE run_id = :rid"),
            {"rid": run_id},
        )
    ).one()
    assert row.parameters is not None
    assert row.code_ref is not None
    assert "essentia" in row.code_ref


@patch("app.services.track_analysis.extract_all_features")
async def test_analyze_track_not_found(mock_extract, client):
    resp = await client.post(
        "/api/v1/tracks/99999/analyze",
        json={"audio_path": "/fake/path.wav"},
    )
    assert resp.status_code == 404
