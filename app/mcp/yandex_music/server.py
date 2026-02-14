"""Yandex Music MCP server factory — generated from OpenAPI spec."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml
from fastmcp import FastMCP

from app.config import settings
from app.mcp.yandex_music.config import EXCLUDE_ROUTE_MAPS, build_mcp_names

_SPEC_PATH = Path(__file__).resolve().parents[3] / "data" / "yandex-music.yaml"


# operationIds missing from the upstream spec (marked with TODO there).
_MISSING_OPERATION_IDS: dict[tuple[str, str], str] = {
    ("/search/suggest", "get"): "getSearchSuggestions",
    ("/artists/{artistId}/brief-info", "get"): "getArtistBriefInfo",
    ("/artists/{artistId}/direct-albums", "get"): "getArtistDirectAlbums",
}


def _patch_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Normalise the raw OpenAPI dict so FastMCP can parse it.

    1. Convert integer response status codes to strings (YAML ``200`` -> ``"200"``).
    2. Inject missing ``operationId`` values for endpoints that lack them.
    """
    paths: dict[str, Any] = spec.get("paths", {})

    for path, path_item in paths.items():
        for method, method_obj in path_item.items():
            if not isinstance(method_obj, dict):
                continue

            # --- response code fix ---
            responses = method_obj.get("responses")
            if isinstance(responses, dict):
                int_keys = [k for k in responses if isinstance(k, int)]
                for k in int_keys:
                    responses[str(k)] = responses.pop(k)

            # --- missing operationId fix ---
            op_key = (path, method)
            if op_key in _MISSING_OPERATION_IDS and "operationId" not in method_obj:
                method_obj["operationId"] = _MISSING_OPERATION_IDS[op_key]

    return spec


def _load_spec() -> dict[str, Any]:
    """Load and parse the OpenAPI YAML spec."""
    with _SPEC_PATH.open() as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    return _patch_spec(raw)


def create_yandex_music_mcp() -> FastMCP:
    """Create a FastMCP server from the Yandex Music OpenAPI spec.

    Filters endpoints via RouteMap to expose only DJ-relevant tools.
    Authenticates via OAuth token from app settings.
    """
    spec = _load_spec()

    client = httpx.AsyncClient(
        base_url=settings.yandex_music_base_url,
        headers={
            "Authorization": f"OAuth {settings.yandex_music_token}",
            "Accept": "application/json",
        },
        timeout=30.0,
    )

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="Yandex Music",
        route_maps=EXCLUDE_ROUTE_MAPS,
        mcp_names=build_mcp_names(spec),
    )
