"""MCP server lifespan — startup/shutdown for observability resources."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastmcp.server.lifespan import lifespan

from app.config import settings

logger = logging.getLogger(__name__)


def _init_otel(
    otel_endpoint: str,
    service_name: str,
    insecure: bool = True,
) -> object | None:
    """Initialize OpenTelemetry TracerProvider with OTLP exporter.

    Returns the TracerProvider if initialized, None otherwise.
    FastMCP auto-instruments all tools/resources/prompts — we just need
    to set up the exporter so spans go to the collector.
    """
    if not otel_endpoint:
        logger.debug("OTEL endpoint not set, skipping OpenTelemetry init")
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=otel_endpoint,
            insecure=insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info(
            "OpenTelemetry initialized",
            extra={"endpoint": otel_endpoint, "service": service_name},
        )
        return provider
    except ImportError:
        logger.warning("opentelemetry packages not installed, skipping OTEL init")
        return None


def _shutdown_otel(provider: object | None) -> None:
    """Gracefully shutdown TracerProvider."""
    if provider is not None and hasattr(provider, "shutdown"):
        provider.shutdown()
        logger.info("OpenTelemetry shut down")


@lifespan
async def mcp_lifespan(server):  # type: ignore[no-untyped-def]
    """Initialize observability resources on MCP server start.

    Yields context dict accessible via ctx.lifespan_context in tools.
    """
    started_at = datetime.now(tz=UTC).isoformat()
    otel_provider = _init_otel(
        otel_endpoint=settings.otel_endpoint,
        service_name=settings.otel_service_name,
        insecure=settings.otel_insecure,
    )
    logger.info(
        "MCP server starting",
        extra={"server": getattr(server, "name", "unknown"), "started_at": started_at},
    )
    try:
        yield {
            "started_at": started_at,
            "otel_provider": otel_provider,
        }
    finally:
        _shutdown_otel(otel_provider)
        logger.info(
            "MCP server shutting down",
            extra={"server": getattr(server, "name", "unknown")},
        )
