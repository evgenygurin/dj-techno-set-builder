"""Compatibility shim — import from app.core.models instead."""

from app.core.models import *  # noqa: F401,F403
from app.core.models import Base  # noqa: F401
