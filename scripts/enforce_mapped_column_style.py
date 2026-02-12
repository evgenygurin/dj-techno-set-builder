#!/usr/bin/env python3
"""Enforce multiline mapped_column(...) style with trailing commas.

Transforms:
    field: Mapped[int] = mapped_column(Integer, nullable=False)
into:
    field: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
"""

from __future__ import annotations

import re
from pathlib import Path

TARGET_DIRS = (Path("app/models"),)


def normalize_file(path: Path) -> bool:
    lines = path.read_text().splitlines()
    out: list[str] = []
    changed = False
    i = 0

    while i < len(lines):
        line = lines[i]
        m = re.match(r'^(\s*\w[^=]*=\s*)mapped_column\((.*)\)$', line)

        # One-line mapped_column(...) case.
        if m:
            prefix, inline_args = m.groups()
            indent = re.match(r'^(\s*)', prefix).group(1)
            args = [a.strip().rstrip(',') for a in inline_args.split(',') if a.strip()]

            out.append(f'{prefix}mapped_column(')
            for arg in args:
                out.append(f'{indent}    {arg},')
            out.append(f'{indent})')
            changed = True
            i += 1
            continue

        m = re.match(r'^(\s*\w[^=]*=\s*)mapped_column\($', line)
        # Already multi-line mapped_column(...) case.
        if not m:
            out.append(line)
            i += 1
            continue

        prefix = m.group(1)
        indent = re.match(r'^(\s*)', prefix).group(1)
        args: list[str] = []
        i += 1

        while i < len(lines):
            cur = lines[i].strip()
            if cur == ')':
                i += 1
                break
            if cur:
                args.append(cur.rstrip(',').strip())
            i += 1

        out.append(f'{prefix}mapped_column(')
        for arg in args:
            out.append(f'{indent}    {arg},')
        out.append(f'{indent})')

        changed = True

    updated = '\n'.join(out) + '\n'
    if updated != path.read_text():
        path.write_text(updated)
        return True
    return changed


def main() -> None:
    changed_paths: list[Path] = []
    for root in TARGET_DIRS:
        if not root.exists():
            continue
        for path in root.rglob('*.py'):
            if normalize_file(path):
                changed_paths.append(path)

    for path in changed_paths:
        print(path)


if __name__ == '__main__':
    main()
