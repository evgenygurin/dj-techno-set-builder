"""DJ Techno Set Builder CLI — main entry point.

Usage:
    dj tracks list
    dj tracks get 42 --features
    dj playlists list
    dj sets list
    dj sets tracks 5
    dj build set 3 "Peak Hour Mix" --template peak_hour_60
    dj build score 5
    dj deliver set 5
    dj analysis classify
    dj analysis gaps --template classic_60
    dj info
"""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from app.cli._context import console, run_async

app = typer.Typer(
    name="dj",
    help="DJ Techno Set Builder — CLI for track management, set building, and delivery.",
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)

# ── Register sub-apps ────────────────────────────────────────────────────────

from app.cli.analysis import app as analysis_app  # noqa: E402
from app.cli.delivery import app as delivery_app  # noqa: E402
from app.cli.playlists import app as playlists_app  # noqa: E402
from app.cli.setbuilder import app as setbuilder_app  # noqa: E402
from app.cli.sets import app as sets_app  # noqa: E402
from app.cli.tracks import app as tracks_app  # noqa: E402

app.add_typer(tracks_app, name="tracks")
app.add_typer(playlists_app, name="playlists")
app.add_typer(sets_app, name="sets")
app.add_typer(setbuilder_app, name="build")
app.add_typer(delivery_app, name="deliver")
app.add_typer(analysis_app, name="analysis")


# ── Top-level commands ───────────────────────────────────────────────────────


@app.command()
def info() -> None:
    """Show library statistics and configuration."""
    run_async(_info())


async def _info() -> None:
    from app.cli._context import open_session
    from app.core.config import settings

    lines = [
        f"[bold]App:[/bold] {settings.app_name}",
        f"[bold]Database:[/bold] {settings.database_url}",
        f"[bold]Library:[/bold] {settings.dj_library_path}",
        f"[bold]YM configured:[/bold] {'yes' if settings.yandex_music_token else 'no'}",
    ]

    async with open_session() as session:
        from sqlalchemy import text

        # Quick stats
        stats: list[tuple[str, int]] = []
        for table_name in ["tracks", "dj_playlists", "dj_sets", "track_audio_features_computed"]:
            try:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar() or 0
                stats.append((table_name, count))
            except Exception:
                stats.append((table_name, 0))

    stat_table = Table(show_header=False, box=None, padding=(0, 2))
    stat_table.add_column("Entity", style="bold")
    stat_table.add_column("Count", justify="right", style="cyan")

    label_map = {
        "tracks": "Tracks",
        "dj_playlists": "Playlists",
        "dj_sets": "DJ Sets",
        "track_audio_features_computed": "Analyzed tracks",
    }
    for table_name, count in stats:
        stat_table.add_row(label_map.get(table_name, table_name), str(count))

    lines.append("")

    console.print(Panel("\n".join(lines), title="DJ Techno Set Builder", border_style="cyan"))
    console.print(stat_table)


@app.command()
def version() -> None:
    """Show CLI version."""
    console.print("[bold]dj-techno-set-builder[/bold] v0.1.0")


if __name__ == "__main__":
    app()
