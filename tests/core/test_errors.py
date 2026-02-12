"""Error handler tests."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.handlers import app_error_handler, unhandled_error_handler


def _make_app() -> FastAPI:
    """Minimal app that raises specific errors."""
    test_app = FastAPI()
    test_app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    test_app.add_exception_handler(Exception, unhandled_error_handler)  # type: ignore[arg-type]

    @test_app.get("/not-found")
    async def _raise_not_found():
        raise NotFoundError("track not found", details={"id": 42})

    @test_app.get("/conflict")
    async def _raise_conflict():
        raise ConflictError("duplicate track")

    @test_app.get("/boom")
    async def _raise_unhandled():
        msg = "unexpected"
        raise RuntimeError(msg)

    return test_app


async def test_app_error_returns_json_format() -> None:
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/not-found")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "track not found"
    assert body["error"]["details"] == {"id": 42}


async def test_conflict_error() -> None:
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/conflict")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_unhandled_error_returns_500() -> None:
    app = _make_app()
    # raise_app_exceptions=False lets us inspect the 500 response
    # instead of httpx re-raising the exception from the ASGI app.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    # Must NOT leak the actual error message
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "unexpected" not in body["error"]["message"]
