# syntax=docker/dockerfile:1

# ═══════════════════════════════════════════════════════════════════════════════
# Multi-stage Dockerfile for DJ Techno Set Builder
#
# Targets:
#   local — не используется (volume mount через compose.override.yaml)
#   dev   — образ со всеми зависимостями (включая dev: pytest, ruff, mypy)
#   prod  — минимальный образ, non-root user, только production deps
#
# Build:
#   docker build --target dev  -t dj-set-builder:dev  .
#   docker build --target prod -t dj-set-builder:prod .
# ═══════════════════════════════════════════════════════════════════════════════

# ── Base ─────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Builder (production deps only) ──────────────────────────────────────────
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Сначала lock-файлы — для кэширования слоя зависимостей
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости без самого проекта (кэш слоя при изменении кода)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Копируем код и финализируем установку
COPY app/ app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Builder-dev (all deps including dev tools) ──────────────────────────────
FROM base AS builder-dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# ── Dev ──────────────────────────────────────────────────────────────────────
# Полный образ для CI/staging: включает ruff, mypy, pytest
FROM base AS dev

COPY --from=builder-dev /app /app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Prod ─────────────────────────────────────────────────────────────────────
# Минимальный образ: только production deps, non-root user
FROM base AS prod

# Non-root user
RUN groupadd --system app && useradd --system --gid app app

# Копируем только venv из builder (не dev-зависимости)
COPY --from=builder /app/.venv /app/.venv

# Код приложения
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "warning"]
