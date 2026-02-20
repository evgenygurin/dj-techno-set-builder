"""Reusable elicitation helpers for DJ workflow tools.

Uses FastMCP's ctx.elicit() to prompt users for confirmation
or conflict resolution during tool execution.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from fastmcp.server.elicitation import AcceptedElicitation

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)


async def confirm_action(
    ctx: Context,
    *,
    message: str,
    action_description: str,
) -> bool:
    """Ask user to confirm a destructive or significant action.

    Returns True if user confirms or if elicitation is not supported
    by the client (fail-open for non-interactive clients).
    """
    try:
        response = await ctx.elicit(message=message, response_type=bool)  # type: ignore[arg-type]
        if isinstance(response, AcceptedElicitation):
            confirmed = bool(response.data)
            if not confirmed:
                await ctx.info(f"Action cancelled by user: {action_description}")
            return confirmed
        # Declined or Cancelled
        await ctx.info(f"Action cancelled by user: {action_description}")
        return False
    except (NotImplementedError, AttributeError, Exception):
        logger.debug(
            "Elicitation not supported, proceeding with action: %s",
            action_description,
        )
        return True


async def resolve_conflict(
    ctx: Context,
    *,
    message: str,
    options: type[Enum],
) -> Enum:
    """Ask user to choose between conflict resolution strategies.

    Falls back to first enum value if elicitation is not supported.
    """
    try:
        response = await ctx.elicit(message=message, response_type=options)  # type: ignore[arg-type]
        if isinstance(response, AcceptedElicitation):
            return response.data  # type: ignore[return-value]
        # Declined or Cancelled — use default
        default = next(iter(options))
        logger.debug("Elicitation declined, using default: %s", default)
        return default
    except (NotImplementedError, AttributeError, Exception):
        default = next(iter(options))
        logger.debug("Elicitation not supported, using default: %s", default)
        return default
