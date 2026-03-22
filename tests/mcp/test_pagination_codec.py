"""Tests for cursor-based pagination codec."""

from app.mcp.pagination import decode_cursor, encode_cursor, paginate_params


class TestCursorCodec:
    def test_encode_decode_roundtrip(self):
        cursor = encode_cursor(offset=50)
        assert isinstance(cursor, str)
        params = decode_cursor(cursor)
        assert params["offset"] == 50

    def test_decode_none_returns_defaults(self):
        params = decode_cursor(None)
        assert params["offset"] == 0

    def test_decode_invalid_returns_defaults(self):
        params = decode_cursor("not-valid-base64!")
        assert params["offset"] == 0

    def test_decode_empty_string_returns_defaults(self):
        params = decode_cursor("")
        assert params["offset"] == 0


class TestPaginateParams:
    def test_no_cursor(self):
        offset, limit = paginate_params(cursor=None, limit=20)
        assert offset == 0
        assert limit == 20

    def test_with_cursor(self):
        cursor = encode_cursor(offset=40)
        offset, limit = paginate_params(cursor=cursor, limit=20)
        assert offset == 40
        assert limit == 20

    def test_limit_clamped(self):
        _offset, limit = paginate_params(cursor=None, limit=500)
        assert limit == 100  # max limit

    def test_limit_minimum(self):
        _offset, limit = paginate_params(cursor=None, limit=0)
        assert limit == 1
