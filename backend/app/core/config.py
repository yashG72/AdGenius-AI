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
    # Peers allowed to tell us the real client IP via X-Forwarded-For (the Next.js server
    # for auth calls, a load balancer in deployment). Anyone else's header is ignored.
    trusted_proxies: list[str] = ["127.0.0.1", "::1"]
    # HSTS tells browsers to only ever use HTTPS - enable only when served over HTTPS.
    hsts_enabled: bool = False
    # JSON request bodies above this are rejected (413) before parsing. Uploads have
    # their own, larger limit (MAX_UPLOAD_SIZE_MB).
    max_json_body_kb: int = Field(default=1024, ge=16)

    # ---------- Rate limiting (Redis) ----------
    rate_limit_enabled: bool = True
    login_max_failures: int = Field(default=5, ge=1)  # per email, then a lockout window
    login_lockout_seconds: int = Field(default=15 * 60, ge=1)

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

    # ---------- Redis / background jobs ----------
    # 127.0.0.1 rather than "localhost": avoids slow IPv6-then-IPv4 attempts on Windows.
    # Empty = no Redis: caches and rate limits fall back to in-process memory, which is
    # fine for a single-instance deployment (requires TASK_MODE=inline: no queue).
    redis_url: str | None = "redis://127.0.0.1:6379/0"
    # "celery": jobs go to Redis queues and separate worker processes (local dev, scalable).
    # "inline": jobs run inside the API process (free hosting with no background workers).
    task_mode: Literal["celery", "inline"] = "celery"
    inline_max_concurrent_campaigns: int = Field(default=1, ge=1, le=4)  # bounds RAM use

    # ---------- Qdrant (vector database) ----------
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: SecretStr | None = None  # only needed for Qdrant Cloud
    qdrant_collection: str = "brand_documents"

    # ---------- Embeddings (local, free - FastEmbed / ONNX on CPU) ----------
    # jina-v2-small: 512-dim, 8192-token input, so ~800-token chunks are never truncated.
    dense_embedding_model: str = "jinaai/jina-embeddings-v2-small-en"
    sparse_embedding_model: str = "Qdrant/bm25"  # keyword vectors for hybrid search
    embedding_batch_size: int = Field(default=16, ge=1)
    # "local" = FastEmbed models on this machine; "gemini" = Gemini embedding API for the
    # dense vectors (no model in RAM - for small hosts). Changing it requires re-indexing:
    # vectors from different models are not comparable (use a new QDRANT_COLLECTION).
    embedding_provider: Literal["local", "gemini"] = "local"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dim: int = Field(default=768, ge=128, le=3072)
    embedding_cache_dir: Path = Path.home() / ".cache" / "adgenius" / "fastembed"

    # ---------- Documents ----------
    storage_dir: Path = Path("storage/documents")  # private: never served directly
    max_upload_size_mb: int = Field(default=25, ge=1)
    max_pdf_pages: int = Field(default=500, ge=1)
    chunk_size_tokens: int = Field(default=800, ge=100)
    chunk_overlap_tokens: int = Field(default=120, ge=0)

    # ---------- LLM (Google Gemini, free AI Studio tier) ----------
    google_api_key: SecretStr | None = None  # without it, LLM features degrade gracefully
    llm_model: str = "gemini-3.8-flash"
    # Used when the primary model fails (e.g. free-tier overload). Empty string disables it.
    llm_fallback_model: str = "gemini-3.5-flash"
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_timeout_seconds: int = Field(default=120, ge=1)  # long outputs (storyboards) need room
    llm_max_retries: int = Field(default=2, ge=0)

    # ---------- RAG ----------
    # Reranking is OFF by default: on our evaluation set (docs/RAG_EVALUATION.md) none of
    # four local cross-encoders beat plain hybrid search, while adding 0.3-2.7 s per query.
    # MiniLM-L-12 was the best of them (note: it reads only the first 512 tokens of a chunk).
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-12-v2"
    rag_rerank_enabled: bool = False
    rag_query_rewrite_enabled: bool = True
    rag_max_query_variants: int = Field(default=3, ge=0, le=5)  # extra queries from rewriting
    rag_candidates_per_search: int = Field(default=20, ge=1)  # depth of each dense/sparse search
    rag_rerank_candidates: int = Field(default=20, ge=1)  # fused results sent to the reranker
    rag_top_k: int = Field(default=8, ge=1)  # results returned by search
    rag_context_chunks: int = Field(default=5, ge=1)  # chunks given to the LLM
    rag_context_token_budget: int = Field(default=4000, ge=200)

    # ---------- Live web research (Tavily) ----------
    tavily_api_key: SecretStr | None = None
    web_search_depth: Literal["basic", "advanced"] = "basic"  # basic = 1 credit, advanced = 2
    web_search_max_results: int = Field(default=5, ge=1, le=20)
    web_search_timeout_seconds: int = Field(default=20, ge=1)
    web_search_cache_ttl_seconds: int = Field(default=24 * 3600, ge=0)  # 0 disables caching
    web_research_max_queries: int = Field(default=6, ge=1, le=15)  # credit budget per run
    web_research_concurrency: int = Field(default=3, ge=1, le=10)
    web_research_max_evidence: int = Field(default=20, ge=1, le=50)
    web_snippet_max_chars: int = Field(default=1200, ge=200, le=5000)

    # ---------- Multi-agent workflow ----------
    agent_approval_threshold: float = Field(default=80, ge=0, le=100)  # Critic pass mark
    agent_max_revisions: int = Field(default=2, ge=0, le=5)  # automatic revision rounds
    agent_max_concept_rounds: int = Field(default=3, ge=1, le=10)  # human reject limit
    agent_max_attempts: int = Field(default=3, ge=1, le=6)  # retries per LLM node
    agent_retry_initial_seconds: float = Field(default=2.0, ge=0)
    agent_brand_context_chunks: int = Field(default=12, ge=1, le=40)

    # ---------- Live run events (Server-Sent Events) ----------
    sse_poll_interval_seconds: float = Field(default=1.0, gt=0)
    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)
    sse_max_stream_seconds: float = Field(default=900.0, gt=0)  # client reconnects after

    # ---------- Tracing (optional) ----------
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "adgenius"

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> "Settings":
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS.")
        return self

    @model_validator(mode="after")
    def _queue_needs_redis(self) -> "Settings":
        if self.task_mode == "celery" and not self.redis_url:
            raise ValueError("TASK_MODE=celery needs REDIS_URL (or set TASK_MODE=inline).")
        return self

    @model_validator(mode="after")
    def _require_strong_secret_outside_dev(self) -> "Settings":
        if self.environment in {"staging", "production"}:
            secret = self.jwt_secret_key.get_secret_value()
            if secret == _INSECURE_DEV_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET_KEY must be a random value of 32+ characters.")
            if self.debug:
                raise ValueError("DEBUG must be off outside local/test environments.")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS cannot be '*' when credentials are allowed.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (parsed once per process)."""
    return Settings()
