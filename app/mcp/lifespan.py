"""MCP server lifespan — startup/shutdown for observability resources."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastmcp.server.lifespan import lifespan

from app.config import settings

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)


def _init_otel() -> TracerProvider | None:
    """Initialize OpenTelemetry OTLP exporter if endpoint is configured.

    Returns a TracerProvider (possibly the existing one) if OTel is configured,
    or None if the endpoint is not set (no-op).

    Sentry-safe: if a non-default TracerProvider is already registered (e.g. by
    Sentry), a BatchSpanProcessor is added to it rather than replacing it.
    """
    if not settings.otel_endpoint:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "opentelemetry-exporter-otlp not installed; skipping OTel initialisation. "
            "Install the 'observability' extras: uv sync --extra observability"
        )
        return None

    exporter = OTLPSpanExporter(
        endpoint=settings.otel_endpoint,
        insecure=settings.otel_insecure,
    )
    processor = BatchSpanProcessor(exporter)

    existing = trace.get_tracer_provider()
    # ProxyTracerProvider is the default when OTel is not yet initialised.
    # Any other concrete TracerProvider means someone (e.g. Sentry) already
    # set one up — we must add our processor to it, not replace it.
    if isinstance(existing, TracerProvider):
        # Sentry or another SDK already registered a provider — piggyback on it.
        existing.add_span_processor(processor)
        logger.info(
            "OTel: added OTLP BatchSpanProcessor to existing TracerProvider",
            extra={"endpoint": settings.otel_endpoint},
        )
        return existing

    # No concrete provider yet — create and register our own.
    provider = TracerProvider()
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    logger.info(
        "OTel: initialised TracerProvider with OTLP exporter",
        extra={"endpoint": settings.otel_endpoint, "insecure": settings.otel_insecure},
    )
    return provider


def _shutdown_otel(provider: TracerProvider | None) -> None:
    """Flush and shut down the OTel TracerProvider if one was initialised."""
    if provider is None:
        return
    try:
        provider.shutdown()
        logger.info("OTel: TracerProvider shut down")
    except Exception:
        logger.exception("OTel: error during TracerProvider shutdown")


@lifespan
async def mcp_lifespan(server):  # type: ignore[no-untyped-def]
    """Initialize observability resources on MCP server start.

    Yields context dict accessible via ctx.lifespan_context in tools.
    """
    started_at = datetime.now(tz=UTC).isoformat()
    logger.info(
        "MCP server starting",
        extra={"server": getattr(server, "name", "unknown"), "started_at": started_at},
    )
    otel_provider = _init_otel()
    try:
        yield {"started_at": started_at}
    finally:
        _shutdown_otel(otel_provider)
        logger.info(
            "MCP server shutting down",
            extra={"server": getattr(server, "name", "unknown")},
        )
