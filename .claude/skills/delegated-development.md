# Delegated Development — Vertical Management System

## Назначение

Режим разработки с вертикальной системой управления: Principal Solution Architect (Claude Code) проектирует, декомпозирует и контролирует, а Codegen cloud agents исполняют bounded tasks. Как в современной небольшой IT-компании — минимум бюрократии, максимум автономии в рамках чётких границ.

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

| Роль | Актор | Зона ответственности | Решения |
|------|-------|---------------------|---------|
| **Architect** | Claude Code (эта сессия) | Архитектура, декомпозиция, quality gates, merge decisions | Что делать, как декомпозировать, когда мержить |
| **Tech Lead** | Claude Code (эта сессия) | Code review результатов Codegen, доработка, интеграция | Approve/reject PR, request changes |
| **Engineer** | Codegen agent (cloud) | Реализация bounded task по спецификации | Выбор реализации в рамках constraints |
| **QA** | Codex (auto-review) + GitHub CI | Автоматический code review, lint, tests | Блокирует merge при failures |
| **Product** | evgenygurin (пользователь) | Приоритеты, acceptance criteria, final approve | Go/no-go на merge в dev/main |

---

## Философия: Codegen-first

**Codegen агенты бесплатны. Токены основной сессии — дорогие.**

Принцип: всё что МОЖНО делегировать — делегируем. Основная сессия (Claude Code) выполняет роль
диспетчера: декомпозиция, промпты, review diff, merge. Никакого чтения кода, никакого написания кода
в основной сессии если это можно отдать агенту.

### Делегировать ВСЕГДА (Codegen agent)

| Категория | Примеры |
|-----------|---------|
| Любой новый код | Модели, роутеры, сервисы, тесты, миграции |
| Рефакторинг | Извлечение base class, переименование, restructuring |
| Фиксы по code review | "@codegen-sh исправь замечания" |
| Тесты | Unit, integration, edge cases — всё |
| Документация | CHANGELOG, README, docstrings, comments |
| Исследование кода | "Найди все места где используется X и опиши" |
| Архитектурные задачи | Разбить на 2-3 subtask, запустить последовательно |
| Code quality | Lint fixes, type annotations, dead code removal |

### НЕ делегировать (только если физически невозможно)

| Критерий | Почему |
|----------|--------|
| Работа с iCloud/локальными файлами | Sandbox не имеет доступа |
| Работа с dev.db (SQLite) напрямую | База на iCloud |
| MCP tool runtime debugging | Требует живой сервер |
| YM API с credentials | Токены/cookies локальные |

**Если агент провалился** — не забирай задачу локально сразу. Сначала:
1. `codegen_analyse_run_logs` — понять причину
2. Уточнить промпт и перезапустить
3. Только после 2 неудач — делать локально

---

## Экономия контекста основной сессии

**Основная сессия = диспетчер. Не читай код, не пиши код.**

| Действие | Основная сессия | Codegen agent |
|----------|----------------|---------------|
| Читать файлы проекта | НЕТ (только gh pr diff) | ДА (полный доступ) |
| Писать код | НЕТ | ДА |
| Исследовать codebase | НЕТ (только blueprint/search) | ДА (Glob, Grep, Read) |
| Запускать тесты | НЕТ | ДА (make check) |
| Code review | Только `gh pr diff` (compact) | — |
| Декомпозиция задач | ДА (главная роль) | — |
| Написание промптов | ДА (главная роль) | — |
| Merge decisions | ДА | — |
| Git operations | Только merge/branch | commit/push |

**Правила экономии:**
- НЕ читай файлы через Read — дай это агенту
- НЕ запускай make check — агент сделает
- НЕ пиши код — опиши ЧТО нужно в промпте агенту
- Review = `gh pr diff <num> | head -100` — только diff, не весь файл
- Используй `codegen_analyse_run_logs` вместо ручного чтения логов

---

## Workflow: делегирование задачи

### Шаг 1: Декомпозиция (Architect)

Разбить фичу на atomic tasks. Каждый task = один Codegen agent run.

```text
Фича: "Добавить фильтрацию треков по energy level"

Task 1: Добавить energy_level enum в модели (app/models/track.py)
Task 2: Расширить repository метод filter_tracks (app/repositories/tracks.py)
Task 3: Добавить query parameter в router (app/routers/v1/tracks.py)
Task 4: Написать тесты (tests/routers/test_tracks.py)
```

### Шаг 2: Спецификация для агента

Каждый промпт для Codegen ДОЛЖЕН содержать:

```markdown
## Task
<Что сделать — одно предложение>

## Context
- Branch: <ветка>
- Base: <от какой ветки>
- Related files: <список файлов для изучения>

## Requirements
- <Конкретное требование 1>
- <Конкретное требование 2>

## Constraints
- Follow existing patterns in <файл-образец>
- Run `make check` before committing
- Conventional commit: <type>(<scope>): <description>
- Co-Authored-By: Claude <noreply@anthropic.com>

## Acceptance criteria
- [ ] <Конкретный критерий 1>
- [ ] <Конкретный критерий 2>
- [ ] `make check` passes (ruff + mypy + pytest)
```

### Шаг 3: Запуск агента

```text
codegen_create_run(
  prompt: "<спецификация>",
  repo_id: 222130,
  agent_type: "claude_code",
  confirmed: true
)
```

### Шаг 4: Мониторинг

```text
codegen_get_run(run_id: X)        # Статус
codegen_get_logs(run_id: X)       # Шаги выполнения
codegen_analyse_run_logs(run_id: X)  # AI-анализ логов
```

### Шаг 5: Review и интеграция

