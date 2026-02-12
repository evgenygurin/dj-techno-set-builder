"""Health endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_200(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_has_request_id_header(client: AsyncClient) -> None:
    resp = await client.get("/health")
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) > 0
