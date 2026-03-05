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
| Фиксы по code review | `@codegen-sh исправь замечания` |
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
1. Посмотри логи через PR комментарии или codegen trace
2. Уточни промпт и перезапусти через `@codegen-sh`
3. Только после 2 неудач — делать локально

---

## Экономия контекста основной сессии

**Основная сессия = диспетчер. Не читай код, не пиши код.**

| Действие | Основная сессия | Codegen agent |
|----------|----------------|---------------|
| Читать файлы проекта | НЕТ (только `view_pr` diff) | ДА (полный доступ) |
| Писать код | НЕТ | ДА |
| Исследовать codebase | НЕТ (только search tools) | ДА (Glob, Grep, Read) |
| Запускать тесты | НЕТ | ДА (make check) |
| Code review | Только `view_pr` (compact diff) | — |
| Декомпозиция задач | ДА (главная роль) | — |
| Написание промптов | ДА (главная роль) | — |
| Merge decisions | ДА | — |
| Git operations | Только merge/branch | commit/push |

**Правила экономии:**
- НЕ читай файлы через Read — дай это агенту
- НЕ запускай make check — агент сделает
- НЕ пиши код — опиши ЧТО нужно в промпте агенту
- Review = `view_pr` MCP tool — только diff, не весь файл
- Используй `@codegen-sh` комментарии для быстрых фиксов

---

## Codegen Bridge — Инструменты

### Настройка плагина

Плагин `codegen-bridge` настроен в `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "codegen-bridge-dev": {
      "source": { "source": "github", "repo": "evgenygurin/codegen-bridge" }
    }
  },
  "enabledPlugins": {
    "codegen-bridge@codegen-bridge-dev": true
  }
}
```

### Основные способы запуска агентов

| Способ | Когда использовать | Пример |
|--------|-------------------|--------|
| `@codegen-sh` комментарий в PR | Фикс замечаний, доработка существующего PR | `@codegen-sh исправь замечания codex` |
| `create_pr_comment` MCP tool | Программный запуск через PR | Создать комментарий с `@codegen-sh` |
| Codegen Dashboard | Сложные задачи, настройка sandbox | codegen.com → New Agent Run |

### MCP Tools для управления (через codegen-tools)

| Tool | Назначение | Когда использовать |
|------|-----------|-------------------|
| `create_pr_comment` | Отправить задачу через `@codegen-sh` | Запуск агента на существующем PR |
| `view_pr` | Посмотреть diff, review comments | Review результата агента |
| `create_pr` | Создать PR для новой ветки | Подготовка перед запуском агентов |
| `edit_pr_meta` | Изменить title/body/state PR | Обновить статус после review |
| `list_pr_checks` | Проверить CI статус | Убедиться что checks пройдены |
| `view_commit` | Посмотреть конкретный коммит | Проверить что именно изменил агент |
| `search_issues` | Найти связанные PR/issues | Контекст для декомпозиции |

### Паттерн запуска: @codegen-sh в PR комментарии

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

## Acceptance criteria
- [ ] <Конкретный критерий 1>
- [ ] `make check` passes
```

### Мониторинг агента

```text
1. Создать PR comment с @codegen-sh → агент запускается
2. Codegen бот отвечает со ссылкой на trace: "📻 View my work"
3. Ждать ответ бота с результатом (обычно 3-10 мин)
4. view_pr → проверить diff и review comments
5. Если нужны правки → ещё один @codegen-sh comment
6. Если OK → merge
```

### Обработка ошибок

| Ситуация | Действие |
|----------|----------|
| Агент не ответил (>15 мин) | Проверить trace ссылку, перезапустить |
| Агент создал PR с ошибками | `@codegen-sh fix: <описание>` в PR |
| Агент не справился (2+ попытки) | Забрать задачу локально, закрыть PR |
| Codex review с критическими P1 | Блокировать merge, исправить через agent или локально |
| CI fails | Посмотреть `list_pr_checks`, создать fix comment |

---

## Linear интеграция

### Linear ↔ GitHub ↔ Codegen треугольник

```text
Linear Issue (BPM-123)
    ↓ создаём ветку
feat/BPM-123-feature-name
    ↓ @codegen-sh в PR
Codegen Agent → коммиты → PR
    ↓ автоматически
Codex Auto-Review → замечания
    ↓ @codegen-sh исправь
Codegen Agent → фиксы
    ↓ merge с "Fixes BPM-123"
