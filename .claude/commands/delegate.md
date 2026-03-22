# /delegate — Delegated Development via Codegen

Запускает Codegen cloud агента для выполнения задачи.

## Как использовать

```text
/delegate <описание задачи>
/delegate BPM-123 <описание задачи>
```

## Что произойдёт

1. Claude проанализирует задачу и декомпозирует её при необходимости
2. Сформирует промпт с context, requirements, constraints, acceptance criteria
3. Запустит Codegen agent через codegen-bridge plugin
4. Агент создаст ветку, реализует задачу, запустит make check и создаст PR
5. Claude сделает review diff и сообщит о результате

## Аргументы

`$ARGUMENTS` — описание задачи (что нужно сделать) и опциональный BPM-xxx ID.

---

Используй `delegated-development` skill для полного workflow, промптов и quality gates.

## Примеры задач

```text
# Тесты
/delegate Добавить тесты для classify_tracks в tests/mcp/test_workflow_curation.py

# Lint/mypy
/delegate Исправить все mypy ошибки в app/services/set_generation.py

# Рефакторинг
/delegate Извлечь общий паттерн фильтрации из TrackRepository и PlaylistRepository

# Документация
/delegate Добавить docstrings к публичным методам app/services/transition_scoring.py

# Новый MCP tool
/delegate Добавить MCP tool get_transition_details(from_track_id, to_track_id) в app/mcp/tools/setbuilder.py
```

Задача для делегирования: **$ARGUMENTS**
