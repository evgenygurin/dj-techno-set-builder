"""Python 3.13 compatibility shims and fixes."""

from __future__ import annotations

import sys
from typing import Any


def _patch_typing_extensions() -> None:
    """Patch typing_extensions to provide TypeForm for Python 3.13 compatibility.

    TypeForm was introduced in typing_extensions 4.16.0 but may not be available
    in all environments. This provides a basic compatibility shim.
    """
    try:
        import typing_extensions

        # Check if TypeForm is already available
        if hasattr(typing_extensions, "TypeForm"):
            return

        # Create a minimal TypeForm implementation
        # This is a temporary shim until proper typing_extensions version is available
        class TypeForm:
            """Compatibility shim for typing_extensions.TypeForm."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def __class_getitem__(cls, item: Any) -> Any:
                return cls

        # Monkey patch typing_extensions
        typing_extensions.TypeForm = TypeForm  # type: ignore[assignment]

    except ImportError:
        # typing_extensions not available, skip patching
        pass


def apply_python313_compatibility() -> None:
    """Apply all Python 3.13 compatibility patches."""
    if sys.version_info >= (3, 13):
        _patch_typing_extensions()
