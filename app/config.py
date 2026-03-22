from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DJ Techno Set Builder"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "sqlite+aiosqlite:///./dev.db"

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not (v.startswith("sqlite+aiosqlite://") or v.startswith("postgresql+asyncpg://")):
            raise ValueError(
                "Unsupported database URL scheme. Use sqlite+aiosqlite:// or postgresql+asyncpg://"
            )
        return v

    yandex_music_token: str = Field(default="", repr=False)
    yandex_music_user_id: str = ""
    yandex_music_base_url: str = "https://api.music.yandex.net:443"

    dj_library_path: str = Field(
        default="~/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/library",
        description="Path to DJ library directory for downloaded files",
    )

    # Sentry
    sentry_dsn: str = Field(default="", repr=False)
    sentry_traces_sample_rate: float = 1.0
    sentry_send_pii: bool = True
    environment: str = "development"

    # OpenTelemetry
    otel_endpoint: str | None = None
    otel_insecure: bool = True
    otel_service_name: str = "dj-set-builder-mcp"

    # MCP Observability
    mcp_cache_dir: str = "./cache/mcp"
    mcp_cache_ttl_tools: int = 60
    mcp_cache_ttl_resources: int = 300
    mcp_retry_max: int = 3
    mcp_retry_backoff: float = 1.0
    mcp_ping_interval: int = 30
    mcp_log_payloads: bool = False

    # Sampling (LLM fallback)
    anthropic_api_key: str = Field(default="", repr=False)
    sampling_model: str = "claude-sonnet-4-5-20250929"
    sampling_max_tokens: int = 1024

    # Pagination
    mcp_page_size: int = 50


settings = Settings()
