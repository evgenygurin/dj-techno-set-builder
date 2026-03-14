"""Set builder CLI commands — build, rebuild, score transitions."""

from __future__ import annotations

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.cli._context import console, err_console, open_session, run_async
from app.cli._formatting import build_result_panel, transitions_table

app = typer.Typer(name="build", help="Set builder commands (GA, scoring).", no_args_is_help=True)


@app.command("set")
def build_set(
    playlist_id: int = typer.Argument(help="Source playlist ID"),
    name: str = typer.Argument(help="Name for the new DJ set"),
    template: str | None = typer.Option(
        None, "--template", "-t", help="Template name (e.g. classic_60)"
    ),
    energy_arc: str = typer.Option(
        "classic",
        "--arc",
        "-a",
        help="Energy arc: classic, progressive, roller, wave",
    ),
    exclude: list[int] | None = typer.Option(None, "--exclude", "-x", help="Track IDs to exclude"),
    generations: int = typer.Option(200, "--generations", "-g", help="GA generations"),
    population: int = typer.Option(100, "--population", "-p", help="GA population size"),
) -> None:
    """Build a DJ set from a playlist using genetic algorithm optimization.

    Creates a new DJ set, runs the GA optimizer to find the best track
    ordering, and displays the results.
    """
    run_async(
        _build_set(
            playlist_id=playlist_id,
            name=name,
            template=template,
            energy_arc=energy_arc,
            exclude=exclude,
            generations=generations,
            population=population,
        )
    )


