"""Application settings loaded from environment variables / `.env`.

All configuration lives here so the rest of the code never reads `os.environ` directly.
Values are validated by Pydantic at startup: a bad value fails fast instead of at runtime.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Application ----------
    app_name: str = "AdGenius AI"
    app_version: str = "0.1.0"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ---------- HTTP ----------
    cors_origins: list[str] = ["http://localhost:3000"]

    # ---------- Database ----------
    # Async driver URL, e.g. postgresql+asyncpg://user:pass@localhost:5432/adgenius
    database_url: str = "postgresql+asyncpg://adgenius:adgenius@localhost:5432/adgenius"
    # Separate database used only by the test suite (it gets wiped on every run).
    test_database_url: str | None = None
    database_echo: bool = False  # log every SQL statement (noisy; debugging only)
    database_pool_size: int = 10
    database_max_overflow: int = 20


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (parsed once per process)."""
    return Settings()
