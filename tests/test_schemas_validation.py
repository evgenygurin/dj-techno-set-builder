from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.dj import DjSavedLoopDTO
from app.schemas.features import KeyDTO, TransitionCandidateDTO
from app.schemas.providers import ProviderTrackIdDTO


def test_provider_country_normalized() -> None:
    dto = ProviderTrackIdDTO(
        track_id=1, provider_id=1, provider_track_id="x", provider_country=" us "
    )
    assert dto.provider_country == "US"


def test_loop_cross_field_validation() -> None:
    with pytest.raises(ValidationError):
        DjSavedLoopDTO(track_id=1, in_ms=1000, out_ms=900, length_ms=1)


def test_key_mapping_validation() -> None:
    with pytest.raises(ValidationError):
        KeyDTO(key_code=3, pitch_class=0, mode=0, name="Cm")


def test_transition_candidate_direction_validation() -> None:
    with pytest.raises(ValidationError):
        TransitionCandidateDTO(
            from_track_id=1, to_track_id=1, run_id=1, bpm_distance=0.1, key_distance=0.2
        )
