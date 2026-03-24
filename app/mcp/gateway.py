"""MCP Gateway — single DJ Set Builder MCP server."""

from __future__ import annotations

import logging
from pathlib import Path

from fastmcp import FastMCP

from app.config import settings
from app.mcp.lifespan import mcp_lifespan
from app.mcp.observability import apply_observability
from app.mcp.tools import create_workflow_mcp

logger = logging.getLogger(__name__)


def create_dj_mcp() -> FastMCP:
    """Create the MCP server with all DJ workflow tools.

    Applies observability middleware and lifespan management.
    Configures AnthropicSamplingHandler as fallback when ANTHROPIC_API_KEY is set.
    Exposes DJ workflow skills as MCP resources via SkillsDirectoryProvider.
    Adds PromptsAsTools and ResourcesAsTools transforms so that tool-only
    clients can still access prompts and resources.
    """
    sampling_handler = None
    if settings.anthropic_api_key:
        try:
            from fastmcp.client.sampling.handlers.anthropic import (
                AnthropicSamplingHandler,
            )

            sampling_handler = AnthropicSamplingHandler(
                default_model=settings.sampling_model,
            )
        except ImportError:
            logger.warning(
                "anthropic_api_key set but fastmcp[anthropic] not installed; "
                "sampling fallback disabled"
            )

    gateway = FastMCP(
        "DJ Set Builder",
        lifespan=mcp_lifespan,
        list_page_size=settings.mcp_page_size,
        sampling_handler=sampling_handler,
        sampling_handler_behavior="fallback",
    )

    # Expose DJ workflow skills as MCP resources
    try:
        from fastmcp.server.providers.skills import SkillsDirectoryProvider

        skills_dir = Path(__file__).parent / "skills"
        if skills_dir.exists():
            gateway.add_provider(
                SkillsDirectoryProvider(
                    roots=skills_dir,
                    supporting_files="template",
                )
            )
    except ImportError:
        logger.debug("SkillsDirectoryProvider not available; skipping skills")

    wf = create_workflow_mcp()
    gateway.mount(wf, namespace="dj")

    apply_observability(gateway, settings)

    try:
        from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools

        gateway.add_transform(PromptsAsTools(gateway))
        gateway.add_transform(ResourcesAsTools(gateway))
    except (ImportError, TypeError, AttributeError):
        logger.debug("PromptsAsTools/ResourcesAsTools not available; skipping transforms")

    return gateway
