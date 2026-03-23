"""Set delivery CLI command — score, write files, optional YM sync."""

from __future__ import annotations

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.cli._context import console, err_console, open_session, run_async

app = typer.Typer(name="deliver", help="Set delivery commands.", no_args_is_help=True)


@app.command("set")
def deliver_set(
    set_id: int = typer.Argument(help="Set ID to deliver"),
    version_id: int | None = typer.Option(
        None, "--version", "-v", help="Version ID (latest if omitted)"
    ),
    sync_ym: bool = typer.Option(False, "--sync-ym", help="Push to Yandex Music"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip hard-conflict prompts"),
) -> None:
    """Deliver a DJ set: score transitions, write files, optional YM sync.

    Writes M3U8, JSON guide, and cheat_sheet.txt to generated-sets/{name}/.
    """
    run_async(
        _deliver_set(
            set_id=set_id,
            version_id=version_id,
            sync_ym=sync_ym,
            force=force,
        )
    )


async def _deliver_set(
    *,
    set_id: int,
    version_id: int | None,
    sync_ym: bool,
    force: bool,
) -> None:
    import contextlib
    import json
    from pathlib import Path

    from app.config import settings
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.repositories.tracks import TrackRepository
    from app.services.features import AudioFeaturesService
    from app.services.sets import DjSetService
    from app.services.tracks import TrackService
    from app.services.transition_scoring_unified import UnifiedTransitionScoringService
    from app.utils.audio.camelot import key_code_to_camelot

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
        unified_svc = UnifiedTransitionScoringService(session)

        dj_set = await set_svc.get(set_id)
        set_name = dj_set.name

        # Resolve version
        if version_id is None:
            versions = await set_svc.list_versions(set_id)
            if not versions.items:
                err_console.print("[red]No versions found.[/red]")
                raise typer.Exit(1)
            latest = max(versions.items, key=lambda v: v.set_version_id)
            version_id = latest.set_version_id

        # ── Stage 1: Score transitions ──────────────────────────────────
        console.print(
            f"\n[bold]Stage 1/3[/bold] — Scoring transitions for [cyan]{set_name}[/cyan]..."
        )

        items_list = await set_svc.list_items(version_id, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        scores: list[dict[str, float]] = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Scoring...", total=max(len(items) - 1, 1))

            for i in range(len(items) - 1):
                from_id = items[i].track_id
                to_id = items[i + 1].track_id
                try:
                    components = await unified_svc.score_components_by_ids(from_id, to_id)
                    scores.append(components)
                except Exception:
                    scores.append({"total": 0.0, "bpm": 0.0, "harmonic": 0.0, "energy": 0.0})
                progress.advance(task)

        # Summary
        valid = [s for s in scores if float(str(s.get("total", 0))) > 0]
        hard_conflicts = sum(1 for s in scores if float(str(s.get("total", 0))) == 0)
        weak = sum(1 for s in valid if float(str(s.get("total", 0))) < 0.85)
        avg = sum(float(str(s.get("total", 0))) for s in valid) / len(valid) if valid else 0

        console.print(
            f"  Scored {len(scores)} transitions: "
            f"avg={avg:.3f}, {weak} weak, {hard_conflicts} hard conflicts"
        )

        if (
            hard_conflicts > 0
            and not force
            and not typer.confirm(f"Found {hard_conflicts} hard conflict(s). Continue delivery?")
        ):
            console.print("[yellow]Delivery aborted.[/yellow]")
            return

        # ── Stage 2: Write files ─────────────────────────────────────────
        console.print("\n[bold]Stage 2/3[/bold] — Writing files...")

        library = Path(settings.dj_library_path).expanduser()
        out_dir = library.parent / "generated-sets" / _safe_name(set_name)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Collect track data
        tracks_data: list[dict[str, object]] = []
        for pos, item in enumerate(items, 1):
            entry: dict[str, object] = {"position": pos, "track_id": item.track_id}
            with contextlib.suppress(Exception):
                track = await track_svc.get(item.track_id)
                entry["title"] = track.title
                entry["duration_s"] = track.duration_ms // 1000

            track_ids_list = [item.track_id]
            artists_map = await track_svc.get_track_artists(track_ids_list)
            artists = artists_map.get(item.track_id, [])
            entry["artists"] = ", ".join(artists) if artists else ""

            with contextlib.suppress(Exception):
                feat = await features_svc.get_latest(item.track_id)
                entry["bpm"] = feat.bpm
                entry["lufs"] = feat.lufs_i
                with contextlib.suppress(ValueError):
                    entry["key"] = key_code_to_camelot(feat.key_code)

            tracks_data.append(entry)

        # Write M3U8
        m3u_lines = ["#EXTM3U", f"#PLAYLIST:{set_name}"]
        for tr in tracks_data:
            title = str(tr.get("title", f"Track {tr['track_id']}"))
            duration = int(str(tr.get("duration_s", -1)))
            m3u_lines.append(f"#EXTINF:{duration},{title}")
            if tr.get("bpm"):
                m3u_lines.append(f"#EXTDJ-BPM:{tr['bpm']}")
            if tr.get("key"):
                m3u_lines.append(f"#EXTDJ-KEY:{tr['key']}")
            if tr.get("lufs"):
                m3u_lines.append(f"#EXTDJ-ENERGY:{tr['lufs']}")
            pos = int(str(tr["position"]))
            safe = _sanitize_fn(title)
            m3u_lines.append(f"{pos:03d}. {safe}.mp3")

        m3u_path = out_dir / f"{set_name}.m3u8"
        m3u_path.write_text("\n".join(m3u_lines) + "\n", encoding="utf-8")

        # Write JSON guide
        bpms = [float(str(tr["bpm"])) for tr in tracks_data if tr.get("bpm")]
        total_s = sum(int(str(tr.get("duration_s", 0))) for tr in tracks_data)
        guide = {
            "set_name": set_name,
            "track_count": len(tracks_data),
            "tracks": tracks_data,
            "transitions": scores,
            "analytics": {
                "bpm_range": [min(bpms), max(bpms)] if bpms else [],
                "total_duration_s": total_s,
            },
        }
        json_path = out_dir / f"{set_name}.json"
        json_text = json.dumps(guide, ensure_ascii=False, indent=2, default=str)
        json_path.write_text(json_text, encoding="utf-8")

        # Write cheat sheet
        cheat_lines = [
            "=" * 80,
            f"CHEAT SHEET: {set_name}",
            "=" * 80,
            f"{'#':<4} {'Track':<30} {'BPM':>7} {'Key':>4} {'LUFS':>6}  Score",
            "-" * 80,
        ]
        for idx, tr in enumerate(tracks_data):
            pos = int(str(tr["position"]))
            title = str(tr.get("title", f"Track {tr['track_id']}"))[:30]
            bpm_s = f"{tr['bpm']:.1f}" if tr.get("bpm") else "—"
            key_s = str(tr.get("key", "—"))
            lufs_s = f"{tr['lufs']:.1f}" if tr.get("lufs") else "—"

            score_s = "— (last)"
            if idx < len(scores):
                total = float(str(scores[idx].get("total", 0)))
                flag = " !!!" if 0 < total < 0.85 else ""
                score_s = f"{total:.3f}{flag}"

            cheat_lines.append(
                f"{pos:02d}.  {title:<30} {bpm_s:>7} {key_s:>4} {lufs_s:>6}  {score_s}"
            )

        cheat_lines += ["=" * 80, "", "!!! = weak transition (< 0.85)", ""]
        cheat_path = out_dir / "cheat_sheet.txt"
        cheat_path.write_text("\n".join(cheat_lines) + "\n", encoding="utf-8")

        files_written = [m3u_path.name, json_path.name, cheat_path.name]
        console.print(f"  Written to [bold]{out_dir}[/bold]:")
        for f in files_written:
            console.print(f"    [green]\u2713[/green] {f}")

        # ── Stage 3: YM sync ────────────────────────────────────────────
        if sync_ym:
            console.print("\n[bold]Stage 3/3[/bold] — Syncing to Yandex Music...")
            try:
                from app.services.yandex_music_client import YandexMusicClient

                if not settings.yandex_music_token or not settings.yandex_music_user_id:
                    err_console.print(
                        "[yellow]YM sync skipped: YANDEX_MUSIC_TOKEN/USER_ID not set.[/yellow]"
                    )
                else:
                    ym_client = YandexMusicClient(settings.yandex_music_token)
                    ym_user_id = int(settings.yandex_music_user_id)
                    title = f"{set_name} [set]"

                    kind = await ym_client.create_playlist(ym_user_id, title)
                    console.print(f"  [green]Created YM playlist:[/green] kind={kind}")
                    await ym_client.close()
            except Exception as exc:
                err_console.print(f"[red]YM sync failed:[/red] {exc}")
        else:
            console.print("\n[bold]Stage 3/3[/bold] — [dim]YM sync skipped (use --sync-ym)[/dim]")

        console.print(f"\n[green bold]Delivery complete![/green bold] {set_name}")


def _safe_name(name: str) -> str:
    """Convert set name to a safe directory name."""
    s = _sanitize_fn(name).strip(". ")
    return s.lower().replace(" ", "_")


def _sanitize_fn(name: str) -> str:
    """Remove filesystem-unsafe characters."""
    unsafe = '<>:"/\\|?*'
    result = name
    for ch in unsafe:
        result = result.replace(ch, "")
    return result.strip()
