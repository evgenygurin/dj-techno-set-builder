"""RouteMap configuration for Yandex Music MCP server."""

from __future__ import annotations

import re
from typing import Any

from fastmcp.server.providers.openapi import MCPType, RouteMap

# Patterns for endpoints to EXCLUDE (non-DJ-relevant)
EXCLUDE_ROUTE_MAPS: list[RouteMap] = [
    RouteMap(pattern=r"^/account", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/feed", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/landing3", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/rotor", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/queues", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/settings$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/permission-alerts$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/token$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/play-audio$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/non-music", mcp_type=MCPType.EXCLUDE),
]


def _camel_to_snake(name: str) -> str:
    """Convert camelCase operationId to snake_case tool name."""
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return s.lower()


def build_mcp_names(spec: dict[str, Any]) -> dict[str, str]:
    """Build operationId -> snake_case mapping from OpenAPI spec.

    Special case: 'search' -> 'search_yandex_music' to avoid name collisions.
    """
    names: dict[str, str] = {}
    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                op_id = operation["operationId"]
                snake = _camel_to_snake(op_id)
                names[op_id] = snake
    # Explicit override for generic names
    if "search" in names:
        names["search"] = "search_yandex_music"
    return names
