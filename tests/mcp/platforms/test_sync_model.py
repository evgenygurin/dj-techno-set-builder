"""Tests for DjPlaylist sync columns."""

from __future__ import annotations

from app.models.dj import DjPlaylist


class TestDjPlaylistSyncFields:
    def test_default_source_of_truth(self) -> None:
        """New playlists default to local as source of truth."""
        pl = DjPlaylist(
            name="Test",
            source_of_truth="local",
        )
        assert pl.source_of_truth == "local"

    def test_ym_source_of_truth(self) -> None:
        pl = DjPlaylist(
            name="Test",
            source_of_truth="ym",
        )
        assert pl.source_of_truth == "ym"

    def test_platform_ids_json(self) -> None:
        pl = DjPlaylist(
            name="Test",
            platform_ids={"ym": "1003:250905515"},
        )
        assert pl.platform_ids["ym"] == "1003:250905515"

    def test_platform_ids_default_none(self) -> None:
        pl = DjPlaylist(name="Test")
        assert pl.platform_ids is None
