"""Pluggable module router & registry.

Each domain module exposes a ``ModuleRouter`` subclass.
``ModuleRegistry`` collects them and wires into the FastAPI app
during startup.

Usage in a future module::

    class TracksRouter(ModuleRouter):
        prefix = "/tracks"
        tags = ["tracks"]

        def create_router(self) -> APIRouter:
            router = APIRouter()
            ...
            return router
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from fastapi import APIRouter, FastAPI


class ModuleRouter(ABC):
    """Interface every domain module must implement."""

    prefix: str = ""
    tags: ClassVar[list[str]] = []

    @abstractmethod
    def create_router(self) -> APIRouter:
        """Build and return the APIRouter for this module."""

    def register(self, app: FastAPI) -> None:
        """Attach the module router to the app."""
        router = self.create_router()
        app.include_router(router, prefix=self.prefix, tags=list(self.tags))


class ModuleRegistry:
    """Collects ``ModuleRouter`` instances and wires them at startup."""

    def __init__(self) -> None:
        self._modules: list[ModuleRouter] = []

    def add(self, module: ModuleRouter) -> None:
        self._modules.append(module)

    def wire(self, app: FastAPI) -> None:
        for module in self._modules:
            module.register(app)
