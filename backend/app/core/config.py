"""Application settings loaded from environment variables / `.env`.

All configuration lives here so the rest of the code never reads `os.environ` directly.
Values are validated by Pydantic at startup: a bad value fails fast instead of at runtime.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Only acceptable for local/test; the validator below rejects it in staging/production.
_INSECURE_DEV_SECRET = "insecure-dev-secret-change-me"


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

    # ---------- Auth ----------
    # Signs access tokens. Anyone holding it can forge logins - keep it secret and long.
    jwt_secret_key: SecretStr = SecretStr(_INSECURE_DEV_SECRET)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def _require_strong_secret_outside_dev(self) -> "Settings":
        if self.environment in {"staging", "production"}:
            secret = self.jwt_secret_key.get_secret_value()
            if secret == _INSECURE_DEV_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET_KEY must be a random value of 32+ characters.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (parsed once per process)."""
    return Settings()
