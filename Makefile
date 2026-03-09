.DEFAULT_GOAL := help

# ── Variables ────────────────────────────────────────────────────────────────
UV       := uv
APP      := app
TESTS    := tests
PORT     ?= 8000
WORKERS  ?= 4
MCP_PORT ?= 9100
MCP_SPEC := app/mcp/gateway.py:create_dj_mcp

# Fix for typing-extensions import priority issues in some environments
VENV_PYTHONPATH := .venv/lib/python3.13/site-packages
UV_RUN := PYTHONPATH="$(VENV_PYTHONPATH):$(PYTHONPATH)" $(UV) run

# Docker compose file combinations
DC       := docker compose
DC_DEV   := $(DC) -f compose.yaml -f compose.dev.yaml
DC_PROD  := $(DC) -f compose.yaml -f compose.prod.yaml

# ── Phony ────────────────────────────────────────────────────────────────────
.PHONY: help install dev clean \
        lint ruff ruff-fix format mypy check \
        test test-v test-k test-file coverage \
        run run-prod kill \
        db db-upgrade db-downgrade db-revision db-history db-current db-reset db-schema \
        docker-local docker-dev docker-prod docker-down docker-logs docker-ps docker-shell docker-test \
        mcp-dev mcp-inspect mcp-list mcp-call mcp-install-desktop mcp-install-code \
        refresh-features refresh-sections refresh-scores refresh-ym refresh-all refresh-dry \
        all ci

# ═════════════════════════════════════════════════════════════════════════════
# Help
# ═════════════════════════════════════════════════════════════════════════════

help:
	@echo "══════════════════════════════════════════════════"
	@echo "  DJ Techno Set Builder"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "  Установка"
	@echo "  ─────────────────────────────────────"
	@echo "  install        Установка production зависимостей"
	@echo "  dev            Установка всех зависимостей (+ dev)"
	@echo "  clean          Очистка кэша и временных файлов"
	@echo ""
	@echo "  Проверка кода"
	@echo "  ─────────────────────────────────────"
	@echo "  lint           Все проверки (ruff check + format check + mypy)"
	@echo "  ruff           Ruff check"
	@echo "  ruff-fix       Ruff check --fix"
	@echo "  format         Ruff format (применить)"
	@echo "  mypy           Проверка типов (strict)"
	@echo "  check          lint + test (полная проверка)"
	@echo ""
	@echo "  Тестирование"
	@echo "  ─────────────────────────────────────"
	@echo "  test           Запуск тестов"
	@echo "  test-v         Тесты с подробным выводом"
	@echo "  test-k MATCH=  Тесты по имени (make test-k MATCH=harmony)"
	@echo "  test-file F=   Один файл (make test-file F=tests/test_tracks.py)"
	@echo "  coverage       Покрытие кода тестами (html + terminal)"
	@echo ""
	@echo "  Запуск"
	@echo "  ─────────────────────────────────────"
	@echo "  run            Dev сервер с hot reload (PORT=$(PORT))"
	@echo "  run-prod       Production режим ($(WORKERS) workers)"
	@echo "  kill           Убить процессы на порту $(PORT)"
	@echo ""
	@echo "  База данных (Alembic)"
	@echo "  ─────────────────────────────────────"
	@echo "  db             Показать текущую ревизию + историю"
	@echo "  db-upgrade     Применить все миграции"
	@echo "  db-downgrade   Откатить одну миграцию"
	@echo "  db-revision M= Создать ревизию (make db-revision M=\"add users\")"
	@echo "  db-history     История миграций"
	@echo "  db-current     Текущая ревизия"
	@echo "  db-reset       Откатить ВСЕ миграции до base"
	@echo "  db-schema      Дамп схемы БД в .claude/rules/db-schema.md"
	@echo ""
	@echo "  Docker"
	@echo "  ─────────────────────────────────────"
	@echo "  docker-local   Запуск local (volume mount, hot reload)"
	@echo "  docker-dev     Запуск dev (собранный образ)"
	@echo "  docker-prod    Запуск production"
	@echo "  docker-down    Остановить все контейнеры"
	@echo "  docker-logs    Логи (follow)"
	@echo "  docker-ps      Статус контейнеров"
	@echo "  docker-shell   Shell в app контейнере"
	@echo "  docker-test    Запуск тестов в dev контейнере"
	@echo ""
	@echo "  MCP Server"
	@echo "  ─────────────────────────────────────"
	@echo "  mcp-dev        HTTP dev-сервер с hot-reload (порт $(MCP_PORT))"
	@echo "  mcp-inspect    MCP Inspector UI (порт 6274)"
	@echo "  mcp-list       Список всех MCP-инструментов"
	@echo "  mcp-call TOOL= Вызов инструмента (make mcp-call TOOL=dj_get_track_details ARGS='{\"track_id\": 45}')"
	@echo "  mcp-install-desktop  Установить в Claude Desktop (stdio)"
	@echo "  mcp-install-code     Установить в Claude Code глобально (stdio)"
	@echo ""
	@echo "  CI / All"
	@echo "  ─────────────────────────────────────"
	@echo "  ci             Полный CI pipeline (lint + test + coverage)"
	@echo "  all            clean + dev + check"
	@echo "══════════════════════════════════════════════════"

