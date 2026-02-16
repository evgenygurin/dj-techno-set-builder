"""Tests for import_playlist MCP tool."""


async def test_import_playlist_accepts_download_files_parameter(workflow_mcp):
    """import_playlist accepts download_files parameter without error."""
    tools = {t.name: t for t in await workflow_mcp.list_tools()}
    tool = tools["import_playlist"]

    # Verify parameter exists in schema
    params = tool.parameters
    assert "download_files" in params["properties"]
    assert params["properties"]["download_files"]["type"] == "boolean"
    assert params["properties"]["download_files"]["default"] is False
