from fastapi import FastAPI

from app.middleware.request_id import RequestIdMiddleware


def apply_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