async def _build_set(
    *,
    playlist_id: int,
    name: str,
    template: str | None,
    energy_arc: str,
    exclude: list[int] | None,
    generations: int,
    population: int,
) -> None:
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.playlists import DjPlaylistItemRepository
    from app.repositories.sections import SectionsRepository
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.schemas.set_generation import SetGenerationRequest
    from app.schemas.sets import DjSetCreate
    from app.services.set_generation import SetGenerationService
    from app.services.sets import DjSetService

    async with open_session() as session:
        set_svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        gen_svc = SetGenerationService(
            set_repo=DjSetRepository(session),
            version_repo=DjSetVersionRepository(session),
            item_repo=DjSetItemRepository(session),
            features_repo=AudioFeaturesRepository(session),
            sections_repo=SectionsRepository(session),
            playlist_repo=DjPlaylistItemRepository(session),
        )

        # Create DJ set
        dj_set = await set_svc.create(
            DjSetCreate(
                name=name,
                source_playlist_id=playlist_id,
                template_name=template,
            )
        )
        console.print(f"[cyan]Created set {dj_set.set_id}:[/cyan] {name}")

        # Run GA
        request = SetGenerationRequest(
            energy_arc_type=energy_arc,
            playlist_id=playlist_id,
            template_name=template,
            exclude_track_ids=exclude,
            generations=generations,
            population_size=population,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Running genetic algorithm...", total=None)
            gen_result = await gen_svc.generate(dj_set.set_id, request)

        avg_score = 0.0
        if gen_result.transition_scores:
            avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

        console.print(
            build_result_panel(
                set_id=dj_set.set_id,
                version_id=gen_result.set_version_id,
                track_count=len(gen_result.track_ids),
                total_score=gen_result.score,
                avg_transition=avg_score,
            )
        )
        console.print(
            f"\n[dim]Energy arc: {gen_result.energy_arc_score:.4f}  "
            f"BPM smoothness: {gen_result.bpm_smoothness_score:.4f}[/dim]"
        )
        console.print(f"[dim]View tracks: dj sets tracks {dj_set.set_id}[/dim]")


@app.command("rebuild")
def rebuild_set(
    set_id: int = typer.Argument(help="Set ID to rebuild"),
    pinned: list[int] | None = typer.Option(None, "--pin", help="Track IDs to keep pinned"),
    exclude: list[int] | None = typer.Option(None, "--exclude", "-x", help="Track IDs to exclude"),
) -> None:
    """Rebuild a set with pinned/excluded constraints.

    Creates a new version of an existing set. Pinned tracks stay fixed,
    excluded tracks are replaced from the full library.
    """
    run_async(_rebuild_set(set_id=set_id, pinned=pinned, exclude=exclude))


async def _rebuild_set(
    *,
    set_id: int,
    pinned: list[int] | None,
    exclude: list[int] | None,
) -> None:
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.playlists import DjPlaylistItemRepository
    from app.repositories.sections import SectionsRepository
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.schemas.set_generation import SetGenerationRequest
    from app.services.set_generation import SetGenerationService
    from app.services.sets import DjSetService

    async with open_session() as session:
        set_svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        gen_svc = SetGenerationService(
            set_repo=DjSetRepository(session),
            version_repo=DjSetVersionRepository(session),
            item_repo=DjSetItemRepository(session),
            features_repo=AudioFeaturesRepository(session),
            sections_repo=SectionsRepository(session),
            playlist_repo=DjPlaylistItemRepository(session),
        )

        dj_set = await set_svc.get(set_id)

        # Get latest version info for track count
        versions = await set_svc.list_versions(set_id)
        if not versions.items:
            err_console.print("[red]No versions found for this set.[/red]")
            raise typer.Exit(1)
        latest = max(versions.items, key=lambda v: v.set_version_id)
        items_list = await set_svc.list_items(latest.set_version_id, limit=500)
        target_count = items_list.total

        # Read pinned from version if not provided
        if pinned is None:
            pinned = [item.track_id for item in items_list.items if item.pinned]

        excluded_set = set(exclude or [])
        playlist_id = None if excluded_set else dj_set.source_playlist_id

        console.print(
            f"[cyan]Rebuilding set {set_id}[/cyan] "
            f"({len(pinned)} pinned, {len(excluded_set)} excluded)"
        )

        request = SetGenerationRequest(
            playlist_id=playlist_id,
            template_name=dj_set.template_name,
            pinned_track_ids=pinned if pinned else None,
            exclude_track_ids=list(excluded_set) if excluded_set else None,
            track_count=target_count,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Running genetic algorithm...", total=None)
            gen_result = await gen_svc.generate(set_id, request)

        avg_score = 0.0
        if gen_result.transition_scores:
            avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

        console.print(
            build_result_panel(
                set_id=set_id,
                version_id=gen_result.set_version_id,
                track_count=len(gen_result.track_ids),
                total_score=gen_result.score,
                avg_transition=avg_score,
            )
        )


@app.command("score")
def score_transitions(
    set_id: int = typer.Argument(help="Set ID"),
    version_id: int | None = typer.Option(
        None, "--version", "-v", help="Version ID (latest if omitted)"
    ),
) -> None:
    """Score all transitions in a set version.

    Evaluates every adjacent track pair and shows the breakdown.
    """
    run_async(_score_transitions(set_id=set_id, version_id=version_id))


async def _score_transitions(*, set_id: int, version_id: int | None) -> None:
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.repositories.tracks import TrackRepository
    from app.services.sets import DjSetService
    from app.services.tracks import TrackService
    from app.services.transition_scoring_unified import UnifiedTransitionScoringService

    async with open_session() as session:
        set_svc = DjSetService(
            DjSetRepository(session),
            DjSetVersionRepository(session),
            DjSetItemRepository(session),
        )
        track_svc = TrackService(TrackRepository(session))
        unified_svc = UnifiedTransitionScoringService(session)

        await set_svc.get(set_id)

        # Resolve version
        if version_id is None:
            versions = await set_svc.list_versions(set_id)
            if not versions.items:
                err_console.print("[red]No versions found.[/red]")
                raise typer.Exit(1)
            latest = max(versions.items, key=lambda v: v.set_version_id)
            version_id = latest.set_version_id

        items_list = await set_svc.list_items(version_id, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        if len(items) < 2:
            console.print("[dim]Need at least 2 tracks to score transitions.[/dim]")
            return

        scores_data: list[dict[str, object]] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Scoring transitions...", total=len(items) - 1)

            for i in range(len(items) - 1):
                from_id = items[i].track_id
                to_id = items[i + 1].track_id

                from_title = f"Track {from_id}"
                to_title = f"Track {to_id}"
                try:
                    t = await track_svc.get(from_id)
                    from_title = t.title
                except Exception:
                    pass
                try:
                    t = await track_svc.get(to_id)
                    to_title = t.title
                except Exception:
                    pass

                try:
                    components = await unified_svc.score_components_by_ids(from_id, to_id)
                    scores_data.append(
                        {
                            "from_title": from_title,
                            "to_title": to_title,
                            "total": components["total"],
                            "bpm": components["bpm"],
                            "harmonic": components["harmonic"],
                            "energy": components["energy"],
                            "recommended_type": _recommend_type(components),
                        }
                    )
                except Exception:
                    scores_data.append(
                        {
                            "from_title": from_title,
                            "to_title": to_title,
                            "total": 0.0,
                            "bpm": 0.0,
                            "harmonic": 0.0,
                            "energy": 0.0,
                            "recommended_type": "—",
                        }
                    )

                progress.advance(task)

        table = transitions_table(scores_data, title=f"Transitions — Set {set_id} v{version_id}")
        console.print(table)

        # Summary
        scored = [s for s in scores_data if s["total"] and float(str(s["total"])) > 0]
        if scored:
            totals = [float(str(s["total"])) for s in scored]
            avg = sum(totals) / len(totals)
            weak = sum(1 for t in totals if t < 0.85)
            hard = sum(1 for s in scores_data if float(str(s["total"])) == 0.0)
            console.print(
                f"\n[bold]Avg:[/bold] {avg:.3f}  "
                f"[bold]Weak (<0.85):[/bold] {weak}  "
                f"[bold]Hard conflicts:[/bold] {hard}"
            )


def _recommend_type(components: dict[str, float]) -> str:
    """Recommend a transition type based on component scores."""
    bpm = components.get("bpm", 0)
    harmonic = components.get("harmonic", 0)
    energy = components.get("energy", 0)

    if bpm >= 0.95 and harmonic >= 0.85:
        return "blend"
    if bpm >= 0.9:
        return "eq"
    if energy >= 0.8:
        return "drum_swap"
    return "drum_cut"
