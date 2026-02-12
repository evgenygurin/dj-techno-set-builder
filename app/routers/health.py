from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {"status": "ok"}
