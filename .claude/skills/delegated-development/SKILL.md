---
name: Delegated Development
description: Режим разработки через Codegen cloud agents. Используй когда: пользователь просит делегировать задачу агенту, запустить Codegen, следить за агентом, ревью PR созданного агентом, параллельный запуск нескольких агентов. Триггеры: "делегируй", "запусти агента", "codegen", /delegate, "@codegen-sh", Codegen Bridge.
---

# Delegated Development — Vertical Management System

## Назначение

Режим разработки с вертикальной системой управления: Principal Solution Architect (Claude Code) проектирует, декомпозирует и контролирует, а Codegen cloud agents исполняют bounded tasks.

---

## Организационная структура

```text
                    Principal Solution Architect
                    (Claude Code + evgenygurin)
                           |
              ┌────────────┼────────────┐
              |            |            |
        Tech Lead     QA/Review     DevOps
       (Claude Code)   (Codex)    (GitHub CI)
              |
     ┌────────┼────────┐
     |        |        |
  Engineer  Engineer  Engineer
  (Codegen) (Codegen) (Codegen)
```

### Роли и ответственности

| Роль | Актор | Зона ответственности |
|------|-------|---------------------|
| **Architect** | Claude Code (эта сессия) | Архитектура, декомпозиция, quality gates, merge decisions |
| **Tech Lead** | Claude Code (эта сессия) | Code review результатов Codegen |
| **Engineer** | Codegen agent (cloud) | Реализация bounded task по спецификации |
| **QA** | Codex (auto-review) + GitHub CI | Автоматический code review, lint, tests |
| **Product** | evgenygurin (пользователь) | Приоритеты, acceptance criteria, final approve |

---

## Философия: Codegen-first

**Codegen агенты бесплатны. Токены основной сессии — дорогие.**

### Делегировать ВСЕГДА (Codegen agent)

| Категория | Примеры |
|-----------|---------|
| Любой новый код | Модели, роутеры, сервисы, тесты, миграции |
| Рефакторинг | Извлечение base class, переименование, restructuring |
| Фиксы по code review | `@codegen-sh исправь замечания` |
| Тесты | Unit, integration, edge cases — всё |
| Документация | CHANGELOG, README, docstrings, comments |
| Code quality | Lint fixes, type annotations, dead code removal |

### НЕ делегировать

| Критерий | Почему |
|----------|--------|
| Работа с iCloud/локальными файлами | Sandbox не имеет доступа |
| Работа с dev.db (SQLite) напрямую | База на iCloud |
| MCP tool runtime debugging | Требует живой сервер |
| YM API с credentials | Токены/cookies локальные |

---

## `/delegate` — Основной интерфейс

`/delegate` — slash-команда для быстрого запуска Codegen cloud агента прямо из чата.

```text
/delegate <описание задачи>
```

### Workflow

```text
1. Пользователь: "/delegate implement energy arc adherence scoring"
2. Claude:
   - Анализирует задачу
   - Декомпозирует на subtasks (если нужно)
   - Формирует полный промпт с context, requirements, constraints
   - Запускает Codegen agent через codegen-bridge plugin
3. Codegen agent:
   - Клонирует репозиторий в cloud sandbox
   - Читает CLAUDE.md + .claude/rules/
   - Реализует задачу
   - Запускает make check
   - Создаёт PR с conventional commit
4. Claude:
   - Получает notification о PR
   - Делает review через view_pr (только diff)
   - Approve или request changes через @codegen-sh

Время: 3-15 минут от /delegate до PR.
```

---

## Промпт шаблон для @codegen-sh

```markdown
@codegen-sh

## Task
<Что сделать — одно предложение>

## Context
- Branch: <ветка>
- Related files: <список файлов для изучения>

## Requirements
- <Конкретное требование 1>
- <Конкретное требование 2>

## Constraints
- Follow existing patterns in <файл-образец>
- Run `make check` before committing
- Conventional commit: <type>(<scope>): <description>
- Do NOT modify files outside of <scope-dirs>
- Do NOT edit CHANGELOG.md (handled separately)
- Create branch `<branch-name>` from `<base-branch>`
- Create PR to `<base-branch>` (NOT main or dev!)

## Acceptance criteria
- [ ] <Конкретный критерий 1>
- [ ] `make check` passes
```

---

## Rate Limits

| Ограничение | Лимит | Обход |
|-------------|-------|-------|
| Параллельных агентов | 3 рекомендуемо | > 3 только если файлы независимы |
| Размер задачи | ≤ 5 файлов | Декомпозиция на subtasks |
| 1 Opus + 3 Sonnet | = rate limit! | Opus solo ИЛИ до 3 Sonnet |

**Model IDs (КРИТИЧНО)**: `claude-sonnet-4-5-20250929` (НЕ `sonnet-4-5` — 404!), `claude-opus-4-6`.

---

## Decision tree после PR

```text
make check failed?
  └─> "@codegen-sh fix CI errors" в PR

Codex нашёл P1/P2 issues?
  └─> "@codegen-sh исправь замечания codex" в PR

Diff OK + tests pass?
  └─> Merge в dev

Агент не справился (2+ попытки)?
  └─> Забрать локально
```

---

## Quality Gates

### Gate 1: Pre-delegation

- [ ] Task bounded: scope <= 3 файла
- [ ] Спецификация: task, context, requirements, constraints, acceptance criteria
- [ ] Файл-образец указан
- [ ] Branch создана и запушена

### Gate 2: Post-agent review

- [ ] `make check` проходит в PR
- [ ] Diff соответствует спецификации
- [ ] Нет хардкода credentials/paths
- [ ] Conventional commit message
- [ ] Codex review пройден

### Gate 3: Pre-merge

- [ ] Acceptance criteria выполнены
- [ ] CHANGELOG обновлён
- [ ] Нет merge conflicts

---

## Best Practices

1. **Специфичность** — чем конкретнее задача, тем выше success rate
2. **Pattern files** — всегда указывай файл-образец
3. **Bounded scope** — задача завершаема за 10-20 минут (1-3 файла)
4. **Linear ID** — включай BPM-xxx для автоматического трекинга
5. **Scope control** — "Do NOT modify files outside [scope]" в каждом промпте
6. **Branch control** — всегда "Create branch X from Y" + "Create PR to Y"
