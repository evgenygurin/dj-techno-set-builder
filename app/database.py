"""Compatibility shim — import from app.infrastructure.database instead."""

from app.infrastructure.database import *  # noqa: F401,F403
from app.infrastructure.database import (  # noqa: F401
    engine,
    get_session,
    init_db,
    session_factory,
)
