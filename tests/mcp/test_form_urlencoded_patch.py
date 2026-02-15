"""Test that the httpx event hook converts JSON POST bodies to form-urlencoded.

FastMCP's RequestDirector.build() always uses ``json=`` for dict bodies,
producing ``Content-Type: application/json``.  Yandex Music API expects
``application/x-www-form-urlencoded`` for all POST endpoints.

Our hook in ``app.mcp.yandex_music.server._json_to_form_urlencoded`` intercepts
requests and re-encodes JSON bodies as form data before they are sent.
"""

from __future__ import annotations

import json

import httpx

from app.mcp.yandex_music.server import _json_to_form_urlencoded, _strip_empty


class TestJsonToFormUrlencodedHook:
    """Verify the httpx event hook converts POST JSON bodies to form-urlencoded."""

    async def test_post_json_converted_to_form(self) -> None:
        """POST with JSON body must be re-encoded as form-urlencoded."""
        request = httpx.Request(
            "POST",
            "https://api.example.com/users/123/playlists/create",
            json={"title": "Test Playlist", "visibility": "public"},
        )
        assert "application/json" in request.headers["content-type"]

        await _json_to_form_urlencoded(request)

        assert request.headers["content-type"] == "application/x-www-form-urlencoded"
        body = request.content.decode()
        assert "title=Test+Playlist" in body
        assert "visibility=public" in body

    async def test_get_request_unchanged(self) -> None:
        """GET requests must not be modified."""
        request = httpx.Request("GET", "https://api.example.com/tracks/42")
        original_headers = dict(request.headers)

        await _json_to_form_urlencoded(request)

        assert dict(request.headers) == original_headers

    async def test_non_json_post_unchanged(self) -> None:
        """POST with non-JSON content-type must not be modified."""
        request = httpx.Request(
            "POST",
            "https://api.example.com/upload",
            content=b"raw bytes",
            headers={"content-type": "application/octet-stream"},
        )

        await _json_to_form_urlencoded(request)

        assert request.headers["content-type"] == "application/octet-stream"
        assert request.content == b"raw bytes"

    async def test_post_with_nested_values(self) -> None:
        """POST with list values must use doseq=True encoding."""
        request = httpx.Request(
            "POST",
            "https://api.example.com/playlists/change",
            json={"diff": json.dumps([{"op": "insert", "at": 0, "tracks": [{"id": "1"}]}])},
        )

        await _json_to_form_urlencoded(request)

        assert request.headers["content-type"] == "application/x-www-form-urlencoded"
        body = request.content.decode()
        assert "diff=" in body

    async def test_content_length_updated(self) -> None:
        """Content-Length header must match the new body size."""
        request = httpx.Request(
            "POST",
            "https://api.example.com/test",
            json={"key": "value"},
        )

        await _json_to_form_urlencoded(request)

        assert int(request.headers["content-length"]) == len(request.content)

    async def test_empty_values_stripped(self) -> None:
        """Keys with None or empty-string values must be removed."""
        request = httpx.Request(
            "POST",
            "https://api.example.com/playlists/change",
            json={"title": "Test", "albumId": "", "extra": None, "valid": "ok"},
        )

        await _json_to_form_urlencoded(request)

        body = request.content.decode()
        assert "title=Test" in body
        assert "valid=ok" in body
        assert "albumId" not in body
        assert "extra" not in body


class TestStripEmpty:
    """Verify _strip_empty helper."""

    def test_removes_none_and_empty_string(self) -> None:
        result = _strip_empty({"a": "1", "b": None, "c": "", "d": "2"})
        assert result == {"a": "1", "d": "2"}

    def test_keeps_zero_and_false(self) -> None:
        result = _strip_empty({"a": 0, "b": False, "c": "ok"})
        assert result == {"a": 0, "b": False, "c": "ok"}

    def test_empty_dict(self) -> None:
        assert _strip_empty({}) == {}
