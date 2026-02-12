"""Base service class."""

from __future__ import annotations

import logging


class BaseService:
    """Thin base that every domain service inherits.

    Provides a logger named after the concrete subclass so that
    log output is easy to filter by service.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__qualname__)
