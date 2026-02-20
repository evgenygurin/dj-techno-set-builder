"""Tests for DJ skills provider."""

from __future__ import annotations

from fastmcp import Client, FastMCP


async def test_skills_provider_lists_skills(gateway_mcp: FastMCP):
    """Gateway exposes DJ skills as resources."""
    async with Client(gateway_mcp) as client:
        resources = await client.list_resources()
        skill_uris = [str(r.uri) for r in resources if "skill://" in str(r.uri)]
        assert len(skill_uris) >= 3  # At least our 3 skills


async def test_skill_readable(gateway_mcp: FastMCP):
    """Skill SKILL.md is readable via resource URI."""
    async with Client(gateway_mcp) as client:
        resources = await client.list_resources()
        # Find the expand-playlist skill
        expand_uris = [
            str(r.uri)
            for r in resources
            if "expand-playlist" in str(r.uri) and "SKILL.md" in str(r.uri)
        ]
        assert len(expand_uris) > 0, f"No expand-playlist skill found in {resources}"

        content = await client.read_resource(expand_uris[0])
        text = content[0].text if hasattr(content[0], "text") else str(content[0])
        assert "Expand Playlist" in text
        assert "dj_get_playlist" in text
