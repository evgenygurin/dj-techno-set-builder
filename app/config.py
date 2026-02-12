from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DJ Techno Set Builder"
    debug: bool = False
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./dev.db"


settings = Settings()
