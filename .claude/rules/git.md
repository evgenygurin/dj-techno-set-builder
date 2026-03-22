# Git Workflow — Project Rules

Расширяет глобальные правила из `~/.claude/rules/git.md`.

## Linear Integration

### Ветки

```text
<type>/BPM-<id>-<short-description>

feat/BPM-42-set-delivery
fix/BPM-99-ym-rate-limit
refactor/BPM-101-mcp-types-cleanup
```

### PR title

```text
BPM-123: <описание>
```

Issue ID — первым токеном. Не в скобках, не в конце.
PR title проверяется GitHub Actions: `.github/workflows/pr-title.yml`.

### PR description magic words

| Слово | Эффект |
|-------|--------|
| `Fixes BPM-123` | Закрывает задачу при merge |
| `Related to BPM-123` | Линкует без закрытия |
| `Contributes to BPM-123` | Частичный вклад |

Подробности: `docs/linear.md`

## Domain Scopes

| Scope | Домен | Примеры файлов |
|-------|-------|----------------|
| `mcp` | MCP gateway, tools, types | `app/mcp/` |
| `api` | REST routers, schemas | `app/routers/`, `app/schemas/` |
| `db` | Models, repos, migrations | `app/models/`, `app/repositories/` |
| `audio` | Audio utils, scoring | `app/utils/audio/` |
| `ym` | Yandex Music integration | `app/mcp/yandex_music/` |
| `ga` | GA optimizer, set builder | `app/services/set_generator.py` |
| — | docs, chore, style | `CLAUDE.md`, `.claude/`, `docs/` |

## Branching Model

```text
main ← production, protected
  └── dev ← integration branch (40+ commits ahead)
        ├── feat/BPM-xxx-... ← feature branches
        └── fix/BPM-xxx-...  ← bugfix branches
```

- Feature branches от `dev`
- PR в `dev`
- `dev → main` через PR после стабилизации

## Post-Commit Checklist

После каждого коммита с изменениями кода/конфига:

- [ ] `CHANGELOG.md` → `[Unreleased]` обновлён
- [ ] `.claude/rules/*.md` обновлены если архитектура изменилась
- [ ] `make check` проходит (lint + test)
