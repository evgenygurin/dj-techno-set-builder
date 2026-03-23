from __future__ import annotations

import re
import unicodedata

_LEADING_ARTICLES = re.compile(r"^(the|a|an|der|die|das|le|la|les)\s+")


def sort_key(name: str) -> str:
    """Normalize text for stable lexical sorting."""
    normalized = unicodedata.normalize("NFKD", name).lower().strip()
    return _LEADING_ARTICLES.sub("", normalized)
