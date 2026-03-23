"""Compatibility shim — re-exports all names including private."""
from app.audio import key_detect as _src  # noqa: F401
import sys as _sys
_this = _sys.modules[__name__]
for _k, _v in _src.__dict__.items():
    if not _k.startswith("__"):
        setattr(_this, _k, _v)
