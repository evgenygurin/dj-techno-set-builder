"""Yandex Music MCP server factory — generated from OpenAPI spec."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import yaml
from fastmcp import FastMCP

from app.core.config import settings
from app.mcp.yandex_music.config import EXCLUDE_ROUTE_MAPS, build_mcp_names
from app.mcp.yandex_music.response_filters import clean_ym_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# httpx event hook: convert JSON POST bodies to application/x-www-form-urlencoded.
#
# FastMCP's RequestDirector.build() always uses ``json=`` for dict bodies,
# producing ``Content-Type: application/json``.  Yandex Music API expects
# ``application/x-www-form-urlencoded`` for ALL POST endpoints, so
# parameters arrive empty → 400 "Parameter value is not set".
#
# This hook runs *after* the request is built but *before* it is sent,
# transparently re-encoding JSON bodies as form data.
# ---------------------------------------------------------------------------
def _strip_empty(body: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with None or empty-string values.

    YM API returns 400 "Parameters requirements are not met" when it
    receives keys with empty values (e.g. ``albumId=``).
    """
    return {k: v for k, v in body.items() if v is not None and v != ""}


async def _json_to_form_urlencoded(request: httpx.Request) -> None:
    """Convert JSON POST bodies to form-urlencoded for YM API compatibility.

    Must be ``async`` because httpx 0.28+ ``await``s request event hooks
    in ``AsyncClient`` (line 1692 of ``_client.py``).

    Also strips keys with None / empty-string values — YM API rejects them.
    """
    if request.method != "POST":
        return

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return

    # Decode JSON body → strip empty values → re-encode as form data
    try:
        body = json.loads(request.content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    if not isinstance(body, dict):
        return

    body = _strip_empty(body)
    form_body = urlencode(body, doseq=True).encode("utf-8")

    # Replace content, headers, and internal stream
    request.headers["content-type"] = "application/x-www-form-urlencoded"
    request.headers["content-length"] = str(len(form_body))
    request.stream = httpx.ByteStream(form_body)
    # httpx caches decoded content in _content; update it too
    request._content = form_body


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
    3. Break circular ``$ref`` in schemas (Genre.subGenres -> Genre).
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

    # --- break circular $ref chains ---
    # Cycles: Artist.popularTracks→Track, Track.artists→Artist,
    #         Track.albums→Album, Album.artists→Artist, Genre.subGenres→Genre
    _break_circular_refs(spec)

    return spec


# (schema_name, property_name) pairs where $ref creates a cycle.
# Replace the $ref with a plain object/array stub.
_CIRCULAR_REFS: list[tuple[str, str]] = [
    ("Artist", "popularTracks"),  # Artist → Track → Artist
    ("Album", "artists"),  # Album → Artist → Track → Album
    ("Album", "volumes"),  # Album → Track → Album
    ("Genre", "subGenres"),  # Genre → Genre
]


def _break_circular_refs(spec: dict[str, Any]) -> None:
    """Replace circular $ref pointers with plain ``object`` stubs."""
    schemas = spec.get("components", {}).get("schemas", {})
    for schema_name, prop_name in _CIRCULAR_REFS:
        prop = schemas.get(schema_name, {}).get("properties", {}).get(prop_name)
        if prop is None:
            continue
        _remove_nested_refs(prop)


def _remove_nested_refs(obj: dict[str, Any]) -> None:
    """Recursively remove $ref from a property, replacing with object stubs."""
    if "$ref" in obj:
        obj.pop("$ref")
        obj["type"] = "object"
    items = obj.get("items")
    if isinstance(items, dict):
        _remove_nested_refs(items)


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
        event_hooks={
            "request": [_json_to_form_urlencoded],
            "response": [clean_ym_response],
        },
    )

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="Yandex Music",
        route_maps=EXCLUDE_ROUTE_MAPS,
        mcp_names=build_mcp_names(spec),
        validate_output=False,  # YM API responses don't match the (unofficial) OpenAPI spec
    )
