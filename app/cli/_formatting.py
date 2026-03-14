"""Rich output helpers for the CLI layer.

Provides consistent table formatting, track display, and transition
rendering across all CLI commands.
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table

from app.cli._context import console


def _key_code_to_camelot(key_code: int) -> str:
    """Lazy import wrapper — avoids eager numpy import via audio.__init__."""
    from app.utils.audio.camelot import key_code_to_camelot

    return key_code_to_camelot(key_code)


# ── Track table ──────────────────────────────────────────────────────────────


def tracks_table(
    tracks: list[Any],
    *,
    title: str = "Tracks",
    artists_map: dict[int, list[str]] | None = None,
) -> Table:
    """Build a Rich Table for a list of TrackRead-like objects."""
    table = Table(title=title, show_lines=False)
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Title", style="bold", min_width=30)
    table.add_column("Artists", style="dim", min_width=20)
    table.add_column("Duration", justify="right", width=8)
    table.add_column("Status", width=8)

    amap = artists_map or {}
    for t in tracks:
        tid = getattr(t, "track_id", 0)
        title_val = getattr(t, "title", "—")
        dur_ms = getattr(t, "duration_ms", 0)
        status_val = getattr(t, "status", 0)
        artists = ", ".join(amap.get(tid, []))
        dur_str = _ms_to_mmss(dur_ms)
        status_str = "[green]active[/green]" if status_val == 0 else "[dim]archived[/dim]"
        table.add_row(str(tid), title_val, artists, dur_str, status_str)

    return table


# ── Playlist table ───────────────────────────────────────────────────────────


def playlists_table(playlists: list[Any], *, title: str = "Playlists") -> Table:
    """Build a Rich Table for DjPlaylistRead-like objects."""
    table = Table(title=title, show_lines=False)
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Name", style="bold", min_width=30)
    table.add_column("Source", width=10)
    table.add_column("Created", width=12)

    for p in playlists:
        pid = getattr(p, "playlist_id", 0)
        name = getattr(p, "name", "—")
        sot = getattr(p, "source_of_truth", "local")
        created = getattr(p, "created_at", None)
        created_str = created.strftime("%Y-%m-%d") if created else "—"
        table.add_row(str(pid), name, sot, created_str)

    return table


# ── Set table ────────────────────────────────────────────────────────────────


def sets_table(sets: list[Any], *, title: str = "DJ Sets") -> Table:
    """Build a Rich Table for DjSetRead-like objects."""
    table = Table(title=title, show_lines=False)
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Name", style="bold", min_width=30)
    table.add_column("Template", width=15)
    table.add_column("Created", width=12)

    for s in sets:
        sid = getattr(s, "set_id", 0)
        name = getattr(s, "name", "—")
        tmpl = getattr(s, "template_name", None) or "—"
        created = getattr(s, "created_at", None)
        created_str = created.strftime("%Y-%m-%d") if created else "—"
        table.add_row(str(sid), name, tmpl, created_str)

    return table


# ── Features display ─────────────────────────────────────────────────────────


def features_panel(feat: Any, *, track_title: str = "") -> Panel:
    """Build a Rich Panel for AudioFeaturesRead-like object."""
    key_str = "—"
    key_code = getattr(feat, "key_code", None)
    if key_code is not None:
        try:
            key_str = _key_code_to_camelot(key_code)
        except (ValueError, KeyError):
            key_str = f"code={key_code}"

    lines = [
        f"[bold]BPM:[/bold] {feat.bpm:.1f}  "
        f"[bold]Key:[/bold] {key_str}  "
        f"[bold]LUFS:[/bold] {feat.lufs_i:.1f}",
        "",
        f"Tempo confidence: {feat.tempo_confidence:.2f}  BPM stability: {feat.bpm_stability:.2f}",
        f"Energy mean: {feat.energy_mean:.3f}  Energy max: {feat.energy_max:.3f}",
    ]

    centroid = getattr(feat, "centroid_mean_hz", None)
    if centroid:
        lines.append(f"Centroid: {centroid:.0f} Hz")

    onset = getattr(feat, "onset_rate_mean", None)
    kick = getattr(feat, "kick_prominence", None)
    if onset or kick:
        parts: list[str] = []
        if onset:
            parts.append(f"Onset rate: {onset:.2f}")
        if kick:
            parts.append(f"Kick prominence: {kick:.2f}")
        lines.append("  ".join(parts))

    title_part = f" — {track_title}" if track_title else ""
    return Panel(
        "\n".join(lines),
        title=f"Audio Features (track {feat.track_id}{title_part})",
        border_style="blue",
    )


# ── Transition scores ────────────────────────────────────────────────────────


def transitions_table(
    scores: list[dict[str, Any]],
    *,
    title: str = "Transitions",
) -> Table:
    """Build a Rich Table for transition score results."""
    table = Table(title=title, show_lines=False)
    table.add_column("#", width=4)
    table.add_column("From", min_width=20)
    table.add_column("To", min_width=20)
    table.add_column("Score", justify="right", width=7)
    table.add_column("BPM", justify="right", width=7)
    table.add_column("Key", justify="right", width=9)
    table.add_column("Energy", justify="right", width=8)
    table.add_column("Type", width=10)
    table.add_column("", width=3)

    for i, s in enumerate(scores, 1):
        total = s.get("total", 0.0)
        score_style = _score_style(total)
        flag = "[red]!!![/red]" if total < 0.85 and total > 0 else ""
        if total == 0.0:
            flag = "[red bold]XXX[/red bold]"

        table.add_row(
            str(i),
            _truncate(s.get("from_title", "—"), 20),
            _truncate(s.get("to_title", "—"), 20),
            f"[{score_style}]{total:.3f}[/{score_style}]",
            f"{s.get('bpm', 0):.3f}",
            f"{s.get('harmonic', 0):.3f}",
            f"{s.get('energy', 0):.3f}",
            s.get("recommended_type", "—"),
            flag,
        )

    return table


# ── Set build result ─────────────────────────────────────────────────────────


def build_result_panel(
    set_id: int,
    version_id: int,
    track_count: int,
    total_score: float,
    avg_transition: float,
) -> Panel:
    """Build a Rich Panel showing set generation results."""
    lines = [
        f"[bold cyan]Set ID:[/bold cyan] {set_id}  [bold cyan]Version:[/bold cyan] {version_id}",
        f"[bold]Tracks:[/bold] {track_count}  "
        f"[bold]Total score:[/bold] {total_score:.4f}  "
        f"[bold]Avg transition:[/bold] {avg_transition:.4f}",
    ]
    return Panel("\n".join(lines), title="Set Build Result", border_style="green")


# ── Helpers ──────────────────────────────────────────────────────────────────


def print_total(total: int, entity: str = "items") -> None:
    """Print a dim total count line."""
    console.print(f"[dim]Total: {total} {entity}[/dim]")


def _ms_to_mmss(ms: int) -> str:
    """Convert milliseconds to MM:SS string."""
    secs = ms // 1000
    return f"{secs // 60}:{secs % 60:02d}"


def _score_style(score: float) -> str:
    """Return a Rich style based on score value."""
    if score >= 0.85:
        return "green"
    if score >= 0.70:
        return "yellow"
    if score > 0.0:
        return "red"
    return "red bold"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"
