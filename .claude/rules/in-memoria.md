# In-Memoria Codebase Intelligence

Rules for using In-Memoria MCP tools to get project context before writing code.

## Session start (BLOCKING — выполни ДО любых действий)

**ПЕРВОЕ действие в каждой сессии** — до Glob, Grep, Read, до ответа пользователю.
Это не опционально. Не пропускай даже если задача кажется простой.
Стоимость: <200 токенов, <2 секунды. Нет причин пропускать.

```text
1. ToolSearch → загрузить In-Memoria tools (если ещё не загружены)
2. get_project_blueprint(path: '/Users/laptop/dev/dj-techno-set-builder', includeFeatureMap: true)
3. If learningStatus.recommendation !== 'ready' → auto_learn_if_needed(path: '...')
4. get_developer_profile(includeRecentActivity: true) — once per session
```

**Почему**: blueprint даёт featureMap, architecture, keyDirectories — ты получаешь карту проекта мгновенно вместо слепого поиска через Glob/Grep.

## When to use each tool

| Trigger | Tool | Required params |
|---------|------|-----------------|
| Starting a session | `get_project_blueprint` | `includeFeatureMap: true` |
| Before implementing a feature | `get_pattern_recommendations` | `problemDescription`, `includeRelatedFiles: true` |
| Need to find code by keyword | `search_codebase` | `type: 'text'`, `limit: 10` |
| Analyzing a topic across codebase | `search_codebase` | `type: 'text'` — **до** Grep/Glob, даёт контекст с номерами строк |
| Deep-diving a specific file | `analyze_codebase` | `path: absolute_path_to_file` |
| After an architectural decision | `contribute_insights` | `type: 'best_practice'`, `content: {practice, reasoning}`, `sourceAgent: 'claude-code'` |

## Порядок инструментов при исследовании кода

Когда нужно найти/проанализировать код по теме:

```text
1. search_codebase(type: 'text', query: 'keyword') → список файлов + контекст строк
2. get_project_blueprint → featureMap покажет связанные модули
3. ЗАТЕМ Read/Grep/Glob для детального чтения конкретных файлов
```

**НЕ начинай с Glob/Grep** — In-Memoria даёт семантический контекст (какие файлы связаны), а Glob/Grep — только текстовые совпадения.

## Tool reliability (v0.6.0 patched)

| Tool | Rating | Notes |
|------|--------|-------|
| `get_project_blueprint` | **5/5** | keyDirs, entryPoints, featureMap, architecture — all work |
| `get_developer_profile` | **4/5** | Correct naming (snake_case), patterns, DI — use for conventions |
| `search_codebase(text)` | **4/5** | 42 results for BaseRepository — fast keyword search |
| `analyze_codebase` | **4/5** | AST, complexity, imports for specific files |
| `get_pattern_recommendations` | **3/5** | Returns real patterns (DI, Factory) but ignores query context |
| `predict_coding_approach` | **2/5** | Weak keyword matching, always falls back to database feature |
| `search_codebase(pattern)` | **2/5** | Returns DB patterns, not regex matches on code |
| `get_semantic_insights` | **0/5** | Always 0 results — Rust Python extractor broken |
| `search_codebase(semantic)` | **0/5** | Phase 5 incomplete — always empty |

## What NOT to do

- **NEVER** use `search_codebase(type: 'semantic')` — always returns 0 results
- **NEVER** use `get_semantic_insights` — Rust extractor finds 0 Python symbols
- **NEVER** use `search_codebase(type: 'text', language: 'python')` — language filter breaks search, returns 0
- **NEVER** rely on `predict_coding_approach` for file routing — use `get_project_blueprint.featureMap` + Grep/Glob instead
- **NEVER** call `learn_codebase_intelligence(force: true)` without reason — takes 55 sec, no-op if data is fresh

## Effective patterns

### Find where to add code

Use blueprint featureMap + Grep, NOT `predict_coding_approach`:

```text
1. get_project_blueprint(includeFeatureMap: true) → featureMap.services lists all service files
2. Grep for similar patterns in identified directory
3. get_pattern_recommendations(problemDescription: '...') → DI, Factory patterns to follow
```

### Understand coding conventions before writing

```text
1. get_developer_profile() → snake_case functions, PascalCase classes, DI pattern
2. get_pattern_recommendations(problemDescription: '...', includeRelatedFiles: true)
3. analyze_codebase(path: 'app/services/specific_file.py') → imports, complexity
```

### Record architectural decisions

After making important decisions (new patterns, approach choices):

```text
contribute_insights(
  type: 'best_practice',
  content: { practice: 'Use X pattern for Y', reasoning: 'Because Z' },
  confidence: 0.9,
  sourceAgent: 'claude-code'
)
```

## Path parameter

**ALWAYS** use absolute path: `/Users/laptop/dev/dj-techno-set-builder`

## Patched installation

In-Memoria v0.6.0 is patched for `app/` directory support. Patches in 3 files under `/opt/homebrew/lib/node_modules/in-memoria/dist/`. After `npm install -g in-memoria`, re-apply with `bash scripts/patch_in_memoria.sh`, then `pkill -f "in-memoria server"`.
