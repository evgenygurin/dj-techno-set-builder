"""Elicitation helpers for destructive MCP operations.

Fail-closed: if elicitation fails or user declines, return False.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)


async def confirm_action(ctx: Context, message: str) -> bool:
    """Ask user to confirm a destructive action. Fail-closed on error/decline."""
    try:
        from fastmcp.server.elicitation import AcceptedElicitation

        result = await ctx.elicit(message=message)  # type: ignore[call-arg]
        if isinstance(result, AcceptedElicitation):
            return True
        logger.info("User declined action: %s", message)
        return False
    except (NotImplementedError, AttributeError, TypeError) as exc:
        logger.warning("Elicitation not supported: %s", exc)
        return False  # fail-closed


async def resolve_conflict(
    ctx: Context,
    description: str,
    options: list[str],
) -> str | None:
    """Ask user to resolve a conflict via choices. Returns chosen option or None."""
    try:
        from fastmcp.server.elicitation import AcceptedElicitation

        result = await ctx.elicit(
            message=description,
            response_type=options,  # type: ignore[arg-type]  # list[str] = choices
        )
        if isinstance(result, AcceptedElicitation):
            data: Any = result.data
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                return data.get("choice")
            return str(data) if data else None
        return None
    except (NotImplementedError, AttributeError, TypeError):
        return None