# ═════════════════════════════════════════════════════════════════════════════
# Установка и зависимости
# ═════════════════════════════════════════════════════════════════════════════

install:
	$(UV) sync --frozen

dev:
	$(UV) sync --frozen --all-groups

clean:
	rm -rf build/ dist/ *.egg-info/ .coverage htmlcov/ .pytest_cache/ .ruff_cache/ .mypy_cache/ __pycache__/ */__pycache__/ */*/__pycache__/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	@echo "Очищено"

# ═════════════════════════════════════════════════════════════════════════════
# Проверка кода
# ═════════════════════════════════════════════════════════════════════════════

lint: ruff mypy
	@$(UV) run ruff format --check $(APP) $(TESTS)

ruff:
	$(UV_RUN) ruff check $(APP) $(TESTS)

ruff-fix:
	$(UV) run ruff check --fix $(APP) $(TESTS)
	$(UV) run ruff format $(APP) $(TESTS)

format:
	$(UV) run ruff format $(APP) $(TESTS)

mypy:
	$(UV_RUN) mypy $(APP)

check: lint test

# ═════════════════════════════════════════════════════════════════════════════
# Тестирование
# ═════════════════════════════════════════════════════════════════════════════

test:
	$(UV_RUN) pytest

test-all:
	$(UV_RUN) pytest -m "" -v

test-v:
	$(UV_RUN) pytest -v

test-k:
	$(UV_RUN) pytest -v -k "$(MATCH)"

test-file:
	$(UV_RUN) pytest -v $(F)

coverage:
	$(UV_RUN) pytest --cov=$(APP) $(TESTS)/ --cov-report=term --cov-report=html
	@echo "HTML-отчёт: htmlcov/index.html"

# ═════════════════════════════════════════════════════════════════════════════
# Запуск
# ═════════════════════════════════════════════════════════════════════════════

run:
	$(UV) run uvicorn $(APP).main:app --host 0.0.0.0 --port $(PORT) --reload

run-prod:
	$(UV) run uvicorn $(APP).main:app --host 0.0.0.0 --port $(PORT) --workers $(WORKERS) --log-level warning

kill:
	@PIDS=$$(lsof -ti :$(PORT) 2>/dev/null || true); \
	if [ -n "$$PIDS" ]; then \
		kill -9 $$PIDS && \
		echo "Процессы на порту $(PORT) убиты"; \
	else \
		echo "Нет процессов на порту $(PORT)"; \
	fi

# ═════════════════════════════════════════════════════════════════════════════
# База данных (Alembic)
# ═════════════════════════════════════════════════════════════════════════════

db: db-current db-history

db-upgrade:
	$(UV) run alembic upgrade head

db-downgrade:
	@OUT=$$($(UV) run alembic downgrade -1 2>&1); RC=$$?; \
	if [ $$RC -eq 0 ]; then \
		printf "%s\n" "$$OUT"; \
	elif echo "$$OUT" | grep -q "Relative revision -1 didn't produce 1 migrations"; then \
		echo "Нет миграций для отката (уже base)"; \
	else \
		printf "%s\n" "$$OUT"; \
		exit $$RC; \
	fi

db-revision:
ifndef M
	$(error Укажи сообщение: make db-revision M="add users table")
endif
	$(UV) run alembic revision --autogenerate -m "$(M)"

db-history:
	$(UV) run alembic history --verbose

db-current:
	$(UV) run alembic current

db-reset:
	@echo "Откат ВСЕХ миграций до base..."
	$(UV) run alembic downgrade base

db-schema:
	$(UV) run python scripts/dump_db_schema.py

# ═════════════════════════════════════════════════════════════════════════════
# Docker
# ═════════════════════════════════════════════════════════════════════════════

docker-local:
	$(DC) up

docker-dev:
	$(DC_DEV) up --build

docker-prod:
	$(DC_PROD) up -d --build

docker-down:
	$(DC) down
	$(DC_DEV) down 2>/dev/null || true
	$(DC_PROD) down 2>/dev/null || true

docker-logs:
	$(DC) logs -f

docker-ps:
	$(DC) ps -a

docker-shell:
	$(DC) run --rm app bash

docker-test:
	$(DC_DEV) run --rm -e DATABASE_URL=sqlite+aiosqlite:///./dev.db -v $(CURDIR)/tests:/app/tests app pytest -v tests

# ═════════════════════════════════════════════════════════════════════════════
# MCP Server
# ═════════════════════════════════════════════════════════════════════════════

mcp-dev:
	$(UV) run fastmcp run --transport http --host 127.0.0.1 --port $(MCP_PORT) --reload --reload-dir $(APP)/mcp --skip-env

mcp-inspect:
	$(UV) run fastmcp dev inspector $(MCP_SPEC) --ui-port 6274 --reload --reload-dir $(APP)/mcp

mcp-list:
	$(UV) run fastmcp list --command "$(UV) run fastmcp run $(MCP_SPEC) --skip-env"

mcp-call:
ifndef TOOL
	$(error Укажи инструмент: make mcp-call TOOL=dj_get_track_details ARGS='{"track_id": 45}')
endif
	$(UV) run fastmcp call --command "$(UV) run fastmcp run $(MCP_SPEC) --skip-env" --target $(TOOL) --input-json '$(ARGS)'

mcp-install-desktop:
	$(UV) run fastmcp install claude-desktop $(MCP_SPEC) --name dj-techno --env-file .env --with-editable .

mcp-install-code:
	$(UV) run fastmcp install claude-code $(MCP_SPEC) --name dj-techno --env-file .env --with-editable .

# ═════════════════════════════════════════════════════════════════════════════
# Data Refresh
# ═════════════════════════════════════════════════════════════════════════════

refresh-features:
	$(UV) run python scripts/refresh_data.py --mode features --workers 4

refresh-sections:
	$(UV) run python scripts/refresh_data.py --mode sections

refresh-scores:
	$(UV) run python scripts/rescore_sets.py

refresh-ym:
	$(UV) run python scripts/refresh_ym_metadata.py --mode all

refresh-all: refresh-ym refresh-features refresh-sections refresh-scores
	@echo "All data refreshed"

refresh-dry:
	$(UV) run python scripts/refresh_data.py --mode all --dry-run
	$(UV) run python scripts/refresh_ym_metadata.py --mode all --dry-run
	$(UV) run python scripts/rescore_sets.py --dry-run

# ═════════════════════════════════════════════════════════════════════════════
# CI / All
# ═════════════════════════════════════════════════════════════════════════════

ci: lint coverage

all: clean dev check
