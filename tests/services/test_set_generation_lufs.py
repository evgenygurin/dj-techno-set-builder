"""Test LUFS-based energy in set generation."""

from app.audio.set_generator import TrackData, lufs_to_energy


def test_track_data_uses_lufs_energy():
    """Verify TrackData energy should come from LUFS, not energy_mean."""
    # Simulate what set_generation.py should do
    lufs_i = -8.0
    energy = lufs_to_energy(lufs_i)
    track = TrackData(track_id=1, bpm=130.0, energy=energy, key_code=4)
    assert 0.7 <= track.energy <= 0.8  # -8 LUFS -> ~0.75 energy
