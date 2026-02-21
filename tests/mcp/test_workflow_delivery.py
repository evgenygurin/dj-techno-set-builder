"""Tests for deliver_set MCP tool."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastmcp import Client, FastMCP

from app.mcp.tools.delivery import _build_transition_summary, _generate_cheat_sheet, _safe_name
from app.mcp.types.workflows import TransitionScoreResult

# ── Unit tests for helpers ─────────────────────────────────────────────────


def test_safe_name_basic():
    assert _safe_name("Эксклюзив техно") == "эксклюзив_техно"


def test_safe_name_strips_dots_and_spaces():
    assert _safe_name("  ..My Set..  ") == "my_set"


def test_safe_name_removes_bad_chars():
    name = _safe_name('Set: "Dark" <2024>')
    assert "<" not in name
    assert ">" not in name
    assert '"' not in name


def test_build_transition_summary_empty():
    summary = _build_transition_summary([])
    assert summary.total == 0
    assert summary.hard_conflicts == 0
    assert summary.weak == 0
    assert summary.avg_score == 0.0
    assert summary.min_score == 0.0


def _make_score(total: float, from_id: int = 1, to_id: int = 2) -> TransitionScoreResult:
    return TransitionScoreResult(
        from_track_id=from_id,
        to_track_id=to_id,
        from_title="A",
        to_title="B",
        total=total,
        bpm=0.9,
        harmonic=0.9,
        energy=0.9,
        spectral=0.9,
        groove=0.9,
    )


def test_build_transition_summary_counts():
    scores = [_make_score(0.0), _make_score(0.7), _make_score(0.9)]
    summary = _build_transition_summary(scores)
    assert summary.total == 3
    assert summary.hard_conflicts == 1
    assert summary.weak == 1  # 0.7 < 0.85
    assert pytest.approx(summary.avg_score, abs=0.01) == (0.7 + 0.9) / 2
    assert summary.min_score == 0.7


def test_generate_cheat_sheet_basic():
    tracks = [
        {"position": 1, "track_id": 1, "title": "Alpha", "bpm": 140.0, "key": "8A", "lufs": -8.0},
        {"position": 2, "track_id": 2, "title": "Beta", "bpm": 142.0, "key": "9A", "lufs": -7.0},
    ]
    scores = [_make_score(0.92)]
    sheet = _generate_cheat_sheet("Test Set", tracks, scores)
    assert "CHEAT SHEET: Test Set" in sheet
    assert "Alpha" in sheet
    assert "Beta" in sheet
    assert "8A→9A" in sheet


def test_generate_cheat_sheet_flags_weak():
    tracks = [
        {"position": 1, "track_id": 1, "title": "A", "bpm": 140.0},
        {"position": 2, "track_id": 2, "title": "B", "bpm": 142.0},
    ]
    scores = [_make_score(0.5)]  # < 0.85 → !!!
    sheet = _generate_cheat_sheet("Test", tracks, scores)
    assert "!!!" in sheet


# ── Registration tests ──────────────────────────────────────────────────────


async def test_deliver_set_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "deliver_set" in tool_names


async def test_deliver_set_has_setbuilder_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name == "deliver_set":
            assert tool.tags is not None
            assert "setbuilder" in tool.tags
            break


async def test_deliver_set_parameters(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "deliver_set")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "set_ref" in props
    assert "version_id" in props
    assert "sync_to_ym" in props
    assert "ym_user_id" in props
    assert "ym_playlist_title" in props


async def test_gateway_has_dj_deliver_set(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_deliver_set" in tool_names


# ── Integration test: deliver empty set version ─────────────────────────────


async def test_deliver_set_empty_version(workflow_mcp_with_db: FastMCP, engine, tmp_path):
    """deliver_set on a version with 0 items → ok with no transitions, all 3 files written."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.sets import DjSet, DjSetVersion

    # Seed via the same engine the MCP server uses
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        dj_set = DjSet(name="Test Delivery Set")
        session.add(dj_set)
        await session.flush()
        version = DjSetVersion(set_id=dj_set.set_id)
        session.add(version)
        await session.flush()
        set_id = dj_set.set_id
        version_id = version.set_version_id
        await session.commit()

    # Patch output dir to tmp_path so no real filesystem writes outside tests
    with patch("app.mcp.tools.delivery._output_dir", return_value=tmp_path):
        async with Client(workflow_mcp_with_db) as c:
            raw = await c.call_tool(
                "deliver_set",
                {"set_ref": set_id, "version_id": version_id},
            )

    # DeliveryResult Pydantic model → FastMCP puts fields directly in structured_content
    sc = raw.structured_content
    assert sc is not None
    assert sc["set_id"] == set_id
    assert sc["version_id"] == version_id
    assert sc["status"] == "ok"
    # 0 items → no transitions → no hard conflicts → all 3 files written
    assert sc["transitions"]["total"] == 0
    assert len(sc["files_written"]) == 3
