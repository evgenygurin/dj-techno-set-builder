---
name: delegated-development
description: Use when delegating tasks to Codegen cloud agents, monitoring agent runs, reviewing agent PRs, or running multiple agents in parallel. Triggers on "delegate", "codegen", /delegate, "@codegen-sh", Codegen Bridge.
---

# Delegated Development

Codegen cloud agents исполняют bounded tasks. Claude Code проектирует и контролирует.

## Когда делегировать

| Делегировать (Codegen) | НЕ делегировать |
|----------------------|----------------|
| Любой новый код, тесты | iCloud/локальные файлы |
| Рефакторинг, lint fixes | dev.db (SQLite на iCloud) |
| Фиксы по code review | MCP runtime debugging |
| Документация | YM API с credentials |

## `/delegate` — быстрый запуск

```text
/delegate <описание задачи>
```

Claude анализирует → декомпозирует → формирует промпт → запускает Codegen agent → review PR.

## Промпт шаблон

```markdown
@codegen-sh

## Task
<Одно предложение>

## Context
- Branch: <ветка>
- Related files: <список>

## Requirements
- <Требование 1>

## Constraints
- Follow patterns in <файл-образец>
- Run `make check` before committing
- Do NOT modify files outside <scope>
- Create branch `X` from `Y`, PR to `Y`

## Acceptance criteria
- [ ] <Критерий>
- [ ] `make check` passes
```

## Richness Rule

**Codegen agents видят ТОЛЬКО клонированный репо + промпт.** Промпт ДОЛЖЕН содержать полный контекст.

| Элемент | Почему |
|---------|--------|
| Ветка (from + to) | PR не туда |
| Текущий код (20-50 строк) | Агент не знает что написано |
| Что НЕ трогать | Агент сломает логику |
| Acceptance criteria | Нет definition of done |

Минимум: 200 слов (1 файл), 500 слов (1-3 файла), >3 файлов → декомпозируй.

## Quality Gates

**Pre-delegation**: scope ≤ 3 файла, спецификация, файл-образец, branch.
**Post-agent**: `make check`, diff vs spec, no hardcoded secrets, Codex review.
**Pre-merge**: acceptance criteria, CHANGELOG, no conflicts.

## Rate Limits

- Параллельных: 3 рекомендуемо (1 Opus ИЛИ 3 Sonnet)
- Model IDs: `claude-sonnet-4-5-20250929` (НЕ `sonnet-4-5`)
- Размер задачи: ≤ 5 файлов

## Decision tree после PR

```text
make check failed → "@codegen-sh fix CI errors"
Codex P1/P2 issues → "@codegen-sh исправь замечания"
Diff OK + tests pass → Merge в dev
2+ неудачных попытки → Забрать локально
```

---

## Iron Law

```text
NO MERGE WITHOUT make check PASSING LOCALLY
```

Codegen агент может пропустить lint/mypy/tests. ВСЕГДА проверяй `make check` на PR ветке перед merge.

## Red Flags

| Отговорка | Реальность |
|-----------|------------|
| "Тесты прошли у агента" | Агент мог пропустить mypy strict, ruff, или test pollution |
| "Scope маленький, review не нужен" | Даже 1-строчный diff может сломать import chain или typing |
| "Промпт и так понятный" | Codegen видит ТОЛЬКО клон репо + промпт — без context из head = слепая работа |
| "Сделаю review потом" | PR без review = tech debt, который копится |
| "3+ файла — нормально" | Scope > 3 файлов → декомпозируй на подзадачи |

## Примеры задач для делегирования

```text
# Тесты
/delegate Добавить тесты для app/mcp/tools/curation.py — classify_tracks, analyze_library_gaps

# Lint fix
/delegate Исправить все mypy ошибки в app/services/set_generation.py

# Рефакторинг
/delegate Извлечь общий паттерн из TrackRepository и PlaylistRepository в BaseFilterRepository

# Документация
/delegate Добавить docstrings к всем публичным методам в app/services/transition_scoring.py
```
