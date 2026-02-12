# DJ Techno Set Builder

Audio analysis, transition matching & set construction backend.

## Tech Stack

- **Python 3.12+**, FastAPI, Pydantic v2
- **SQLAlchemy 2.0** (async) + Alembic
- **FastMCP** — LLM tool server
- **uv** — package manager

## Quick Start

```bash
# Install dependencies
uv sync --all-extras

# Run dev server
uv run uvicorn app.main:app --reload

# Run MCP server
uv run python -m app.mcp_server
```

## Database

```bash
# schema_v6 migrations are PostgreSQL-only:
# export ALEMBIC_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dj_techno

# Create migration
uv run alembic revision --autogenerate -m "describe change"

# Apply migrations
uv run alembic upgrade head

# Rollback one step
uv run alembic downgrade -1
```

## Testing

```bash
uv run pytest -v
```

## Linting & Type Checking

```bash
uv run ruff check app tests
uv run ruff check --fix app tests
uv run ruff format app tests
python3 scripts/enforce_mapped_column_style.py
uv run ruff format --check app tests
uv run mypy app
```

## Project Structure

```
app/
├── core/              # Config, errors, logging, monitoring
│   └── middleware/     # Request-ID, HTTP logging, metrics
├── db/                # Engine, session factory, Unit of Work
├── common/            # Base DTO, service, repository, router
├── main.py            # FastAPI application factory
└── mcp_server.py      # FastMCP tool server
migrations/            # Alembic migration scripts
tests/                 # pytest test suite
```
