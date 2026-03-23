"""Playlist CRUD CLI commands."""

from __future__ import annotations

import typer
from rich.panel import Panel

from app.cli._context import console, open_session, run_async
from app.cli._formatting import playlists_table, print_total, tracks_table

app = typer.Typer(name="playlists", help="Playlist management commands.", no_args_is_help=True)


@app.command("list")
def list_playlists(
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by name"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
) -> None:
    """List playlists with optional text search."""
    run_async(_list_playlists(search=search, limit=limit, offset=offset))


async def _list_playlists(*, search: str | None, limit: int, offset: int) -> None:
    from app.infrastructure.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
    from app.services.playlists import DjPlaylistService

    async with open_session() as session:
        svc = DjPlaylistService(DjPlaylistRepository(session), DjPlaylistItemRepository(session))
        result = await svc.list(offset=offset, limit=limit, search=search)

        if not result.items:
            console.print("[dim]No playlists found.[/dim]")
            return

        table = playlists_table(result.items)
        console.print(table)
        print_total(result.total, "playlists")


@app.command("get")
def get_playlist(
    playlist_id: int = typer.Argument(help="Playlist ID"),
    show_tracks: bool = typer.Option(False, "--tracks", "-t", help="Show playlist tracks"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max tracks to show"),
) -> None:
    """Show playlist details."""
    run_async(_get_playlist(playlist_id=playlist_id, show_tracks=show_tracks, limit=limit))


async def _get_playlist(*, playlist_id: int, show_tracks: bool, limit: int) -> None:
    from app.infrastructure.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
    from app.infrastructure.repositories.tracks import TrackRepository
    from app.services.playlists import DjPlaylistService
    from app.services.tracks import TrackService

    async with open_session() as session:
        svc = DjPlaylistService(DjPlaylistRepository(session), DjPlaylistItemRepository(session))
        playlist = await svc.get(playlist_id)

        lines = [
            f"[bold cyan]ID:[/bold cyan] {playlist.playlist_id}",
            f"[bold]Name:[/bold] {playlist.name}",
            f"[bold]Source:[/bold] {playlist.source_of_truth}",
            f"[bold]Created:[/bold] {playlist.created_at.strftime('%Y-%m-%d %H:%M')}",
        ]
        console.print(
            Panel("\n".join(lines), title=f"Playlist {playlist_id}", border_style="cyan")
        )

        if show_tracks:
            items = await svc.list_items(playlist_id, limit=limit)
            if not items.items:
                console.print("[dim]Playlist is empty.[/dim]")
                return

            track_repo = TrackRepository(session)
            track_svc = TrackService(track_repo)
            track_ids = [item.track_id for item in items.items]

            # Fetch actual track objects for display
            track_objects = []
            for tid in track_ids:
                try:
                    t = await track_svc.get(tid)
                    track_objects.append(t)
                except Exception:
                    pass

            artists_map = await track_svc.get_track_artists(track_ids)
            table = tracks_table(
                track_objects,
                title=f"Tracks in '{playlist.name}'",
                artists_map=artists_map,
            )
            console.print(table)
            print_total(items.total, "tracks")


@app.command("create")
def create_playlist(
    name: str = typer.Argument(help="Playlist name"),
) -> None:
    """Create a new playlist."""
    run_async(_create_playlist(name=name))


async def _create_playlist(*, name: str) -> None:
    from app.infrastructure.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
    from app.schemas.playlists import DjPlaylistCreate
    from app.services.playlists import DjPlaylistService

    async with open_session() as session:
        svc = DjPlaylistService(DjPlaylistRepository(session), DjPlaylistItemRepository(session))
        playlist = await svc.create(DjPlaylistCreate(name=name))
        console.print(f"[green]Created playlist {playlist.playlist_id}:[/green] {playlist.name}")


@app.command("delete")
def delete_playlist(
    playlist_id: int = typer.Argument(help="Playlist ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a playlist."""
    if not confirm and not typer.confirm(f"Delete playlist {playlist_id}?"):
        raise typer.Abort()
    run_async(_delete_playlist(playlist_id=playlist_id))


async def _delete_playlist(*, playlist_id: int) -> None:
    from app.infrastructure.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
    from app.services.playlists import DjPlaylistService

    async with open_session() as session:
        svc = DjPlaylistService(DjPlaylistRepository(session), DjPlaylistItemRepository(session))
        await svc.delete(playlist_id)
        console.print(f"[green]Deleted playlist {playlist_id}[/green]")
