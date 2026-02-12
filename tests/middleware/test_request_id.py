"""Request-ID middleware tests."""

from __future__ import annotations

from httpx import AsyncClient


async def test_request_id_generated(client: AsyncClient) -> None:
    """When no X-Request-ID header is sent, one is generated."""
    resp = await client.get("/health")
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) == 32  # uuid4().hex


async def test_request_id_preserved_from_header(client: AsyncClient) -> None:
    """When X-Request-ID is sent, it is echoed back."""
    custom_rid = "my-custom-request-id-12345"
    resp = await client.get("/health", headers={"X-Request-ID": custom_rid})
    assert resp.headers["X-Request-ID"] == custom_rid