1. Codegen создаёт PR → Codex автоматически ревьюит
2. Architect проверяет diff: `gh pr diff <num>`
3. Если нужны правки → комментарий "@codegen-sh исправь X"
4. Если ОК → merge (или запрос approve у Product)

---

## Branching model для делегирования

```text
dev ← integration branch
  └── feat/BPM-xxx-feature-name ← feature branch (создаётся Architect)
        ├── codegen/task-1-description ← Codegen agent branch (auto)
        ├── codegen/task-2-description ← Codegen agent branch (auto)
        └── ... (каждый agent создаёт свой PR в feature branch)
```

**Правило**: Codegen агенты создают PR в **feature branch**, НЕ в dev/main напрямую.

---

## Quality Gates

### Gate 1: Pre-delegation (Architect)

- [ ] Task bounded: scope <= 3 файла
- [ ] Спецификация содержит: task, context, requirements, constraints, acceptance criteria
- [ ] Файл-образец указан (pattern to follow)
- [ ] Branch создана и запушена

### Gate 2: Post-agent (Tech Lead review)

- [ ] `make check` проходит в PR
- [ ] Diff соответствует спецификации (не больше, не меньше)
- [ ] Нет хардкода credentials/paths
- [ ] Conventional commit message
- [ ] Codex review пройден (или замечания несущественные)

### Gate 3: Pre-merge (Product approve)

- [ ] Acceptance criteria выполнены
- [ ] Интеграционные тесты пройдены
- [ ] CHANGELOG обновлён
- [ ] Нет merge conflicts

---

## Escalation paths

| Ситуация | Действие |
|----------|----------|
| Codegen agent stuck (>10 min) | `codegen_get_logs` → diagnose → `codegen_resume_run` с подсказкой |
| Agent создал PR с ошибками | Comment "@codegen-sh fix: <описание>" |
| Agent не справился (2+ попытки) | Забрать задачу локально, закрыть PR |
| Codex review с критическими P1 | Блокировать merge, исправить локально или через agent |
| CI fails | `codegen_analyse_run_logs` → fix локально или re-run |

---

## Параллелизация

Запускай до 3 Codegen агентов параллельно если задачи **независимы**:

```text
# Параллельно (нет зависимостей между файлами):
Agent 1: добавить модель + миграцию
Agent 2: написать тесты для существующего кода
Agent 3: обновить документацию

# Последовательно (зависимости):
Agent 1: создать модель → merge
Agent 2: создать repository (зависит от модели) → merge
Agent 3: создать router (зависит от repository) → merge
```

---

## Шаблоны промптов для типовых задач

### Новый CRUD endpoint

```markdown
## Task
Create CRUD router for {entity} following existing patterns.

## Context
- Branch: feat/BPM-xxx-{entity}
- Pattern file: app/routers/v1/tracks.py (follow this structure exactly)
- Model: app/models/{entity}.py (already exists)
- Repository: app/repositories/{entity}.py (already exists)

## Requirements
- Router with GET (list + detail), POST, PUT, DELETE
- Pydantic schemas in app/schemas/{entity}.py
- OpenAPI error responses from app/routers/v1/_openapi.py
- Register in app/routers/v1/__init__.py

## Constraints
- DI: `DbSession = Annotated[AsyncSession, Depends(get_session)]`
- Service layer between router and repository
- `make check` must pass

## Acceptance criteria
- [ ] All 5 CRUD endpoints working
- [ ] Schemas with proper validation
- [ ] Registered in router __init__
- [ ] `make check` passes
```

### Fix code review feedback

```markdown
## Task
Address code review feedback on PR #{num}.

## Context
- PR: #{num} on branch {branch}
- Review comments: {summary of comments}

## Requirements
- Fix each review comment
- Do not change unrelated code
- Preserve existing test coverage

## Constraints
- `make check` must pass after fixes
- Conventional commit: fix({scope}): address review feedback

## Acceptance criteria
- [ ] All review comments addressed
- [ ] No regressions in tests
- [ ] `make check` passes
```

### Write tests for existing code

```markdown
## Task
Write comprehensive tests for {module}.

## Context
- Branch: test/BPM-xxx-{module}-tests
- Target: {file_path}
- Test pattern: tests/{matching_path}
- Existing test examples: tests/services/test_track_service.py

## Requirements
- Happy path + edge cases + error cases
- Use project fixtures from tests/conftest.py
- pytest-asyncio (asyncio_mode = "auto", no @pytest.mark.asyncio needed)
- In-memory SQLite for DB tests

## Constraints
- No mocking of repository layer (use real DB fixtures)
- `make check` must pass

## Acceptance criteria
- [ ] >= 80% coverage for target module
- [ ] Edge cases covered (empty input, None, duplicates)
- [ ] Error cases covered (not found, validation errors)
- [ ] `make check` passes
```

---

## Метрики эффективности

Отслеживай после каждого sprint/фичи:

| Метрика | Цель | Как считать |
|---------|------|-------------|
| Agent success rate | > 70% | Merged PRs / Total agent PRs |
| First-pass success | > 50% | PRs merged без повторных фиксов / Total |
| Time to merge | < 30 min | Created → Merged |
| Rework ratio | < 30% | Фиксы после review / Total commits |
| Local fallback rate | < 20% | Задачи забранные локально / Total delegated |

---

## Чеклист запуска режима делегирования

- [ ] Feature branch создана и запушена
- [ ] Linear issue привязан (BPM-xxx)
- [ ] Задачи декомпозированы на atomic tasks
- [ ] Спецификации написаны для каждого task
- [ ] Codegen agents запущены (`codegen_create_run`)
- [ ] Мониторинг настроен (polling или webhook)
- [ ] Review plan готов (кто, когда, criteria)
