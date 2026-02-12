"""Metrics / monitoring scaffold.

Provides a ``MetricsBackend`` protocol and a no-op default
so that the rest of the codebase can emit metrics without
caring whether Prometheus / Datadog / OTEL is wired up yet.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsBackend(Protocol):
    """Minimal metrics interface."""

    def increment(
        self, name: str, value: float = 1, *, tags: dict[str, str] | None = None
    ) -> None: ...
    def timing(
        self, name: str, value_ms: float, *, tags: dict[str, str] | None = None
    ) -> None: ...


class NoopMetrics:
    """Drop-in metrics backend that does nothing."""

    def increment(
        self, name: str, value: float = 1, *, tags: dict[str, str] | None = None
    ) -> None:
        pass

    def timing(
        self, name: str, value_ms: float, *, tags: dict[str, str] | None = None
    ) -> None:
        pass


_metrics: MetricsBackend = NoopMetrics()


def get_metrics() -> MetricsBackend:
    """Return the currently configured metrics backend."""
    return _metrics


def configure_metrics(backend: MetricsBackend) -> None:
    """Swap the global metrics backend (call once at startup)."""
    global _metrics  # noqa: PLW0603
    _metrics = backend
