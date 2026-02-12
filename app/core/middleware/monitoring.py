"""Metrics-emitting middleware."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.monitoring import get_metrics


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Emits ``http.requests`` counter and ``http.latency`` timing per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        tags = {
            "method": request.method,
            "path": request.url.path,
            "status": str(response.status_code),
        }
        metrics = get_metrics()
        metrics.increment("http.requests", tags=tags)
        metrics.timing("http.latency", elapsed_ms, tags=tags)
        return response
