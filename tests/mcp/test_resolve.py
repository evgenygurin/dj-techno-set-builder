"""Tests for resolve_local_id helper."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from app.mcp.resolve import resolve_local_id


def test_resolve_bare_int():
    assert resolve_local_id(42) == 42


def test_resolve_string_int():
    assert resolve_local_id("42") == 42


def test_resolve_local_urn():
    assert resolve_local_id("local:42") == 42


def test_resolve_text_raises():
    with pytest.raises(ToolError, match="Cannot resolve"):
        resolve_local_id("Boris Brejcha")


def test_resolve_platform_raises():
    with pytest.raises(ToolError, match="Cannot resolve"):
        resolve_local_id("ym:12345")
