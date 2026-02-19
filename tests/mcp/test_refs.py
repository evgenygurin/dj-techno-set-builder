"""Tests for entity reference parser."""

import pytest

from app.mcp.refs import ParsedRef, RefType, parse_ref


class TestParseRef:
    def test_local_id_with_prefix(self):
        r = parse_ref("local:42")
        assert r.ref_type == RefType.LOCAL
        assert r.local_id == 42
        assert r.source == "local"

    def test_bare_integer(self):
        r = parse_ref("42")
        assert r.ref_type == RefType.LOCAL
        assert r.local_id == 42

    def test_integer_input(self):
        r = parse_ref(42)
        assert r.ref_type == RefType.LOCAL
        assert r.local_id == 42

    def test_platform_ym(self):
        r = parse_ref("ym:12345")
        assert r.ref_type == RefType.PLATFORM
        assert r.source == "ym"
        assert r.platform_id == "12345"

    def test_platform_spotify(self):
        r = parse_ref("spotify:abc123")
        assert r.ref_type == RefType.PLATFORM
        assert r.source == "spotify"
        assert r.platform_id == "abc123"

    def test_text_query(self):
        r = parse_ref("Boris Brejcha")
        assert r.ref_type == RefType.TEXT
        assert r.query == "Boris Brejcha"

    def test_text_with_dash(self):
        r = parse_ref("Boris Brejcha - Gravity")
        assert r.ref_type == RefType.TEXT
        assert r.query == "Boris Brejcha - Gravity"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_ref("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_ref("   ")

    def test_known_platforms(self):
        """Only known platform prefixes are treated as URN."""
        r = parse_ref("beatport:67890")
        assert r.ref_type == RefType.PLATFORM
        assert r.source == "beatport"

    def test_unknown_prefix_treated_as_text(self):
        """'genre:techno' is NOT a platform ref — treated as text query."""
        r = parse_ref("genre:techno")
        assert r.ref_type == RefType.TEXT
        assert r.query == "genre:techno"
