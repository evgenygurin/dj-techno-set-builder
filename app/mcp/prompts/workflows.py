"""Workflow recipe prompts for the DJ MCP server.

Each prompt is a multi-step recipe that tells the AI which tools to call
in order, guiding it through a complete DJ workflow.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.prompts import Message


def register_prompts(mcp: FastMCP) -> None:
    """Register workflow recipe prompts on the MCP server."""

    @mcp.prompt
    def expand_playlist(
        playlist_name: str,
        count: int = 20,
        style: str = "dark techno",
    ) -> list[Message]:
        """Expand an existing playlist with similar tracks and build an optimized DJ set."""
        return [
            Message(
                role="user",
                content=(
                    f"I need to expand the playlist '{playlist_name}' with {count} "
                    f"similar tracks in the '{style}' style, then build an optimal "
                    "DJ set.\n\n"
                    "Please follow these steps:\n"
                    "1. Check the playlist's audio profile using the REST API "
                    "or resources (BPM range, keys, energy levels).\n"
                    f"2. Use `dj_find_similar_tracks` to search for {count} "
                    f"matching tracks that fit the '{style}' style.\n"
                    "3. Use `dj_build_set` to optimize the track order for "
                    "smooth transitions.\n\n"
                    "Let's start with step 1."
                ),
            ),
        ]

    @mcp.prompt
    def build_set_from_scratch(
        genre: str,
        duration_minutes: int = 60,
        energy_arc: str = "classic",
    ) -> list[Message]:
        """Build a complete DJ set from scratch given a genre and duration."""
        return [
            Message(
                role="user",
                content=(
                    f"I want to build a {duration_minutes}-minute DJ set in the "
                    f"'{genre}' genre with a '{energy_arc}' energy arc, starting "
                    "from zero.\n\n"
                    "Please follow these steps:\n"
                    "1. Use `ym_search_tracks` to search Yandex Music for tracks "
                    f"matching the '{genre}' genre.\n"
                    "2. Use `dj_download_tracks` to download found tracks, "
                    "then add them to the local database.\n"
                    "3. Use `dj_find_similar_tracks` to expand the selection with "
                    "similar tracks that fit the vibe.\n"
                    "4. Use `dj_build_set` to optimize the track order with "
                    f"energy_arc='{energy_arc}'.\n\n"
                    "Let's start with step 1."
                ),
            ),
        ]

    @mcp.prompt
    def improve_set(
        set_id: str,
        version_id: str,
        feedback: str = "",
    ) -> list[Message]:
        """Improve an existing DJ set based on transition scores and feedback."""
        feedback_line = ""
        if feedback:
            feedback_line = f"\n\nUser feedback: {feedback}"

        return [
            Message(
                role="user",
                content=(
                    f"I want to improve DJ set {set_id} (version {version_id})."
                    f"{feedback_line}\n\n"
                    "Please follow these steps:\n"
                    f"1. Use `dj_score_transitions` with set_id={set_id} and "
                    f"version_id={version_id} to evaluate the current transitions "
                    "and identify weak points.\n"
                    f"2. Use `dj_rebuild_set` with set_id={set_id} to rebuild "
                    "the set with pinned tracks preserved and weak ones excluded.\n"
                    "3. Use `dj_score_transitions` again on the new version to "
                    "compare and verify the improvements.\n\n"
                    "Let's start with step 1."
                ),
            ),
        ]
