"""Application configuration via Pydantic Settings v2."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "dj-techno-set-builder"
    app_env: str = "dev"  # dev | staging | prod
    debug: bool = False
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    # Optional dedicated DB URL for Alembic (use PostgreSQL for schema_v6 migrations).
    alembic_database_url: str | None = None


settings = Settings()
