# Import typing_extensions patch early to fix TypeForm compatibility issue
import contextlib

with contextlib.suppress(ImportError):
    import typing_extensions_patch  # noqa: F401
