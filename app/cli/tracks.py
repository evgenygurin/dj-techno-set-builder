"""Track CRUD CLI commands."""

from __future__ import annotations

import typer
from rich.panel import Panel

from app.cli._context import console, open_session, run_async
from app.cli._formatting import features_panel, print_total, tracks_table

app = typer.Typer(name="tracks", help="Track management commands.", no_args_is_help=True)


@app.command("list")
def list_tracks(
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by title"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
) -> None:
    """List tracks with optional text search."""
    run_async(_list_tracks(search=search, limit=limit, offset=offset))


async def _list_tracks(*, search: str | None, limit: int, offset: int) -> None:
    from app.infrastructure.repositories.tracks import TrackRepository
    from app.services.tracks import TrackService

    async with open_session() as session:
        svc = TrackService(TrackRepository(session))
        result = await svc.list(offset=offset, limit=limit, search=search)

        if not result.items:
            console.print("[dim]No tracks found.[/dim]")
            return

        track_ids = [t.track_id for t in result.items]
        artists_map = await svc.get_track_artists(track_ids)
        table = tracks_table(result.items, artists_map=artists_map)
        console.print(table)
        print_total(result.total, "tracks")


@app.command("get")
def get_track(
    track_id: int = typer.Argument(help="Track ID"),
    features: bool = typer.Option(False, "--features", "-f", help="Show audio features"),
) -> None:
    """Show detailed information about a track."""
    run_async(_get_track(track_id=track_id, show_features=features))


async def _get_track(*, track_id: int, show_features: bool) -> None:
    from app.infrastructure.repositories.audio_features import AudioFeaturesRepository
    from app.infrastructure.repositories.tracks import TrackRepository
    from app.services.features import AudioFeaturesService
    from app.services.tracks import TrackService

    async with open_session() as session:
        track_repo = TrackRepository(session)
        svc = TrackService(track_repo)
        track = await svc.get(track_id)

        artists_map = await svc.get_track_artists([track_id])
        artists = ", ".join(artists_map.get(track_id, []))

        lines = [
            f"[bold cyan]ID:[/bold cyan] {track.track_id}",
            f"[bold]Title:[/bold] {track.title}",
            f"[bold]Artists:[/bold] {artists or '—'}",
            f"[bold]Duration:[/bold]"
            f" {track.duration_ms // 1000 // 60}:{track.duration_ms // 1000 % 60:02d}",
            f"[bold]Status:[/bold] {'active' if track.status == 0 else 'archived'}",
            f"[bold]Created:[/bold] {track.created_at.strftime('%Y-%m-%d %H:%M')}",
        ]
        console.print(Panel("\n".join(lines), title=f"Track {track_id}", border_style="cyan"))

        if show_features:
            features_repo = AudioFeaturesRepository(session)
            feat_svc = AudioFeaturesService(features_repo, track_repo)
            try:
                feat = await feat_svc.get_latest(track_id)
                console.print(features_panel(feat, track_title=track.title))
            except Exception:
                console.print("[dim]No audio features available.[/dim]")


@app.command("create")
def create_track(
    title: str = typer.Argument(help="Track title"),
    duration_ms: int = typer.Argument(help="Duration in milliseconds"),
) -> None:
    """Create a new track."""
    run_async(_create_track(title=title, duration_ms=duration_ms))


async def _create_track(*, title: str, duration_ms: int) -> None:
    from app.infrastructure.repositories.tracks import TrackRepository
    from app.schemas.tracks import TrackCreate
    from app.services.tracks import TrackService

    async with open_session() as session:
        svc = TrackService(TrackRepository(session))
        track = await svc.create(TrackCreate(title=title, duration_ms=duration_ms))
        console.print(f"[green]Created track {track.track_id}:[/green] {track.title}")


@app.command("delete")
def delete_track(
    track_id: int = typer.Argument(help="Track ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a track."""
    if not confirm and not typer.confirm(f"Delete track {track_id}?"):
        raise typer.Abort()
    run_async(_delete_track(track_id=track_id))


async def _delete_track(*, track_id: int) -> None:
    from app.infrastructure.repositories.tracks import TrackRepository
    from app.services.tracks import TrackService

    async with open_session() as session:
        svc = TrackService(TrackRepository(session))
        await svc.delete(track_id)
        console.print(f"[green]Deleted track {track_id}[/green]")


@app.command("search")
def search_tracks(
    query: str = typer.Argument(help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Search tracks by title."""
    run_async(_list_tracks(search=query, limit=limit, offset=0))


@app.command("features")
def show_features(
    track_id: int = typer.Argument(help="Track ID"),
) -> None:
    """Show audio features for a track."""
    run_async(_get_track(track_id=track_id, show_features=True))
