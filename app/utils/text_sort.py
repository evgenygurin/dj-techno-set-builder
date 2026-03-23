from __future__ import annotations

import re
import unicodedata

_LEADING_ARTICLES = re.compile(r"^(the|a|an|der|die|das|le|la|les)\s+")
_BAD_PATH_RE = re.compile(r'[<>:"/\\|?*]')


def sort_key(name: str) -> str:
    """Normalize text for stable lexical sorting."""
    normalized = unicodedata.normalize("NFKD", name).lower().strip()
    return _LEADING_ARTICLES.sub("", normalized)


def sanitize_filename(name: str) -> str:
    """Replace characters forbidden on Windows/macOS with ``_``."""
    return _BAD_PATH_RE.sub("_", name).strip()
