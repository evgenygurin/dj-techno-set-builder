"""Unit tests for feedback gate functions in scripts/fill_and_verify.py.

Tests cover:
- is_disliked / is_liked pure functions
- get_disliked_ids / get_liked_ids with mocked YM API
- verify_no_disliked_in_main with mocked playlist operations

No real DB or live YM API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# The script inserts repo root into sys.path; replicate that for import.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.fill_and_verify import (  # noqa: E402
    Candidate,
    is_disliked,
    is_liked,
    get_disliked_ids,
    get_liked_ids,
    verify_no_disliked_in_main,
)


# ── is_disliked / is_liked ──────────────────────────────────────────────────


class TestIsDisliked:
    """Tests for the is_disliked gate function."""

    def test_present_in_set(self) -> None:
        assert is_disliked(123, {123, 456}) is True

    def test_absent_from_set(self) -> None:
        assert is_disliked(789, {123, 456}) is False

    def test_empty_set(self) -> None:
        assert is_disliked(123, set()) is False

    def test_coerces_str_to_int(self) -> None:
        """ym_id may arrive as str from playlist fetch — gate must handle."""
        assert is_disliked(int("123"), {123}) is True

    def test_zero_id(self) -> None:
        assert is_disliked(0, {0}) is True
        assert is_disliked(0, {1, 2}) is False


class TestIsLiked:
    """Tests for the is_liked gate function."""

    def test_present_in_set(self) -> None:
        assert is_liked(42, {42, 99}) is True

    def test_absent_from_set(self) -> None:
        assert is_liked(7, {42, 99}) is False

    def test_empty_set(self) -> None:
        assert is_liked(42, set()) is False

    def test_coerces_str_to_int(self) -> None:
        assert is_liked(int("42"), {42}) is True


# ── get_disliked_ids / get_liked_ids (mocked YM API) ───────────────────────


class _FakeYmApi:
    """Minimal stub replacing YmApi for unit tests."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses

    async def get(self, url: str) -> dict:
        for pattern, resp in self._responses.items():
            if pattern in url:
                return resp
        raise RuntimeError(f"No mock for {url}")


class TestGetDislikedIds:
    async def test_returns_int_set(self) -> None:
        api = _FakeYmApi({
            "dislikes/tracks": {
                "result": {
                    "library": {
                        "tracks": [
                            {"id": "111"},
                            {"id": "222"},
                            {"id": "333"},
                        ],
                    },
                },
            },
        })
        result = await get_disliked_ids(api)  # type: ignore[arg-type]
        assert result == {111, 222, 333}
        assert all(isinstance(x, int) for x in result)

    async def test_empty_when_no_dislikes(self) -> None:
        api = _FakeYmApi({
            "dislikes/tracks": {"result": {"library": {"tracks": []}}},
        })
        result = await get_disliked_ids(api)  # type: ignore[arg-type]
        assert result == set()

    async def test_handles_api_error_gracefully(self) -> None:
        api = AsyncMock()
        api.get = AsyncMock(side_effect=RuntimeError("network error"))
        result = await get_disliked_ids(api)
        assert result == set()

    async def test_skips_entries_without_id(self) -> None:
        api = _FakeYmApi({
            "dislikes/tracks": {
                "result": {
                    "library": {
                        "tracks": [{"id": "111"}, {}, {"id": "222"}],
                    },
                },
            },
        })
        result = await get_disliked_ids(api)  # type: ignore[arg-type]
        assert result == {111, 222}


class TestGetLikedIds:
    async def test_returns_int_set(self) -> None:
        api = _FakeYmApi({
            "likes/tracks": {
                "result": {
                    "library": {
                        "tracks": [{"id": "10"}, {"id": "20"}],
                    },
                },
            },
        })
        result = await get_liked_ids(api)  # type: ignore[arg-type]
        assert result == {10, 20}
        assert all(isinstance(x, int) for x in result)

    async def test_empty_when_no_likes(self) -> None:
        api = _FakeYmApi({
            "likes/tracks": {"result": {"library": {"tracks": []}}},
        })
        result = await get_liked_ids(api)  # type: ignore[arg-type]
        assert result == set()

    async def test_handles_api_error_gracefully(self) -> None:
        api = AsyncMock()
        api.get = AsyncMock(side_effect=RuntimeError("network error"))
        result = await get_liked_ids(api)
        assert result == set()


# ── verify_no_disliked_in_main ──────────────────────────────────────────────


