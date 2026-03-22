#!/usr/bin/env python3
"""Dump live SQLite DB schema to .claude/rules/db-schema.md.

Generates a compact reference of all tables with columns, types, PKs,
FKs, and row counts — auto-loaded by Claude Code when editing DB-related files.

Usage:
    uv run python scripts/dump_db_schema.py           # uses $DJ_DB_PATH or .env
    uv run python scripts/dump_db_schema.py path.db    # explicit DB path
    make db-schema                                      # Makefile shortcut
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / ".claude" / "rules" / "db-schema.md"

# Tables to skip (internal / not useful for context)
SKIP_TABLES = frozenset({"sqlite_sequence", "alembic_version"})


def _load_env() -> None:
    """Source DJ_DB_PATH from .env if not already set."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _resolve_db_path(argv_path: str | None) -> Path:
    """Resolve DB path from CLI arg, env var, or default."""
    if argv_path:
        return Path(argv_path).expanduser().resolve()

    _load_env()
    env_path = os.environ.get("DJ_DB_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p.resolve()

    return PROJECT_ROOT / "dev.db"


def _get_row_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT count(*) FROM [{table}]").fetchone()[0]
    except sqlite3.OperationalError:
        return -1


def _get_foreign_keys(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    """Return {column: 'ref_table.ref_col'} for all FKs."""
    fks: dict[str, str] = {}
    try:
        for row in conn.execute(f"PRAGMA foreign_key_list([{table}])"):
            fks[row[3]] = f"{row[2]}.{row[4]}"
    except sqlite3.OperationalError:
        pass
    return fks


def _format_col(col: sqlite3.Row, fks: dict[str, str]) -> str:
    """Format column as compact one-liner: `name TYPE [PK] [NOT NULL] [DEFAULT x] [-> ref]`."""
    name = col[1]
    col_type = col[2] or ""
    parts: list[str] = [f"`{name}`", col_type] if col_type else [f"`{name}`"]
    if col[5]:  # pk
        parts.append("PK")
    if col[3]:  # notnull
        parts.append("NOT NULL")
    if col[4] is not None:  # default
        parts.append(f"DEFAULT {col[4]}")
    if name in fks:
        parts.append(f"-> {fks[name]}")
    return " ".join(parts)


def dump_schema(db_path: Path) -> str:
    """Generate compact markdown schema documentation."""
    conn = sqlite3.connect(str(db_path))

    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        if row[0] not in SKIP_TABLES
    ]

    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "---",
        "paths:",
        '  - "app/models/**"',
        '  - "app/repositories/**"',
        '  - "app/mcp/tools/**"',
        '  - "migrations/**"',
        "---",
        "",
        "# DB Schema Reference (auto-generated)",
        "",
        f"> Generated: {now} | Source: `{db_path.name}` | Tables: {len(tables)}",
        ">",
        "> **Do not edit manually.** Regenerate: `make db-schema`",
        "",
        "## Overview",
        "",
        "| Table | Rows | Cols |",
        "|-------|------|------|",
    ]

    # Collect data
    table_meta: list[tuple[str, int, list[sqlite3.Row], dict[str, str]]] = []
    for table in tables:
        cols = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
        fks = _get_foreign_keys(conn, table)
        rows = _get_row_count(conn, table)
        table_meta.append((table, rows, cols, fks))
        lines.append(f"| `{table}` | {rows:,} | {len(cols)} |")

    lines.append("")
    lines.append("## Tables")
    lines.append("")

    for table, rows, cols, fks in table_meta:
        # One-line header + compact column list
        lines.append(f"### `{table}` ({rows:,} rows)")
        for col in cols:
            lines.append(f"- {_format_col(col, fks)}")
        lines.append("")

    conn.close()
    return "\n".join(lines)


def main() -> None:
    argv_path = sys.argv[1] if len(sys.argv) > 1 else None
    db_path = _resolve_db_path(argv_path)

    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading schema from: {db_path}")
    content = dump_schema(db_path)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(content)

    line_count = content.count("\n") + 1
    print(f"Written to: {OUTPUT_FILE}")
    print(f"Size: {len(content):,} bytes | {line_count} lines")


if __name__ == "__main__":
    main()
