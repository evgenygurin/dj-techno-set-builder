"""FastMCP server — exposes domain tools for LLM agents.

Run standalone::

    python -m app.mcp_server

Or mount into FastAPI via SSE transport (see FastMCP docs).
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("dj-techno-set-builder")


# ── Example tool (health-check) ─────────────────────────────────
@mcp.tool()
async def health_check() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok"}


# ── Future: register domain tools here ──────────────────────────
# from app.modules.tracks.service import TrackService
#
# @mcp.tool()
# async def search_tracks(query: str) -> list[dict]:
#     svc = TrackService(...)
#     return await svc.search(query)


if __name__ == "__main__":
    mcp.run()
