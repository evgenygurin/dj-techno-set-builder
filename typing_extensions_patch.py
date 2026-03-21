"""
Temporary patch for typing_extensions to provide TypeForm compatibility.

This is needed because some dependencies (like py-key-value-aio via beartype)
require TypeForm from PEP 747, but it's not yet available in stable
typing_extensions releases.

TODO: Remove this patch once typing_extensions includes TypeForm support.
"""

from typing import Any

import typing_extensions

# Check if TypeForm is already available
if not hasattr(typing_extensions, "TypeForm"):

    class TypeForm[T]:
        """Temporary mock implementation of PEP 747 TypeForm.

        This is a minimal implementation that allows imports to work
        but doesn't provide full PEP 747 functionality.
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __class_getitem__(cls, item: Any) -> "TypeForm[Any]":
            return cls()

        def __getitem__(self, item: Any) -> "TypeForm[Any]":
            return self

    # Patch typing_extensions
    typing_extensions.TypeForm = TypeForm  # type: ignore[attr-defined]

    # Also add to __all__ if it exists
    if hasattr(typing_extensions, "__all__") and "TypeForm" not in typing_extensions.__all__:
        typing_extensions.__all__ = [*list(typing_extensions.__all__), "TypeForm"]
