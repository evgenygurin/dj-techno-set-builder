# Отчёт: Аудит ORM моделей vs схемы БД (BPM-1)

**Дата:** 15.02.2026  
**Issue:** [BPM-1](https://linear.app/r2r-cloud-platform/issue/BPM-1/audit-orm-models-against-schema-v6-and-document-gaps)  
**Ветка:** `codegen/BPM-1-orm-schema-audit`  
**PR:** [#9](https://github.com/evgenygurin/dj-techno-set-builder/pull/9)

## Summary

Выполнен полный аудит соответствия SQLAlchemy моделей и SQL DDL схемы. Обнаружено и исправлено 5 критических несоответствий в default-значениях колонок. Покрытие улучшено с 79.5% до 90.9% (40/44 таблицы идеальное соответствие).

**Ключевая проблема:** Python-уровневые defaults в ORM не отражались как SQL DDL defaults в схеме БД.

## Decisions

### Исправленные несоответствия (5 таблиц):
1. **`dj_beatgrid`** - добавлены `default=False` + `server_default="0"` для `is_variable_tempo`, `is_canonical`
2. **`tracks`** - добавлен `default=0` + `server_default="0"` для `status`  
3. **`feature_extraction_runs`** - добавлен `default="running"` + `server_default=text("'running'")` для `status`
4. **`transition_runs`** - добавлен `default="running"` + `server_default=text("'running'")` для `status`
5. **`track_audio_features_computed`** - добавлены двойные defaults для `is_atonal`, `is_variable_tempo`, `computed_from_asset_type`

### Стратегия исправления:
- Использование `server_default` + Python `default` для полной совместимости
- Корректный SQL синтаксис: `text("'running'")` для строковых defaults
- Импорт `text` из SQLAlchemy для правильной SQL генерации

## Risks

### Исправленные риски:
- **Низкий риск** - изменения добавляют только SQL defaults, не меняют поведение
- **Обратная совместимость** - Python defaults сохранены
- **Откат** - простой (удаление server_default параметров)

### Остающиеся риски:
4 минорных несоответствия требуют отдельной миграции:
- `dj_set_feedback.feedback_type`
- `spotify_metadata.explicit`  
- `track_timeseries_refs.dtype`
- `transition_candidates.is_fully_scored`

## Blockers

Блокеров нет. Все критические проблемы решены.

## Next Steps

1. **Immediate:** Ревью и merge PR #9
2. **Short-term:** Создать отдельный issue для оставшихся 4 несоответствий
3. **Long-term:** Стандартизировать подходы к defaults в новых моделях

## Technical Details

**Затронутые файлы:**
- `app/models/catalog.py`
- `app/models/dj.py` 
- `app/models/features.py`
- `app/models/runs.py`
- `AUDIT_REPORT_BPM-1.md`

**Проверки:**
- ✅ `uv run ruff check` (исправлены стилевые предупреждения)
- ✅ `uv run mypy app/` (ожидаемые numpy warnings)  
- ✅ Базовая валидация моделей

**Commit:** 55f145e - "Fix ORM model default consistency issues (BPM-1)"