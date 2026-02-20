"""Entity reference parser.

Parses URN-style refs into structured ParsedRef:
  "local:42"            → LOCAL, id=42
  "ym:12345"            → PLATFORM, source="ym", platform_id="12345"
  42                    → LOCAL, id=42
  "Boris Brejcha"       → TEXT, query="Boris Brejcha"
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

KNOWN_PLATFORMS = frozenset({"local", "ym", "spotify", "beatport", "soundcloud"})


class RefType(StrEnum):
    LOCAL = "local"
    PLATFORM = "platform"
    TEXT = "text"


@dataclass(frozen=True)
class ParsedRef:
    ref_type: RefType
    source: str = ""
    local_id: int | None = None
    platform_id: str | None = None
    query: str | None = None


def parse_ref(ref: str | int) -> ParsedRef:
    """Parse an entity reference string into a structured ParsedRef."""
    if isinstance(ref, int):
        return ParsedRef(ref_type=RefType.LOCAL, source="local", local_id=ref)

    ref = str(ref).strip()
    if not ref:
        msg = "Entity ref cannot be empty"
        raise ValueError(msg)

    # Bare integer: "42"
    try:
        return ParsedRef(ref_type=RefType.LOCAL, source="local", local_id=int(ref))
    except ValueError:
        pass

    # URN format: "source:id"
    if ":" in ref:
        prefix, _, suffix = ref.partition(":")
        if prefix.lower() in KNOWN_PLATFORMS and suffix:
            if prefix.lower() == "local":
                try:
                    return ParsedRef(ref_type=RefType.LOCAL, source="local", local_id=int(suffix))
                except ValueError:
                    pass
            else:
                return ParsedRef(
                    ref_type=RefType.PLATFORM,
                    source=prefix.lower(),
                    platform_id=suffix,
                )

    # Everything else: text query for fuzzy search
    return ParsedRef(ref_type=RefType.TEXT, query=ref)
