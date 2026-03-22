"""DJ Set CRUD and version management CLI commands."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from app.cli._context import console, open_session, run_async
from app.cli._formatting import print_total, sets_table

app = typer.Typer(name="sets", help="DJ set management commands.", no_args_is_help=True)


@app.command("list")
def list_sets(
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by name"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
) -> None:
    """List DJ sets."""
    run_async(_list_sets(search=search, limit=limit, offset=offset))


async def _list_sets(*, search: str | None, limit: int, offset: int) -> None:
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.services.sets import DjSetService

    async with open_session() as session:
        svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        result = await svc.list(offset=offset, limit=limit, search=search)

        if not result.items:
            console.print("[dim]No sets found.[/dim]")
            return

        table = sets_table(result.items)
        console.print(table)
        print_total(result.total, "sets")


@app.command("get")
def get_set(
    set_id: int = typer.Argument(help="Set ID"),
) -> None:
    """Show detailed information about a DJ set."""
    run_async(_get_set(set_id=set_id))


async def _get_set(*, set_id: int) -> None:
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.services.sets import DjSetService

    async with open_session() as session:
        svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        dj_set = await svc.get(set_id)
        versions = await svc.list_versions(set_id)

        lines = [
            f"[bold cyan]ID:[/bold cyan] {dj_set.set_id}",
            f"[bold]Name:[/bold] {dj_set.name}",
            f"[bold]Description:[/bold] {dj_set.description or '—'}",
            f"[bold]Template:[/bold] {dj_set.template_name or '—'}",
            f"[bold]Source playlist:[/bold] {dj_set.source_playlist_id or '—'}",
            f"[bold]Versions:[/bold] {versions.total}",
            f"[bold]Created:[/bold] {dj_set.created_at.strftime('%Y-%m-%d %H:%M')}",
        ]
        console.print(Panel("\n".join(lines), title=f"DJ Set {set_id}", border_style="cyan"))

        if versions.items:
            table = Table(title="Versions", show_lines=False)
            table.add_column("Version ID", style="cyan", width=12)
            table.add_column("Label", min_width=20)
            table.add_column("Score", justify="right", width=8)
            table.add_column("Created", width=12)

            for v in sorted(versions.items, key=lambda x: x.set_version_id):
                score_str = f"{v.score:.4f}" if v.score is not None else "—"
                created_str = v.created_at.strftime("%Y-%m-%d") if v.created_at else "—"
                table.add_row(
                    str(v.set_version_id),
                    v.version_label or "—",
                    score_str,
                    created_str,
                )
            console.print(table)


@app.command("tracks")
def show_set_tracks(
    set_id: int = typer.Argument(help="Set ID"),
    version_id: int | None = typer.Option(
        None, "--version", "-v", help="Version ID (latest if omitted)"
    ),
    limit: int = typer.Option(100, "--limit", "-n", help="Max tracks"),
) -> None:
    """Show tracks in a set version."""
    run_async(_show_set_tracks(set_id=set_id, version_id=version_id, limit=limit))


async def _show_set_tracks(*, set_id: int, version_id: int | None, limit: int) -> None:
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.repositories.tracks import TrackRepository
    from app.services.features import AudioFeaturesService
    from app.services.sets import DjSetService
    from app.services.tracks import TrackService

    async with open_session() as session:
        set_svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        track_svc = TrackService(TrackRepository(session))
        features_svc = AudioFeaturesService(
            AudioFeaturesRepository(session), TrackRepository(session)
        )

        # Resolve version
        if version_id is None:
            versions = await set_svc.list_versions(set_id)
            if not versions.items:
                console.print("[red]No versions found for this set.[/red]")
                raise typer.Exit(1)
            latest = max(versions.items, key=lambda v: v.set_version_id)
            version_id = latest.set_version_id

        items_list = await set_svc.list_items(version_id, limit=limit)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        if not items:
            console.print("[dim]No tracks in this version.[/dim]")
            return

        table = Table(title=f"Set {set_id} / Version {version_id}", show_lines=False)
        table.add_column("#", width=4)
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="bold", min_width=30)
        table.add_column("BPM", justify="right", width=7)
        table.add_column("Key", justify="right", width=5)
        table.add_column("LUFS", justify="right", width=7)
        table.add_column("Pinned", width=6)

        for item in items:
            title = f"Track {item.track_id}"
            bpm_str = "—"
            key_str = "—"
            lufs_str = "—"

            try:
                track = await track_svc.get(item.track_id)
                title = track.title
            except Exception:
                pass

            try:
                feat = await features_svc.get_latest(item.track_id)
                bpm_str = f"{feat.bpm:.1f}"
                lufs_str = f"{feat.lufs_i:.1f}"
                try:
                    from app.utils.audio.camelot import key_code_to_camelot as _ktc

                    key_str = _ktc(feat.key_code)
                except (ValueError, KeyError):
                    key_str = str(feat.key_code)
            except Exception:
                pass

            pinned = "[green]\u2713[/green]" if item.pinned else ""
            table.add_row(
                str(item.sort_index + 1),
                str(item.track_id),
                title,
                bpm_str,
                key_str,
                lufs_str,
                pinned,
            )

        console.print(table)
        print_total(items_list.total, "tracks")


@app.command("create")
def create_set(
    name: str = typer.Argument(help="Set name"),
    template: str | None = typer.Option(None, "--template", "-t", help="Template name"),
) -> None:
    """Create a new empty DJ set."""
    run_async(_create_set(name=name, template=template))


async def _create_set(*, name: str, template: str | None) -> None:
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.schemas.sets import DjSetCreate
    from app.services.sets import DjSetService

    async with open_session() as session:
        svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        dj_set = await svc.create(DjSetCreate(name=name, template_name=template))
        console.print(f"[green]Created set {dj_set.set_id}:[/green] {dj_set.name}")


@app.command("delete")
def delete_set(
    set_id: int = typer.Argument(help="Set ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a DJ set."""
    if not confirm and not typer.confirm(f"Delete set {set_id}?"):
        raise typer.Abort()
    run_async(_delete_set(set_id=set_id))


async def _delete_set(*, set_id: int) -> None:
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.services.sets import DjSetService

    async with open_session() as session:
        svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        await svc.delete(set_id)
        console.print(f"[green]Deleted set {set_id}[/green]")
