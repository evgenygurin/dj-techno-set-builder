"""Audio analysis and curation CLI commands."""

from __future__ import annotations

import contextlib

import typer
from rich.table import Table

from app.cli._context import console, open_session, run_async
from app.cli._formatting import features_panel

app = typer.Typer(
    name="analysis",
    help="Audio analysis and curation commands.",
    no_args_is_help=True,
)


@app.command("features")
def list_features(
    limit: int = typer.Option(50, "--limit", "-n", help="Max results"),
) -> None:
    """List all tracks with computed audio features."""
    run_async(_list_features(limit=limit))


async def _list_features(*, limit: int) -> None:
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.tracks import TrackRepository
    from app.services.features import AudioFeaturesService
    from app.utils.audio.camelot import key_code_to_camelot

    async with open_session() as session:
        svc = AudioFeaturesService(AudioFeaturesRepository(session), TrackRepository(session))
        features = await svc.list_all()

        if not features:
            console.print("[dim]No features found.[/dim]")
            return

        table = Table(title="Tracks with Audio Features", show_lines=False)
        table.add_column("Track ID", style="cyan", width=8)
        table.add_column("BPM", justify="right", width=7)
        table.add_column("Key", justify="right", width=5)
        table.add_column("LUFS", justify="right", width=7)
        table.add_column("Energy", justify="right", width=8)
        table.add_column("Onset", justify="right", width=7)
        table.add_column("Kick", justify="right", width=7)

        for f in features[:limit]:
            key_str = "—"
            with contextlib.suppress(ValueError, KeyError):
                key_str = key_code_to_camelot(f.key_code)

            table.add_row(
                str(f.track_id),
                f"{f.bpm:.1f}",
                key_str,
                f"{f.lufs_i:.1f}",
                f"{f.energy_mean:.3f}",
                f"{f.onset_rate_mean:.2f}" if f.onset_rate_mean else "—",
                f"{f.kick_prominence:.2f}" if f.kick_prominence else "—",
            )

        console.print(table)
        console.print(f"[dim]Showing {min(limit, len(features))} of {len(features)} tracks[/dim]")


@app.command("classify")
def classify_tracks(
    limit: int = typer.Option(50, "--limit", "-n", help="Max tracks to classify"),
) -> None:
    """Classify all tracks by mood (15 techno subgenres)."""
    run_async(_classify_tracks(limit=limit))


async def _classify_tracks(*, limit: int) -> None:
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.services.set_curation import SetCurationService

    async with open_session() as session:
        features_repo = AudioFeaturesRepository(session)
        features = await features_repo.list_all()

        if not features:
            console.print("[dim]No features found.[/dim]")
            return

        curation = SetCurationService()
        classified = curation.classify_features(features[:limit])
        distribution = curation.mood_distribution(classified)

        # Distribution table
        dist_table = Table(title="Mood Distribution", show_lines=False)
        dist_table.add_column("Mood", style="bold", min_width=20)
        dist_table.add_column("Count", justify="right", width=7)
        dist_table.add_column("Bar", min_width=30)

        max_count = max(distribution.values()) if distribution else 1
        for mood, count in sorted(distribution.items(), key=lambda x: x[0].intensity):
            bar_len = int(30 * count / max_count) if max_count > 0 else 0
            bar = "\u2588" * bar_len
            dist_table.add_row(mood.value, str(count), f"[cyan]{bar}[/cyan]")

        console.print(dist_table)
        console.print(f"[dim]Classified {len(classified)} tracks[/dim]")


@app.command("gaps")
def analyze_gaps(
    template: str = typer.Option(
        "classic_60", "--template", "-t", help="Template to analyze against"
    ),
) -> None:
    """Analyze library gaps relative to a set template."""
    run_async(_analyze_gaps(template=template))


async def _analyze_gaps(*, template: str) -> None:
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.services.set_curation import SetCurationService
    from app.utils.audio.set_templates import TemplateName, get_template

    async with open_session() as session:
        features_repo = AudioFeaturesRepository(session)
        features = await features_repo.list_all()

        if not features:
            console.print("[dim]No features found.[/dim]")
            return

        curation = SetCurationService()
        classified = curation.classify_features(features)
        distribution = curation.mood_distribution(classified)

        tmpl = get_template(TemplateName(template))

        # Count slots by mood
        slot_needs: dict[str, int] = {}
        for slot in tmpl.slots:
            mood_name = slot.mood.value
            slot_needs[mood_name] = slot_needs.get(mood_name, 0) + 1

        table = Table(title=f"Library Gaps — {template}", show_lines=False)
        table.add_column("Mood", style="bold", min_width=20)
        table.add_column("Need", justify="right", width=6)
        table.add_column("Have", justify="right", width=6)
        table.add_column("Gap", justify="right", width=6)
        table.add_column("Status", width=10)

        for mood_name, needed in sorted(slot_needs.items()):
            # Find matching mood in distribution
            have = 0
            for mood, count in distribution.items():
                if mood.value == mood_name:
                    have = count
                    break

            gap = max(0, needed - have)
            status = "[green]OK[/green]" if gap == 0 else f"[red]-{gap}[/red]"
            table.add_row(mood_name, str(needed), str(have), str(gap), status)

        console.print(table)


@app.command("inspect")
def inspect_track(
    track_id: int = typer.Argument(help="Track ID"),
) -> None:
    """Show detailed audio features for a single track."""
    run_async(_inspect_track(track_id=track_id))


async def _inspect_track(*, track_id: int) -> None:
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.tracks import TrackRepository
    from app.services.features import AudioFeaturesService
    from app.services.tracks import TrackService

    async with open_session() as session:
        track_svc = TrackService(TrackRepository(session))
        features_svc = AudioFeaturesService(
            AudioFeaturesRepository(session), TrackRepository(session)
        )

        track = await track_svc.get(track_id)
        feat = await features_svc.get_latest(track_id)
        console.print(features_panel(feat, track_title=track.title))
