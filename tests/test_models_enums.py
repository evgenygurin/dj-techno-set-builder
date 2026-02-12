from app.models.enums import ArtistRole, AssetType, RunStatus, SectionType, SourceApp


def test_artist_role_values() -> None:
    assert ArtistRole.PRIMARY == 0
    assert ArtistRole.FEATURED == 1
    assert ArtistRole.REMIXER == 2


def test_section_type_range() -> None:
    assert len(SectionType) == 12
    assert SectionType.INTRO == 0
    assert SectionType.UNKNOWN == 11


def test_source_app_range() -> None:
    assert SourceApp.TRAKTOR == 1
    assert SourceApp.GENERATED == 5


def test_asset_type_range() -> None:
    assert AssetType.FULL_MIX == 0
    assert AssetType.PREVIEW_CLIP == 5


def test_run_status_values() -> None:
    assert RunStatus.RUNNING.value == "running"
    assert RunStatus.COMPLETED.value == "completed"
    assert RunStatus.FAILED.value == "failed"
