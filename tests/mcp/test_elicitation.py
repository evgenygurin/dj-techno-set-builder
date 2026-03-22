"""Tests for elicitation helpers (destructive MCP operations)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastmcp.server.elicitation import AcceptedElicitation
from mcp.server.elicitation import DeclinedElicitation

from app.mcp.elicitation import confirm_action, resolve_conflict

# ---------------------------------------------------------------------------
# confirm_action
# ---------------------------------------------------------------------------


async def test_confirm_action_returns_true_on_accept() -> None:
    """Returns True when user accepts the elicitation."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(return_value=AcceptedElicitation(action="accept", data=True))

    result = await confirm_action(ctx, "Delete this track?")

    assert result is True
    ctx.elicit.assert_awaited_once_with(message="Delete this track?")


async def test_confirm_action_returns_false_on_decline() -> None:
    """Returns False when user declines the elicitation (fail-closed)."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(return_value=DeclinedElicitation(action="decline"))

    result = await confirm_action(ctx, "Overwrite playlist?")

    assert result is False


async def test_confirm_action_graceful_degradation() -> None:
    """Returns False when elicitation is not supported (fail-closed)."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(side_effect=NotImplementedError("no elicitation"))

    result = await confirm_action(ctx, "Purge library?")

    assert result is False


async def test_confirm_action_attribute_error_returns_false() -> None:
    """Returns False when ctx has no elicit method (fail-closed)."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(side_effect=AttributeError("no elicit"))

    result = await confirm_action(ctx, "Delete set?")

    assert result is False


async def test_confirm_action_type_error_returns_false() -> None:
    """Returns False on TypeError from elicit call (fail-closed)."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(side_effect=TypeError("bad args"))

    result = await confirm_action(ctx, "Archive track?")

    assert result is False


# ---------------------------------------------------------------------------
# resolve_conflict
# ---------------------------------------------------------------------------


async def test_resolve_conflict_returns_choice_as_string() -> None:
    """Returns the chosen option when data is a plain string."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(return_value=AcceptedElicitation(action="accept", data="option1"))

    result = await resolve_conflict(ctx, "Choose merge strategy:", ["option1", "option2"])

    assert result == "option1"
    ctx.elicit.assert_awaited_once_with(
        message="Choose merge strategy:", response_type=["option1", "option2"]
    )


async def test_resolve_conflict_returns_choice_from_dict() -> None:
    """Returns the 'choice' key when data is a dict."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(
        return_value=AcceptedElicitation(action="accept", data={"choice": "option2"})
    )

    result = await resolve_conflict(ctx, "Pick one:", ["option1", "option2"])

    assert result == "option2"


async def test_resolve_conflict_returns_none_on_decline() -> None:
    """Returns None when user declines conflict resolution."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(return_value=DeclinedElicitation(action="decline"))

    result = await resolve_conflict(ctx, "Choose:", ["a", "b"])

    assert result is None


async def test_resolve_conflict_graceful_degradation() -> None:
    """Returns None when elicitation is not supported."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(side_effect=NotImplementedError("no elicitation"))

    result = await resolve_conflict(ctx, "Choose:", ["a", "b"])

    assert result is None


async def test_resolve_conflict_stringifies_unexpected_data() -> None:
    """Returns str(data) for non-str, non-dict accepted data."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(return_value=AcceptedElicitation(action="accept", data=42))

    result = await resolve_conflict(ctx, "Choose:", ["42"])

    assert result == "42"


async def test_resolve_conflict_none_data_returns_none() -> None:
    """Returns None when accepted but data is falsy."""
    ctx = AsyncMock()
    ctx.elicit = AsyncMock(return_value=AcceptedElicitation(action="accept", data=None))

    result = await resolve_conflict(ctx, "Choose:", ["a"])

    assert result is None