Linear Issue → Done ✓
```

### Magic words в PR description

| Слово | Эффект |
|-------|--------|
| `Fixes BPM-123` | Закрывает задачу при merge |
| `Related to BPM-123` | Линкует без закрытия |
| `Contributes to BPM-123` | Частичный вклад |

### MCP Tools для Linear

| Tool | Назначение | Когда |
|------|-----------|-------|
| `linear_create_issue` | Создать подзадачу | Декомпозиция фичи на agent tasks |
| `linear_update_issue` | Обновить статус | После завершения агента |
| `linear_search_issues` | Найти связанные задачи | Контекст для планирования |
| `linear_get_issue` | Прочитать детали задачи | Понять scope перед декомпозицией |
| `linear_comment_on_issue` | Оставить обновление | Прогресс-репорт |
| `linear_get_teams` | Список команд | Начальная настройка |
| `linear_get_issue_states` | Доступные статусы | Для update_issue |
| `linear_get_active_cycle` | Текущий спринт | Привязка задач к спринту |
| `linear_assign_issue_to_cycle` | Добавить в спринт | Планирование |

### Жизненный цикл задачи

```text
1. linear_create_issue("BPM-123: Implement energy arc scoring")
2. Декомпозиция на sub-issues:
   - BPM-124: Add compute method (→ Agent A)
   - BPM-125: Write tests (→ Agent B)  
   - BPM-126: Update MCP tool (→ Agent C, после 124)
3. Каждый agent run → PR с "Fixes BPM-12x"
4. На merge → Linear issue автоматически закрывается
5. Родительский BPM-123 трекает прогресс
```

---

## Case Study: PR #26 — Energy Arc Adherence

### Хронология событий

| Шаг | Событие | Актор |
|-----|---------|-------|
| 1 | Нужен scoring энергетической дуги сета | Product (evgenygurin) |
| 2 | Codegen agent создал ветку `fix/energy-arc-adherence` | Engineer (Codegen) |
| 3 | Реализовал `compute_energy_arc_adherence()` в `SetCurationService` | Engineer |
| 4 | Обновил `review_set` MCP tool с параметром `template` | Engineer |
| 5 | Написал 15 тестов (adherence + interpolation) | Engineer |
| 6 | Создал PR #26 → 4 файла, 990 тестов pass | Engineer |
| 7 | Codex auto-review нашёл **2 P2 issues** | QA (Codex) |
| 8 | P2-1: list comprehension пропускает треки без features → сжимает позиции | QA |
| 9 | P2-2: hardcoded `classic_60` вместо `set.template_name` | QA |
| 10 | evgenygurin: `@codegen-sh исправь замечания` | Product → Engineer |
| 11 | Agent добавил `compute_energy_arc_adherence_with_gaps()` | Engineer |
| 12 | Agent извлёк `set.template_name` с fallback на параметр | Engineer |
| 13 | Agent подтвердил: mypy + ruff pass | Engineer |

### Извлечённые уроки

1. **Codex ловит реальные архитектурные проблемы** — не просто стиль, а логические ошибки (сжатие позиций при пропуске треков)
2. **`@codegen-sh` паттерн** — позволяет исправить замечания одним комментарием, без создания нового agent run
3. **Agent справился с нетривиальной бизнес-логикой** — DB-aware template resolution с fallback
4. **Цикл: Agent → Codex review → Fix = 15 минут** от PR до готового кода

### Обобщённый паттерн

```text
Architect: декомпозиция + промпт
    → Codegen Agent: реализация + PR
        → Codex: автоматический review (P1/P2/P3)
            → Architect: "@codegen-sh исправь <summary>"
                → Agent: фиксы + push
                    → Merge ✓
```

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

**Для параллельных агентов** — каждый работает в своём файле:

```text
feat/BPM-xxx-big-feature
  ├── Agent A → .codegen/drafts/part-a.md (или свой .py файл)
  ├── Agent B → .codegen/drafts/part-b.md
  └── Agent C → .codegen/drafts/part-c.md
  → Assembler agent (или Architect): merge в финальные файлы
