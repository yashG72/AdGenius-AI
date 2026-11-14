"""Application settings loaded from environment variables / `.env`.

All configuration lives here so the rest of the code never reads `os.environ` directly.
Values are validated by Pydantic at startup: a bad value fails fast instead of at runtime.
"""

from functools import lru_cache
from pathlib import Path
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

    # ---------- Redis / Celery ----------
    # 127.0.0.1 rather than "localhost": avoids slow IPv6-then-IPv4 attempts on Windows.
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ---------- Qdrant (vector database) ----------
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: SecretStr | None = None  # only needed for Qdrant Cloud
    qdrant_collection: str = "brand_documents"

    # ---------- Embeddings (local, free - FastEmbed / ONNX on CPU) ----------
    # jina-v2-small: 512-dim, 8192-token input, so ~800-token chunks are never truncated.
    dense_embedding_model: str = "jinaai/jina-embeddings-v2-small-en"
    sparse_embedding_model: str = "Qdrant/bm25"  # keyword vectors for hybrid search
    embedding_batch_size: int = Field(default=16, ge=1)
    embedding_cache_dir: Path = Path.home() / ".cache" / "adgenius" / "fastembed"

    # ---------- Documents ----------
    storage_dir: Path = Path("storage/documents")  # private: never served directly
    max_upload_size_mb: int = Field(default=25, ge=1)
    max_pdf_pages: int = Field(default=500, ge=1)
    chunk_size_tokens: int = Field(default=800, ge=100)
    chunk_overlap_tokens: int = Field(default=120, ge=0)

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> "Settings":
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS.")
        return self

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
