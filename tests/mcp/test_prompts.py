"""Tests for MCP prompt templates."""

from __future__ import annotations


async def test_prompts_are_listed():
    """All three workflow prompts should be registered."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    prompts = await mcp.list_prompts()
    prompt_names = {p.name for p in prompts}
    assert "expand_playlist" in prompt_names
    assert "build_set_from_scratch" in prompt_names
    assert "improve_set" in prompt_names


async def test_expand_playlist_arguments():
    """expand_playlist should accept playlist_name (required), count, style."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    prompts = await mcp.list_prompts()
    prompt = next(p for p in prompts if p.name == "expand_playlist")

    arg_names = {a.name for a in prompt.arguments}
    assert "playlist_name" in arg_names
    assert "count" in arg_names
    assert "style" in arg_names

    # playlist_name is required, others are optional
    required = {a.name for a in prompt.arguments if a.required}
    assert "playlist_name" in required
    assert "count" not in required
    assert "style" not in required


async def test_build_set_from_scratch_arguments():
    """build_set_from_scratch should accept genre (required), duration_minutes, energy_arc."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    prompts = await mcp.list_prompts()
    prompt = next(p for p in prompts if p.name == "build_set_from_scratch")

    arg_names = {a.name for a in prompt.arguments}
    assert "genre" in arg_names
    assert "duration_minutes" in arg_names
    assert "energy_arc" in arg_names

    required = {a.name for a in prompt.arguments if a.required}
    assert "genre" in required


async def test_improve_set_arguments():
    """improve_set should accept set_id, version_id (required), feedback (optional)."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    prompts = await mcp.list_prompts()
    prompt = next(p for p in prompts if p.name == "improve_set")

    arg_names = {a.name for a in prompt.arguments}
    assert "set_id" in arg_names
    assert "version_id" in arg_names
    assert "feedback" in arg_names

    required = {a.name for a in prompt.arguments if a.required}
    assert "set_id" in required
    assert "version_id" in required
    assert "feedback" not in required


async def test_prompts_appear_through_gateway_with_prefix():
    """Prompts should be available via gateway with dj_ namespace prefix."""
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    prompts = await mcp.list_prompts()
    prompt_names = {p.name for p in prompts}
    assert "dj_expand_playlist" in prompt_names
    assert "dj_build_set_from_scratch" in prompt_names
    assert "dj_improve_set" in prompt_names


async def test_expand_playlist_renders_messages():
    """expand_playlist prompt should render a list with a user message."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    result = await mcp.render_prompt(
        "expand_playlist",
        arguments={"playlist_name": "My Mix"},
    )
    assert len(result.messages) >= 1
    first_msg = result.messages[0]
    assert first_msg.role == "user"


async def test_build_set_from_scratch_renders_messages():
    """build_set_from_scratch prompt should render a user message."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    result = await mcp.render_prompt(
        "build_set_from_scratch",
        arguments={"genre": "dark techno"},
    )
    assert len(result.messages) >= 1
    assert result.messages[0].role == "user"


async def test_improve_set_renders_messages():
    """improve_set prompt should render a user message."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    result = await mcp.render_prompt(
        "improve_set",
        arguments={"set_id": "1", "version_id": "2"},
    )
    assert len(result.messages) >= 1
    assert result.messages[0].role == "user"