```

---

## Параллелизация

Запускай до 3 Codegen агентов параллельно если задачи **независимы**:

> **Rate limit**: орг-лимит Codegen — 2M input tokens/min. При запуске >3 opus-агентов
> одновременно все получают `rate_limit_error` и завершаются без результата.
> Для research-задач используй sonnet (дешевле по токенам).

### Матрица решений

| Связь между задачами | Стратегия | Пример |
|---------------------|-----------|--------|
| Независимые (разные файлы) | **Параллельно** | Model + Tests для другого модуля |
| Interface dependency | **Последовательно** + контракт | Service → Router |
| Один файл, разные секции | **Последовательно** | 2 метода в одном классе |
| Один файл, одна секция | **НЕ делегировать параллельно** | Рефакторинг функции |

### Предотвращение конфликтов

1. **File-level isolation**: каждый агент владеет конкретными файлами
2. **Draft-first**: агенты пишут в temp файлы → assembler мержит
3. **Sequential chains**: Agent 1 → merge → Agent 2 (для зависимых задач)
4. **Interface contracts**: определи API контракт первым → параллельная реализация

### При конфликте

1. `git merge --no-commit` → инспекция
2. Создать fix-агента с описанием конфликта
3. Manual resolution как последнее средство

---

## Advanced Operations

### Sandbox Setup для Codegen агентов

Что нужно агентам для работы с этим проектом:

```bash
# Setup commands (настроить в Codegen Dashboard → Repository → Setup)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --all-extras
```

**Важно:**
- `dev.db` НЕ доступен в sandbox — тесты используют in-memory SQLite
- Alembic миграции НЕ запускать в sandbox
- `make check` = ruff + mypy + pytest → должен проходить

### Agent Rules (рекомендуемые)

Настроить в Codegen Dashboard → Repository → Agent Rules:

```text
1. Всегда читай CLAUDE.md первым
2. Читай `.claude/rules/*.md` для соответствующего домена
3. Запускай `make check` перед коммитом
4. Используй conventional commits: <type>(<scope>): <description>
5. Не модифицируй файлы вне scope задачи
6. Не пушь в dev или main напрямую
7. Co-Authored-By: Claude <noreply@anthropic.com>
```

### GitHub Actions интеграция

| Trigger | Action | Эффект |
|---------|--------|--------|
| PR created | PR title check | Блокирует если нет BPM-xxx |
| PR created | Codex auto-review | Inline comments P1/P2/P3 |
| `@codegen-sh` comment | Codegen agent triggered | Агент работает с PR |
| Check suite failure | Auto-fixer (если включён) | Codegen пытается исправить CI |

### Hooks для автоматизации

```json
{
  "hooks": {
    "PostCommit": [{
      "command": "sh -c 'git diff --name-only HEAD~1 | grep -q app/models && make db-schema || true'",
      "description": "Auto-regenerate db-schema.md when models change"
    }],
    "PrePush": [{
      "command": "make check",
      "description": "Verify lint + tests before push"
    }]
  }
}
```

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

## Session Handoff для делегированного режима

При передаче работы в новую сессию — фиксируй:

### Таблица состояния агентов

```markdown
| Agent | Task | PR | Status | Trace |
|-------|------|----|--------|-------|
| A | Bridge API section | #27 | ⏳ running | codegen.com/trace/170xxx |
| B | Linear section | #27 | ✅ done | codegen.com/trace/170yyy |
| C | Advanced ops | #27 | ❌ failed | codegen.com/trace/170zzz |
```

### Промпт для новой сессии

```markdown
## Контекст: разработка delegated-development skill v2

### Предыстория
- Ветка: feat/enhanced-delegated-dev, PR #27
- 3 codegen агента запущены на PR #27 (комментарии @codegen-sh)
- Agent A: Bridge API, Agent B: Linear + Case Study, Agent C: Advanced Ops

### Задачи
1. Проверить статус агентов: `view_pr(27)` → новые комментарии/коммиты
2. Если агенты завершили → review drafts в `.codegen/drafts/`
3. Собрать финальный `.claude/skills/delegated-development.md`
4. Обновить CHANGELOG, commit, push, PR ready for review
```

---

## Шаблоны промптов для типовых задач

### Новый CRUD endpoint

```markdown
@codegen-sh

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
@codegen-sh исправь замечания codex review:

1. <Замечание 1 — краткое описание>
2. <Замечание 2 — краткое описание>

Constraints: `make check` must pass, conventional commit.
```

### Write tests

```markdown
@codegen-sh

## Task
Write comprehensive tests for {module}.

## Context
- Target: {file_path}
- Test pattern: tests/{matching_path}
- Existing test examples: tests/services/test_track_service.py

## Requirements
- Happy path + edge cases + error cases
- pytest-asyncio (asyncio_mode = "auto", no @pytest.mark.asyncio needed)
- In-memory SQLite for DB tests

## Acceptance criteria
- [ ] >= 80% coverage for target module
- [ ] `make check` passes
```

---

## Метрики эффективности

| Метрика | Цель | Как считать |
|---------|------|-------------|
| Agent success rate | > 70% | Merged PRs / Total agent PRs |
| First-pass success | > 50% | PRs merged без повторных фиксов / Total |
| Time to merge | < 30 min | Created → Merged |
| Rework ratio | < 30% | Фиксы после review / Total commits |
| Local fallback rate | < 20% | Задачи забранные локально / Total delegated |

---

## Чеклист запуска режима

Перед началом делегированной разработки:

- [ ] Codegen Bridge plugin включён (`.claude/settings.json`)
- [ ] Codegen имеет доступ к репозиторию (GitHub app установлен)
- [ ] Setup commands настроены в Codegen Dashboard
- [ ] Agent rules настроены
- [ ] Linear интеграция подключена (если используется)
- [ ] Codex auto-review включён
- [ ] Feature branch создана от dev
- [ ] PR создан (draft) для отслеживания
