"""Resolve entity refs to local IDs for legacy tools."""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from app.mcp.refs import RefType, parse_ref


def resolve_local_id(ref: str | int, entity_name: str = "entity") -> int:
    """Resolve a ref to a local integer ID.

    Accepts: bare int, "42", "local:42".
    Rejects: text queries, platform refs (use CRUD tools for those).

    Raises:
        ToolError: If ref cannot be resolved to a local ID.
    """
    parsed = parse_ref(ref)
    if parsed.ref_type == RefType.LOCAL and parsed.local_id is not None:
        return parsed.local_id
    msg = (
        f"Cannot resolve {entity_name} ref '{ref}' to a local ID. "
        f"Use a numeric ID, 'local:ID', or find the ID via search/list tools first."
    )
    raise ToolError(msg)