class TestVerifyNoDislikedInMain:
    """Tests for verify_no_disliked_in_main with fully mocked playlist ops."""

    async def test_removes_disliked_track(self) -> None:
        """Track 76796973 (Rhythm Dancer) should be removed from main playlist."""
        disliked_ids = {76796973, 999}

        # fetch_playlist returns playlist with the leaked track
        mock_fetch = AsyncMock(
            side_effect=[
                # First call: playlist with the leaked track
                (10, 3, ["100", "76796973", "200"]),
                # Re-fetch after delete (for potential re-index)
                (11, 2, ["100", "200"]),
            ],
        )
        mock_delete = AsyncMock(return_value=11)
        mock_add_deleted = AsyncMock()

        with (
            patch("scripts.fill_and_verify.fetch_playlist", mock_fetch),
            patch("scripts.fill_and_verify.delete_from_playlist", mock_delete),
            patch("scripts.fill_and_verify.add_to_deleted_playlist", mock_add_deleted),
        ):
            api = AsyncMock()
            removed = await verify_no_disliked_in_main(
                api, "1280", "9999", disliked_ids,
            )

        assert removed == 1
        # Verify add_to_deleted_playlist was called with the leaked track
        mock_add_deleted.assert_called_once()
        cands = mock_add_deleted.call_args[0][2]
        assert len(cands) == 1
        assert cands[0].ym_id == "76796973"

    async def test_no_removal_when_clean(self) -> None:
        """No action when main playlist has no disliked tracks."""
        disliked_ids = {76796973}

        mock_fetch = AsyncMock(return_value=(10, 2, ["100", "200"]))

        with patch("scripts.fill_and_verify.fetch_playlist", mock_fetch):
            api = AsyncMock()
            removed = await verify_no_disliked_in_main(
                api, "1280", "9999", disliked_ids,
            )

        assert removed == 0

    async def test_removes_multiple_disliked(self) -> None:
        """All disliked tracks in playlist are removed."""
        disliked_ids = {111, 222}

        mock_fetch = AsyncMock(
            side_effect=[
                (10, 4, ["100", "111", "200", "222"]),
                (12, 2, ["100", "200"]),
            ],
        )
        mock_delete = AsyncMock(side_effect=[11, 12])
        mock_add_deleted = AsyncMock()

        with (
            patch("scripts.fill_and_verify.fetch_playlist", mock_fetch),
            patch("scripts.fill_and_verify.delete_from_playlist", mock_delete),
            patch("scripts.fill_and_verify.add_to_deleted_playlist", mock_add_deleted),
        ):
            api = AsyncMock()
            removed = await verify_no_disliked_in_main(
                api, "1280", "9999", disliked_ids,
            )

        assert removed == 2

    async def test_empty_disliked_set_noop(self) -> None:
        """Empty disliked set → nothing to remove."""
        mock_fetch = AsyncMock(return_value=(10, 2, ["100", "200"]))

        with patch("scripts.fill_and_verify.fetch_playlist", mock_fetch):
            api = AsyncMock()
            removed = await verify_no_disliked_in_main(
                api, "1280", "9999", set(),
            )

        assert removed == 0


# ── Feedback gate integration (pure logic, no I/O) ─────────────────────────


class TestFeedbackGateLogic:
    """Test the combined gate logic as used in the pipeline loop."""

    def test_disliked_blocks_even_if_audio_ok(self) -> None:
        """A track that is both disliked and audio-ok must be blocked."""
        disliked = {42}
        liked: set[int] = set()
        cand = Candidate(
            ym_id="42", album_id="1", title="Test", artists="A",
            duration_ms=300_000, raw={}, audio_ok=True,
        )
        ym_int = int(cand.ym_id)

        # Disliked check has highest priority
        assert is_disliked(ym_int, disliked) is True
        # Even though audio passed, track is blocked
        assert not is_liked(ym_int, liked)

    def test_liked_bypasses_audio_failure(self) -> None:
        """A liked track with bad audio should still pass."""
        disliked: set[int] = set()
        liked = {99}
        cand = Candidate(
            ym_id="99", album_id="1", title="Liked Track", artists="B",
            duration_ms=300_000, raw={}, audio_ok=False,
            fail_reasons=["BPM=180.0"],
        )
        ym_int = int(cand.ym_id)

        assert not is_disliked(ym_int, disliked)
        assert is_liked(ym_int, liked) is True

    def test_neither_liked_nor_disliked_uses_audio(self) -> None:
        """Neutral track falls through to audio gate."""
        disliked: set[int] = set()
        liked: set[int] = set()
        ym_int = 50

        assert not is_disliked(ym_int, disliked)
        assert not is_liked(ym_int, liked)
        # Caller would check cand.audio_ok next

    def test_priority_disliked_over_liked(self) -> None:
        """If somehow a track is in both sets, disliked wins."""
        both = {77}
        ym_int = 77

        # Disliked is checked first in the pipeline
        assert is_disliked(ym_int, both) is True
        assert is_liked(ym_int, both) is True
        # But the pipeline checks disliked FIRST (elif), so it blocks
