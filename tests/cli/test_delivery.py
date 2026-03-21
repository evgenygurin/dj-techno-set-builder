"""Tests for CLI delivery sub-command."""

from __future__ import annotations

from app.cli.delivery import _safe_name, _sanitize_fn

# ── Pure helper tests ────────────────────────────────────────────────────


def test_safe_name_basic() -> None:
    assert _safe_name("My Cool Set") == "my_cool_set"


def test_safe_name_special_chars() -> None:
    assert _safe_name("Set: A/B Test?") == "set_ab_test"


def test_safe_name_unicode() -> None:
    assert _safe_name("Сет 1") == "сет_1"


def test_sanitize_fn_removes_unsafe() -> None:
    assert _sanitize_fn('Hello <World> "Test"') == "Hello World Test"
    assert _sanitize_fn("file:name|here?") == "filenamehere"
    assert _sanitize_fn("normal name") == "normal name"


def test_sanitize_fn_strips_whitespace() -> None:
    assert _sanitize_fn("  padded  ") == "padded"
