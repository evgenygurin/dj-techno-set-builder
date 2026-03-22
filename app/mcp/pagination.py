"""Cursor-based pagination utilities.

Cursor = base64(JSON{"offset": N}). Simple, stateless, no DB dependency.
"""

from __future__ import annotations

import base64
import json

MAX_LIMIT = 100
MIN_LIMIT = 1


def encode_cursor(*, offset: int) -> str:
    """Encode pagination state into an opaque cursor string."""
    payload = json.dumps({"offset": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str | None) -> dict[str, int]:
    """Decode cursor back to pagination state. Returns defaults on any error."""
    if not cursor:
        return {"offset": 0}
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(payload)
        return {"offset": max(0, int(data.get("offset", 0)))}
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return {"offset": 0}


def paginate_params(*, cursor: str | None = None, limit: int = 20) -> tuple[int, int]:
    """Return (offset, clamped_limit) from cursor + limit."""
    params = decode_cursor(cursor)
    clamped = max(MIN_LIMIT, min(limit, MAX_LIMIT))
    return params["offset"], clamped
