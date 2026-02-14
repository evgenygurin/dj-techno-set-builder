"""Tests for sampling-related Pydantic types."""

from __future__ import annotations

from app.mcp.types import AdjustmentPlan, ReorderSuggestion, SwapSuggestion


def test_swap_suggestion_creation():
    swap = SwapSuggestion(position=3, reason="BPM mismatch")
    assert swap.position == 3
    assert swap.reason == "BPM mismatch"


def test_reorder_suggestion_creation():
    reorder = ReorderSuggestion(from_position=1, to_position=5, reason="Energy flow")
    assert reorder.from_position == 1
    assert reorder.to_position == 5


def test_adjustment_plan_creation():
    plan = AdjustmentPlan(
        reasoning="Improve energy flow in second half",
        swap_suggestions=[SwapSuggestion(position=3, reason="BPM mismatch")],
        reorder_suggestions=[
            ReorderSuggestion(from_position=1, to_position=5, reason="Energy flow")
        ],
    )
    assert len(plan.swap_suggestions) == 1
    assert len(plan.reorder_suggestions) == 1


def test_adjustment_plan_empty_suggestions():
    plan = AdjustmentPlan(
        reasoning="Set looks good",
        swap_suggestions=[],
        reorder_suggestions=[],
    )
    assert plan.swap_suggestions == []
    assert plan.reorder_suggestions == []
